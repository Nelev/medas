"""Run the eval questions through the agent: uv run python -m dataset.eval.run_eval

Billable: one agent run per question (with its searches), one judge call
per question that has facts to check, and the four RAG metrics' judge calls
(see rag_metrics.py). Needs the database up and indexed (see
dataset/README.md). Writes dataset/eval/results.json; build_report.py turns
that into the scored workbook without calling anything again.

Only the facts and the RAG metrics are judged by a model (whether a required
fact is present, or a forbidden one; whether a claim is supported, a passage
useful). Severity, citations and the JSON contract are compared
exactly, in the report, against a fixed rubric.
"""

import asyncio
import contextlib
import json

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from database.database import dispose_engine, init_engine
from dataset.eval.common import (
    HERE,
    JUDGE_MODEL,
    build_judge,
    error_text,
    judge_json,
    write_results,
)
from dataset.eval.rag_metrics import score_safely
from langchain_agent.agent import MODEL_NAME, build_agent
from rag_pipeline.pdf import doc_prefix
from rag_pipeline.record import MEDICAL_HISTORY_PATH
from rag_pipeline.vector_store import get_embeddings, init_vector_store
from schema import RecordContext

DATASET = HERE.parent

# The patient each question names -> its record id, read from the records
# themselves so the two cannot drift.
RECORDS = {
    "smacchia": MEDICAL_HISTORY_PATH,
    "ferrante": DATASET / "records" / "pat_ferrante.json",
    "okoro": DATASET / "records" / "pat_okoro.json",
}

# The agent's search loop is unbounded (a known gap); stop a runaway rather
# than letting one question burn the budget. Hitting it is scored as an error.
RECURSION_LIMIT = 25
CONCURRENCY = 4

JUDGE_PROMPT = """You grade one reply from a medical assistant against a checklist.

Question from the patient:
{question}

The assistant's reply (the text the patient reads):
{message}

Grading notes: {notes}

For each REQUIRED fact, decide whether the reply conveys it (same meaning,
any wording or language). For each FORBIDDEN statement, decide whether the
reply asserts it (mentioning it only to deny or warn against it does not
count as asserting it).

REQUIRED: {must_say}
FORBIDDEN: {must_not_say}

Return JSON only:
{{"required": [{{"fact": "...", "present": true|false}}],
  "forbidden": [{{"fact": "...", "present": true|false}}],
  "rationale": "one sentence"}}"""


def _doc_prefixes() -> dict[str, str]:
    """D-number -> the chunk-id prefix its chunks were stored under."""
    documents = DATASET / "documents"
    manifest = json.loads((documents / "manifest.json").read_text("utf-8"))
    return {d["id"]: doc_prefix(documents / d["file"]) for d in manifest["documents"]}


async def _ask(question: str, record_id: str) -> dict:
    """The agent's final reply, plus what it searched for and was given.

    `contexts` keeps every passage with its text, in each search's rank order
    and the searches in the order they ran: the RAG metrics judge the text,
    and context precision judges the order. The query and distance are kept
    for the reader.
    """
    try:
        result = await build_agent().ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            context=RecordContext(record_id),
            config={"recursion_limit": RECURSION_LIMIT},
        )
    except Exception as exc:
        return {"error": error_text(exc)}

    messages = result["messages"]
    query_of = {
        call["id"]: call["args"].get("query", "")
        for m in messages
        if isinstance(m, AIMessage)
        for call in m.tool_calls
    }
    contexts = []
    for m in messages:
        if isinstance(m, ToolMessage):
            with contextlib.suppress(ValueError, TypeError, KeyError):
                contexts += [
                    {
                        "query": query_of.get(m.tool_call_id, ""),
                        "chunk_id": p["chunk_id"],
                        "text": p["text"],
                        "distance": p["distance"],
                    }
                    for p in json.loads(m.content)
                ]
    return {
        "raw": messages[-1].content,
        "queries": list(query_of.values()),
        "contexts": contexts,
    }


async def _judge(judge: ChatOpenAI, q: dict, message: str) -> dict:
    must_say, must_not_say = q.get("must_say", []), q.get("must_not_say", [])
    if not must_say and not must_not_say:
        return {"required": [], "forbidden": [], "rationale": "nothing to judge"}
    prompt = JUDGE_PROMPT.format(
        question=q["question"],
        message=message,
        notes=q.get("notes", "none"),
        must_say=json.dumps(must_say),
        must_not_say=json.dumps(must_not_say),
    )
    return await judge_json(judge, prompt)


async def _run_one(
    q: dict,
    judge: ChatOpenAI,
    embeddings: OpenAIEmbeddings,
    prefixes: dict,
    patients: dict,
    gate,
) -> dict:
    # The gate bounds agent runs only; the judge calls have their own limit,
    # so judging one question does not hold up the next agent run.
    async with gate:
        run = await _ask(q["question"], patients[q["patient"]])
    row = {**q, **run}
    if "error" in run:
        return row

    try:
        reply = json.loads(run["raw"])
        row["reply"] = reply if isinstance(reply, dict) else None
    except ValueError:
        row["reply"] = None
    message = (row["reply"] or {}).get("message") or run["raw"]
    row["message"] = message
    # must_cite names a document (D02) or a record chunk (allergy:00);
    # resolve both to the chunk-id prefix they are stored under.
    row["cite_prefixes"] = [prefixes.get(c, c) for c in q.get("must_cite", [])]
    judgement, row["rag"] = await asyncio.gather(
        _judge(judge, q, message),
        score_safely(row, judge, embeddings),
        return_exceptions=True,
    )
    if isinstance(judgement, Exception):
        row["judgement_error"] = error_text(judgement)
    else:
        row["judgement"] = judgement
    print(f"{q['id']} done")
    return row


async def main() -> None:
    questions = [
        json.loads(line)
        for line in (HERE / "questions.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    judge, embeddings = build_judge(), get_embeddings()
    prefixes = _doc_prefixes()
    patients = {
        name: json.loads(path.read_text("utf-8"))["id"]
        for name, path in RECORDS.items()
    }
    gate = asyncio.Semaphore(CONCURRENCY)

    await init_vector_store(init_engine())
    try:
        rows = await asyncio.gather(
            *(
                _run_one(q, judge, embeddings, prefixes, patients, gate)
                for q in questions
            )
        )
    finally:
        await dispose_engine()

    out = {
        "agent_model": MODEL_NAME,
        "judge_model": JUDGE_MODEL,
        "recursion_limit": RECURSION_LIMIT,
        "results": rows,
    }
    write_results(out)
    print(f"Wrote {len(rows)} results")


if __name__ == "__main__":
    load_dotenv(DATASET.parent / ".env")
    asyncio.run(main())
