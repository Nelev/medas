"""The traffic generator: the question file, what a run sends, and how it
records each outcome. No database, no model: `send` takes the asker."""

import asyncio

import pytest

from dataset.traffic.send_traffic import (
    ANSWERED,
    KINDS,
    TIMEOUT,
    Outcome,
    Query,
    load_queries,
    parse_args,
    plan,
    send,
    summary,
)


def test_the_question_file_has_every_kind_and_unique_ids():
    queries = load_queries()

    assert {query.kind for query in queries} == set(KINDS)
    assert len({query.id for query in queries}) == len(queries)


@pytest.mark.parametrize(
    "text",
    [
        "id: N01",
        "- id: N01\n  kind: normal",
        "- id: N01\n  kind: weird\n  question: hi",
        "- id: N01\n  kind: normal\n  question: hi\n- id: N01\n  kind: edge\n  question: ho",
        "- id: N01\n  kind: normal\n  question: 3",
    ],
)
def test_a_malformed_question_file_is_refused(tmp_path, text):
    path = tmp_path / "queries.yaml"
    path.write_text(text)

    with pytest.raises(ValueError):
        load_queries(path)


QUERIES = [
    Query("N01", "normal", "a"),
    Query("E01", "edge", "b"),
    Query("A01", "adversarial", "c"),
]


def test_a_plan_keeps_the_kinds_asked_for_repeats_and_cuts():
    sent = plan(QUERIES, kinds=["normal", "edge"], repeat=3, seed=1)

    assert sorted(query.id for query in sent) == ["E01"] * 3 + ["N01"] * 3
    assert plan(QUERIES, kinds=["normal", "edge"], repeat=3, seed=1) == sent
    assert len(plan(QUERIES, repeat=3, limit=4, seed=1)) == 4


def test_a_plan_can_be_cut_to_some_questions():
    sent = plan(QUERIES, ids=["N01", "A01"], repeat=2, seed=1)

    assert sorted(query.id for query in sent) == ["A01", "A01", "N01", "N01"]


def test_ids_are_read_as_a_list():
    assert parse_args(["--ids", "N01, E03"]).ids == ["N01", "E03"]
    assert parse_args([]).ids is None


async def test_every_question_gets_an_outcome_and_none_is_raised():
    async def ask(question):
        if question == "b":
            raise RuntimeError("the model is down")
        if question == "c":
            await asyncio.sleep(1)
        return "an answer"

    outcomes = await send(QUERIES, ask, concurrency=2, time_limit=0.05)

    assert [(o.id, o.result) for o in outcomes] == [
        ("N01", ANSWERED),
        ("E01", "RuntimeError"),
        ("A01", TIMEOUT),
    ]


async def test_no_more_than_the_concurrency_runs_at_once():
    running = peak = 0

    async def ask(question):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    await send(QUERIES * 3, ask, concurrency=2)

    assert peak == 2


async def test_nothing_a_run_prints_holds_a_question_or_an_answer(capsys):
    async def ask(question):
        return "Your record says penicillin"

    outcomes = await send([Query("N01", "normal", "What am I allergic to?")], ask)
    printed = capsys.readouterr().out + summary(outcomes)

    assert "allergic" not in printed and "penicillin" not in printed


def test_the_summary_counts_each_result_per_kind():
    text = summary(
        [
            Outcome("N01", "normal", ANSWERED, 1.0),
            Outcome("N02", "normal", ANSWERED, 1.0),
            Outcome("A01", "adversarial", TIMEOUT, 9.0),
        ]
    )

    assert "normal       answered                 2" in text
    assert "adversarial  timeout                  1" in text
    assert text.endswith("2 of 3 answered")


def test_an_unknown_kind_is_refused():
    with pytest.raises(SystemExit):
        parse_args(["--kinds", "normal,nonsense"])
