"""Score the agent's tool calling: uv run python -m dataset.eval.run_tool_eval

Billable: one agent run per case in tool_cases.py. The tools' backends are
stubbed (no database, no vector store), so only the model's routing is judged.
Writes dataset/eval/tool_results.json.
"""

import asyncio
import json
from collections import defaultdict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

import langchain_agent.agent as agent_module
from dataset.eval.common import HERE, error_text
from dataset.eval.tool_cases import RECORD_ID, test_cases
from langchain_agent.agent import RecordContext, build_agent

RECURSION_LIMIT = 12


async def _search_record(query, patient_id):
    return [{"chunk_id": "c1", "text": "Allergy: penicillin", "distance": 0.2}]


async def _add_document(attachment, record_id):
    return 3


def _params_correct(case: dict, tool_calls: list[dict]) -> bool:
    """Every wanted keyword appears in the expected tool's arguments."""
    for argument, wanted in (case["expected_params"] or {}).items():
        seen = " ".join(
            str(c["args"].get(argument, ""))
            for c in tool_calls
            if c["name"] == case["expected_tool"]
        ).lower()
        if not all(k.lower() in seen for k in wanted):
            return False
    return True


def _row(case: dict) -> dict:
    return {
        "query": case["query"],
        "expected_tool": case["expected_tool"],
        "expected_params": case["expected_params"],
        "difficulty": case["difficulty"],
        "tool_correct": False,
        "params_correct": False,
    }


async def _run_case(i: int, case: dict, agent) -> dict:
    print(f"[{i + 1}/{len(test_cases)}] {case['query'][:60]}...")
    try:
        response = await agent.ainvoke(
            {"messages": [{"role": "user", "content": case["query"]}]},
            context=RecordContext(RECORD_ID, tuple(case["attachments"])),
            config={"recursion_limit": RECURSION_LIMIT},
        )
    except Exception as exc:
        # One failed run should not lose the other, billed, results.
        return {**_row(case), "error": error_text(exc)}

    tool_calls = [
        call
        for msg in response["messages"]
        if isinstance(msg, AIMessage)
        for call in msg.tool_calls
    ]
    first = tool_calls[0] if tool_calls else None
    tool_correct = (first and first["name"]) == case["expected_tool"]
    return {
        **_row(case),
        "actual_tool": first and first["name"],
        "tool_correct": tool_correct,
        "actual_params": first and first["args"],
        "params_correct": tool_correct and _params_correct(case, tool_calls),
        "response": response["messages"][-1].content,
    }


async def main() -> None:
    agent_module.search_record, agent_module.add_document = (
        _search_record,
        _add_document,
    )
    agent = build_agent()

    results = [await _run_case(i, case, agent) for i, case in enumerate(test_cases)]
    print(f"\nCompleted {len(results)}/{len(test_cases)} test cases.")

    by_difficulty = defaultdict(list)
    for r in results:
        by_difficulty[r["difficulty"]].append(r)
    for difficulty, rows in by_difficulty.items():
        tools = sum(r["tool_correct"] for r in rows)
        params = sum(r["params_correct"] for r in rows)
        print(f"  {difficulty}: tool {tools}/{len(rows)}, params {params}/{len(rows)}")

    (HERE / "tool_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), "utf-8", newline="\n"
    )


if __name__ == "__main__":
    load_dotenv(HERE.parent.parent / ".env")
    asyncio.run(main())
