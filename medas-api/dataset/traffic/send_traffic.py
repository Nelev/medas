"""Send the questions in queries.yaml to the agent, traced, for TraceScan.

    uv run python -m dataset.traffic.send_traffic [--repeat N] [--kinds normal,edge]
        [--limit N] [--concurrency N] [--seed N] [--timeout SECONDS]

Each question is one agent run as the seeded patient, made in process through
`langchain_agent.agent.answer`, the function `/ask` calls: the same agent,
tools and retrieval, and the same trace, without HTTP or a Clerk session. No
conversation is stored. Tracing must be on (OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
and OTEL_EXPORTER_OTLP_TRACES_HEADERS in .env, see the root README), or the
script refuses to run, since nothing would come of it.

Billable: one agent run per question, with its model calls and searches.
Needs the database up and indexed (see dataset/README.md).

What a run prints is ids, kinds, outcomes and timings: never a question's
answer, which is about the patient's record.
"""

import argparse
import asyncio
import json
import random
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).parent
API_DIR = HERE.parent.parent
QUERIES_PATH = HERE / "queries.yaml"

KINDS = ("normal", "edge", "adversarial")
# A question still running after this long is abandoned and counted as a
# timeout: the agent's search loop has no bound of its own (a known gap).
TIMEOUT_S = 180.0
CONCURRENCY = 3

ANSWERED = "answered"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class Query:
    id: str
    kind: str
    question: str


@dataclass(frozen=True)
class Outcome:
    id: str
    kind: str
    # ANSWERED, TIMEOUT, or the type name of the exception the run raised.
    result: str
    seconds: float


def load_queries(path: Path = QUERIES_PATH) -> list[Query]:
    """The questions in `path`, in file order. Raises ValueError on a malformed
    entry, an unknown kind or a repeated id."""
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path.name}: expected a list of questions")
    queries: list[Query] = []
    seen: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != {"id", "kind", "question"}:
            raise ValueError(f"{path.name}: entry {number} needs id, kind and question")
        query = Query(entry["id"], entry["kind"], entry["question"])
        if not all(isinstance(value, str) for value in vars(query).values()):
            raise ValueError(f"{path.name}: entry {number} must be all text")
        if query.kind not in KINDS:
            raise ValueError(f"{path.name}: {query.id} has unknown kind {query.kind}")
        if query.id in seen:
            raise ValueError(f"{path.name}: {query.id} appears twice")
        seen.add(query.id)
        queries.append(query)
    return queries


def plan(
    queries: Sequence[Query],
    *,
    kinds: Sequence[str] = KINDS,
    repeat: int = 1,
    limit: int | None = None,
    seed: int | None = None,
) -> list[Query]:
    """What a run sends: the questions of `kinds`, each `repeat` times,
    shuffled (the same order for the same seed), then cut to `limit`."""
    chosen = [query for query in queries if query.kind in kinds] * repeat
    random.Random(seed).shuffle(chosen)  # noqa: S311 - an order, not a secret
    return chosen if limit is None else chosen[:limit]


async def send(
    queries: Sequence[Query],
    ask: Callable[[str], Awaitable[object]],
    *,
    concurrency: int = CONCURRENCY,
    time_limit: float = TIMEOUT_S,
) -> list[Outcome]:
    """Ask every question, at most `concurrency` at a time, and say how each
    went, giving up on one after `time_limit` seconds. A failing question is
    recorded, never raised: the failures are what the traffic is for. The
    answers themselves are dropped."""
    gate = asyncio.Semaphore(concurrency)

    async def one(query: Query) -> Outcome:
        async with gate:
            started = time.monotonic()
            try:
                await asyncio.wait_for(ask(query.question), time_limit)
                result = ANSWERED
            except TimeoutError:
                result = TIMEOUT
            except Exception as exc:
                result = type(exc).__name__
            seconds = round(time.monotonic() - started, 1)
            print(f"{query.id:<4} {query.kind:<12} {result:<24} {seconds:>6.1f} s")
            return Outcome(query.id, query.kind, result, seconds)

    return list(await asyncio.gather(*(one(query) for query in queries)))


def summary(outcomes: Sequence[Outcome]) -> str:
    """One line per kind and result, then the total."""
    counts = Counter((outcome.kind, outcome.result) for outcome in outcomes)
    lines = [
        f"{kind:<12} {result:<24} {counts[kind, result]}"
        for kind in KINDS
        for result in sorted({r for k, r in counts if k == kind})
    ]
    answered = sum(outcome.result == ANSWERED for outcome in outcomes)
    lines.append(f"{answered} of {len(outcomes)} answered")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repeat", type=int, default=1, help="send each question N times"
    )
    parser.add_argument(
        "--kinds",
        default=",".join(KINDS),
        help="comma-separated kinds to send (default: all)",
    )
    parser.add_argument("--limit", type=int, help="send at most N questions")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--seed", type=int, help="shuffle the same way every time")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = parser.parse_args(argv)
    args.kinds = [kind.strip() for kind in args.kinds.split(",") if kind.strip()]
    if unknown := set(args.kinds) - set(KINDS):
        parser.error(f"unknown kinds: {', '.join(sorted(unknown))}")
    if args.repeat < 1 or args.concurrency < 1:
        parser.error("--repeat and --concurrency must be at least 1")
    return args


async def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    queries = plan(
        load_queries(),
        kinds=args.kinds,
        repeat=args.repeat,
        limit=args.limit,
        seed=args.seed,
    )

    # The OTLP exporter reads its headers (the collector's token) from the
    # process environment, not from the settings classes.
    load_dotenv(API_DIR / ".env")

    # Imported here: importing the agent must not need the environment.
    from database.database import dispose_engine, init_engine
    from langchain_agent.agent import answer
    from rag_pipeline.record import MEDICAL_HISTORY_PATH
    from rag_pipeline.vector_store import init_vector_store
    from tracing import active_handler, start_tracing, stop_tracing, traced

    start_tracing()
    handler = active_handler()
    if handler is None:
        raise SystemExit(
            "Tracing is off: set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT (and its "
            "headers) in .env, or no trace would reach the collector."
        )

    record_id = json.loads(MEDICAL_HISTORY_PATH.read_text(encoding="utf-8"))["id"]

    async def ask(question: str) -> object:
        return await answer(
            [{"role": "user", "content": question}], record_id=record_id
        )

    engine = init_engine()
    try:
        await init_vector_store(engine)
        print(f"Sending {len(queries)} questions, {args.concurrency} at a time")
        # Every task gather starts copies this context, handler included.
        with traced(handler):
            outcomes = await send(
                queries, ask, concurrency=args.concurrency, time_limit=args.timeout
            )
    finally:
        # Sends the spans still waiting in the batch before the process ends.
        stop_tracing()
        await dispose_engine()

    print(summary(outcomes))


if __name__ == "__main__":
    asyncio.run(main())
