"""Run the eval questions through the agent: uv run python -m dataset.eval.run_eval

Billable: one agent run per question (with its searches) and one judge call
per question that has facts to check. Needs the database up and indexed (see
dataset/README.md). Writes dataset/eval/results.json; build_report.py turns
that into the scored workbook without calling anything again.

Only the facts are judged by a model (whether a required fact is present, or
a forbidden one). Severity, citations and the JSON contract are compared
exactly, in the report, against a fixed rubric.
"""

import asyncio
import contextlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from database.database import dispose_engine, init_engine
from langchain_agent.agent import MODEL_NAME, RecordContext, build_agent
from langchain_agent.rag import MEDICAL_HISTORY_PATH
from rag_pipeline.pdf import doc_prefix
from rag_pipeline.vector_store import init_vector_store
from utils import OPENROUTER_BASE_URL

HERE = Path(__file__).parent
DATASET = HERE.parent

RESULTS_PATH = HERE / "results.json"

# The patient each question names -> its record id, read from the records
# themselves so the two cannot drift.
RECORDS = {
    "smacchia": MEDICAL_HISTORY_PATH,
    "ferrante": DATASET / "records" / "pat_ferrante.json",
    "okoro": DATASET / "records" / "pat_okoro.json",
}

JUDGE_MODEL = "openai/gpt-4o"

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
    """The agent's final reply, plus what it searched for and was given."""
    try:
        result = await build_agent().ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            context=RecordContext(record_id),
            config={"recursion_limit": RECURSION_LIMIT},
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}

    messages = result["messages"]
    queries = [
        call["args"].get("query", "")
        for m in messages
        if isinstance(m, AIMessage)
        for call in m.tool_calls
    ]
    returned = set()
    for m in messages:
        if isinstance(m, ToolMessage):
            with contextlib.suppress(ValueError, TypeError, KeyError):
                returned.update(p["chunk_id"] for p in json.loads(m.content))
    return {
        "raw": messages[-1].content,
        "queries": queries,
        "returned_ids": sorted(returned),
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
    reply = await judge.ainvoke(prompt)
    return json.loads(reply.content)


async def _run_one(
    q: dict, judge: ChatOpenAI, prefixes: dict, patients: dict, gate
) -> dict:
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
        # must_cite names a document (D05) or a record chunk (allergy:00);
        # resolve both to the chunk-id prefix they are stored under.
        row["cite_prefixes"] = [prefixes.get(c, c) for c in q.get("must_cite", [])]
        try:
            row["judgement"] = await _judge(judge, q, message)
        except Exception as exc:
            row["judgement_error"] = f"{type(exc).__name__}: {exc}"[:300]
        print(f"{q['id']} done")
        return row


async def main() -> None:
    questions = [
        json.loads(line)
        for line in (HERE / "questions.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    judge = ChatOpenAI(
        model=JUDGE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        temperature=0,
        extra_body={"response_format": {"type": "json_object"}},
    )
    prefixes = _doc_prefixes()
    patients = {
        name: json.loads(path.read_text("utf-8"))["id"]
        for name, path in RECORDS.items()
    }
    gate = asyncio.Semaphore(CONCURRENCY)

    await init_vector_store(init_engine())
    try:
        rows = await asyncio.gather(
            *(_run_one(q, judge, prefixes, patients, gate) for q in questions)
        )
    finally:
        await dispose_engine()

    out = {
        "agent_model": MODEL_NAME,
        "judge_model": JUDGE_MODEL,
        "recursion_limit": RECURSION_LIMIT,
        "results": rows,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    print(f"Wrote {len(rows)} results to {RESULTS_PATH}")


if __name__ == "__main__":
    load_dotenv(DATASET.parent / ".env")
    asyncio.run(main())
