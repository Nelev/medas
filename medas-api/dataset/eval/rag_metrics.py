"""The four RAG metrics, over one eval result: uv run python -m dataset.eval.rag_metrics

Run as a module, this rescores an existing results.json in place, without
asking the agent again -- for when a metric prompt changes. run_eval.py calls
score() on every fresh result, so a normal run needs nothing extra.

The definitions follow RAGAS, adapted to a record assistant:

- Faithfulness: the share of the answer's claims about the patient's record
  that the retrieved passages support. General medical knowledge and safety
  advice ("call 999") are claims no record could hold, so they are kept out of
  the ratio, not counted against it. Catches hallucinated record facts.
- Answer relevancy: the judge writes the questions the answer would be the
  answer to; their mean cosine similarity to the real question, embedded with
  the index's own model. A non-committal answer scores 0, but only when the
  record held the answer (common.answerable): refusing an off-topic question
  is the right answer, not an irrelevant one.
- Context precision: average precision over the passages in the order the
  model received them, each judged useful or not for the reference answer.
  Relevant passages ranked lower cost more.
- Context recall: the share of the reference's record facts (must_say) that
  the retrieved passages contain. Guidance and absence statements ("the record
  does not show...") are nothing retrieval could return, so they are left out.

Each LLM metric has an exact twin over chunk ids, using must_cite as the
relevance labels: id_precision (average precision) and id_recall (share of
required sources returned). They cost nothing and cannot be argued with, so a
disagreement between a metric and its twin is itself worth reading.

A metric that has nothing to measure is None, not 0: faithfulness for an
answer with no record claims, recall for a question with no record facts,
precision for a question with nothing relevant to find.
"""

import asyncio
import json
import math

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from dataset.eval.common import (
    HERE,
    answerable,
    build_judge,
    error_text,
    judge_json,
    matches,
    read_results,
    sources_hit,
    write_results,
)
from rag_pipeline.vector_store import get_embeddings

# Generated questions per answer, for answer relevancy (RAGAS uses 3).
N_QUESTIONS = 3

# Faithfulness is two steps, as in RAGAS: split the reply into claims, then
# check each claim alone. Asked to do both at once, over a whole reply, the
# judge waves details through -- a wrong start date passed as "supported".
CLAIMS_PROMPT = """Break this reply from a medical assistant into short, self-contained claims.

{answer}

Label each claim:
- "record": specific to this patient -- a diagnosis, medicine, dose,
  frequency, allergy, result, date, appointment, an instruction one of their
  clinicians or letters gave (what to bring, when to call), or that the
  record does not show something.
- "general": true for any patient -- general medical knowledge, generic
  advice or safety-netting, what the assistant can or cannot help with,
  questions back, or pleasantries.

Return JSON only:
{{"claims": [{{"claim": "...", "kind": "record"|"general"}}]}}"""

# The passages come first in the verify and recall prompts: they are the same
# for every claim and fact of a question, so the calls share a prefix the
# provider can cache.
VERIFY_PROMPT = """Record passages for a patient (the only evidence):
{contexts}

Is this claim about the patient supported by those passages?

Claim: {claim}

Supported means the passages state it or it follows directly from them, in
any wording or date format ("October 14" and "14 October" are the same date).
Each detail must match in value and in what it refers to: a date must be the
date of the same event, a dose the dose of the same medicine. A detail that
differs, or that the passages do not give, makes the claim unsupported. A
claim that the record does not show something is supported when no passage
shows it.

The passages are text extracted from PDFs: a table cell can wrap onto the
next line, so read a row's pieces together before calling a detail missing.

Quote the words that decide it (or leave the quote empty), then reason in
one sentence, then decide.

Return JSON only:
{{"evidence": "...", "reasoning": "...", "supported": true|false}}"""

