"""What run_eval, rag_metrics and build_report share: the judge, the results
file, and how a chunk id is matched against a question's must_cite.
"""

import asyncio
import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

from utils import OPENROUTER_BASE_URL

HERE = Path(__file__).parent
RESULTS_PATH = HERE / "results.json"

# One judge for the rubric's facts and for the RAG metrics.
JUDGE_MODEL = "openai/gpt-4o"

# Every judge call in the run shares this: a question fans out to one call per
# claim, passage and fact, and several questions are judged at once.
_JUDGE_CALLS = asyncio.Semaphore(16)


def build_judge() -> ChatOpenAI:
    return ChatOpenAI(
        model=JUDGE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        temperature=0,
        extra_body={"response_format": {"type": "json_object"}},
    )


async def judge_json(judge: ChatOpenAI, prompt: str) -> dict:
    async with _JUDGE_CALLS:
        reply = await judge.ainvoke(prompt)
    return json.loads(reply.content)


def error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def read_results() -> dict:
    return json.loads(RESULTS_PATH.read_text("utf-8"))


def write_results(data: dict) -> None:
    # newline: LF on Windows too, so a rerun does not rewrite every line.
    RESULTS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), "utf-8", newline="\n"
    )


def chunk_tail(chunk_id: str) -> str:
    """A chunk id without its patient: pat_...:allergy:00 -> allergy:00."""
    return chunk_id.split(":", 1)[1] if chunk_id.startswith("pat_") else chunk_id


def matches(chunk_id: str, prefixes: list[str]) -> bool:
    """Whether a chunk belongs to one of the required sources."""
    tail = chunk_tail(chunk_id)
    return any(tail.startswith(p) for p in prefixes)


def sources_hit(chunk_ids: list[str], prefixes: list[str]) -> int:
    """How many required sources have at least one chunk among `chunk_ids`."""
    return sum(any(matches(c, [p]) for c in chunk_ids) for p in prefixes)


def answerable(row: dict) -> bool:
    """Whether the record holds the answer: the question names sources to cite."""
    return bool(row.get("must_cite"))