RELEVANCY_PROMPT = """Here is a reply from a medical assistant to a patient:

{answer}

Write {n} different questions a patient could have asked for this to be the
reply, in the language of the reply. Also decide whether the reply is
non-committal: it declines, says it cannot help, or says it does not know or
that the record does not show the answer.

Return JSON only:
{{"questions": ["...", "..."], "noncommittal": true|false}}"""

# One call per passage and per fact, not one per question: asked for a list of
# verdicts, the judge sometimes returns fewer than it was given.
PRECISION_PROMPT = """A patient asked a medical assistant:
{question}

A correct answer conveys: {reference}
Grading notes: {notes}

Is this record passage useful for arriving at the correct answer? Useful means
it holds a fact the answer needs, or one that decides it; sharing the topic is
not enough.

Passage:
{passage}

Return JSON only:
{{"reason": "one sentence", "useful": true|false}}"""

RECALL_PROMPT = """Record passages retrieved for a patient's question:
{contexts}

The patient asked: {question}

A correct answer must convey this: {fact}

First label it:
- "record": a fact a patient record could hold (a medicine, date, result,
  diagnosis, allergy...).
- "other": advice, an instruction, a refusal, or a statement that something is
  absent from the record -- nothing a passage could contain.
If "record", decide whether the passages contain it or it follows directly
from them, and quote the words that do.

Return JSON only:
{{"kind": "record"|"other", "evidence": "...", "attributed": true|false}}"""


def ranked_contexts(row: dict) -> list[dict]:
    """Every passage the model was given, in the order it received them.

    Search after search, each in its own rank order, a passage returned twice
    counted once, where it first arrived: what a reader of the whole thread
    would have seen, and in what order.
    """
    seen: set[str] = set()
    out = []
    for p in row.get("contexts", []):
        if p["chunk_id"] not in seen:
            seen.add(p["chunk_id"])
            out.append(p)
    return out


def average_precision(verdicts: list[bool]) -> float | None:
    """Mean of precision@k over the ranks k that hold a relevant passage.

    1.0 when every relevant passage outranks every irrelevant one; None when
    nothing is relevant, since there is then no ranking to judge.
    """
    hits, total = 0, 0.0
    for k, relevant in enumerate(verdicts, start=1):
        if relevant:
            hits += 1
            total += hits / k
    return total / hits if hits else None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _ratio(items: list[dict], kind: str, verdict: str) -> float | None:
    counted = [x for x in items if x.get("kind") == kind]
    if not counted:
        return None
    return sum(bool(x.get(verdict)) for x in counted) / len(counted)


def _numbered(contexts: list[dict]) -> str:
    return (
        "\n\n".join(f"[{i}] {p['text']}" for i, p in enumerate(contexts, start=1))
        or "(no passages were retrieved)"
    )


def _id_metrics(contexts: list[dict], prefixes: list[str]) -> dict:
    """Precision and recall over chunk ids, with must_cite as the labels."""
    if not prefixes:
        return {"id_precision": None, "id_recall": None}
    ids = [p["chunk_id"] for p in contexts]
    return {
        "id_precision": average_precision([matches(c, prefixes) for c in ids]) or 0.0,
        "id_recall": sources_hit(ids, prefixes) / len(prefixes),
    }


async def _each(judge: ChatOpenAI, prompts: list[str]) -> list[dict]:
    return await asyncio.gather(*(judge_json(judge, p) for p in prompts))


async def _faithfulness(judge, answer: str, numbered: str) -> dict:
    j = await judge_json(judge, CLAIMS_PROMPT.format(answer=answer))
    claims = [c for c in j.get("claims", []) if c.get("claim")]
    record = [c for c in claims if c.get("kind") == "record"]
    verdicts = await _each(
        judge,
        [VERIFY_PROMPT.format(contexts=numbered, claim=c["claim"]) for c in record],
    )
    for c, v in zip(record, verdicts, strict=True):
        c["supported"] = bool(v.get("supported"))
        c["evidence"] = v.get("evidence", "")
        c["reasoning"] = v.get("reasoning", "")
    return {"faithfulness": _ratio(claims, "record", "supported"), "claims": claims}


async def _relevancy(judge, embeddings, row: dict, answer: str) -> dict:
    j = await judge_json(judge, RELEVANCY_PROMPT.format(answer=answer, n=N_QUESTIONS))
    generated = [q for q in j.get("questions", []) if q][:N_QUESTIONS]
    noncommittal = bool(j.get("noncommittal"))
    relevancy = 0.0
    # Only penalise "I don't know" when the record held the answer.
    if generated and not (noncommittal and answerable(row)):
        original, *others = await embeddings.aembed_documents(
            [row["question"], *generated]
        )
        relevancy = sum(cosine(original, v) for v in others) / len(others)
    return {
        "answer_relevancy": relevancy,
        "generated_questions": generated,
        "noncommittal": noncommittal,
    }


async def _precision(judge, row: dict, contexts: list[dict]) -> dict:
    if not contexts:
        return {"context_precision": None, "useful": []}
    reference = json.dumps(
        row.get("must_say") or ["(no fact list; see the notes)"], ensure_ascii=False
    )
    verdicts = await _each(
        judge,
        [
            PRECISION_PROMPT.format(
                question=row["question"],
                reference=reference,
                notes=row.get("notes", "none"),
                passage=p["text"],
            )
            for p in contexts
        ],
    )
    useful = [bool(v.get("useful")) for v in verdicts]
    ap = average_precision(useful)
    # Nothing useful returned: a miss when the record held the answer, and
    # nothing to judge when it did not.
    if ap is None and answerable(row):
        ap = 0.0
    return {"context_precision": ap, "useful": useful}


async def _recall(judge, row: dict, numbered: str) -> dict:
    facts = row.get("must_say", [])
    if not facts:
        return {"context_recall": None, "facts": []}
    verdicts = await _each(
        judge,
        [
            RECALL_PROMPT.format(contexts=numbered, question=row["question"], fact=f)
            for f in facts
        ],
    )
    judged = [{"fact": f, **v} for f, v in zip(facts, verdicts, strict=True)]
    return {"context_recall": _ratio(judged, "record", "attributed"), "facts": judged}


async def score(row: dict, judge: ChatOpenAI, embeddings: OpenAIEmbeddings) -> dict:
    """The four metrics and their id twins for one result, with the verdicts.

    A result without an answer (the agent errored) has nothing to score.
    """
    if "error" in row:
        return {}
    answer = row.get("message") or row.get("raw", "")
    contexts = ranked_contexts(row)
    numbered = _numbered(contexts)
    faithfulness, relevancy, precision, recall = await asyncio.gather(
        _faithfulness(judge, answer, numbered),
        _relevancy(judge, embeddings, row, answer),
        _precision(judge, row, contexts),
        _recall(judge, row, numbered),
    )
    return {
        "answerable": answerable(row),
        "passages": len(contexts),
        **_id_metrics(contexts, row.get("cite_prefixes", [])),
        **faithfulness,
        **relevancy,
        **precision,
        **recall,
    }


async def score_safely(
    row: dict, judge: ChatOpenAI, embeddings: OpenAIEmbeddings
) -> dict:
    """score(), with a failure kept on the row instead of ending the run."""
    try:
        return await score(row, judge, embeddings)
    except Exception as exc:
        return {"error": error_text(exc)}


async def main() -> None:
    data = read_results()
    if not any("contexts" in r for r in data["results"]):
        raise SystemExit("results.json has no passage text: rerun run_eval first")
    judge, embeddings = build_judge(), get_embeddings()

    async def one(row: dict) -> None:
        row["rag"] = await score_safely(row, judge, embeddings)
        print(f"{row['id']} scored")

    # The shared judge semaphore bounds the fan-out; no per-row gate needed.
    await asyncio.gather(*(one(r) for r in data["results"]))
    write_results(data)
    print(f"Rescored {len(data['results'])} results")


if __name__ == "__main__":
    load_dotenv(HERE.parent.parent / ".env")
    asyncio.run(main())
