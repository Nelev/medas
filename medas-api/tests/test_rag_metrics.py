"""The RAG metrics' arithmetic and the edge cases that decide N/A vs 0.

The judge and the embeddings are fakes: what is tested is how their verdicts
become scores, not whether the verdicts are right.
"""

import json
from types import SimpleNamespace

import pytest

from dataset.eval.common import chunk_tail
from dataset.eval.rag_metrics import average_precision, cosine, ranked_contexts, score


def _passage(chunk_id: str) -> dict:
    return {"query": "q", "chunk_id": chunk_id, "text": chunk_id}


class FakeJudge:
    """Answers each metric's prompts from a fixed script.

    The claims to split the reply into, which of them are supported, which
    passages are useful and which facts were retrieved: each verification
    call is answered by finding its item in the prompt.
    """

    def __init__(self, claims, supported, relevancy, useful, facts):
        self.claims, self.supported = claims, supported
        self.relevancy, self.useful, self.facts = relevancy, useful, facts

    async def ainvoke(self, prompt: str):
        if prompt.startswith("Break this reply"):
            out = {"claims": self.claims}
        elif "Is this claim" in prompt:
            out = {"supported": any(f"Claim: {c}\n" in prompt for c in self.supported)}
        elif prompt.startswith("Here is a reply"):
            out = self.relevancy
        elif prompt.startswith("A patient asked a medical assistant"):
            out = {"useful": any(f"Passage:\n{t}\n" in prompt for t in self.useful)}
        else:
            fact = next(f for f in self.facts if f"convey this: {f}\n" in prompt)
            kind, attributed = self.facts[fact]
            out = {"kind": kind, "attributed": attributed}
        return SimpleNamespace(content=json.dumps(out))


class FakeEmbeddings:
    """The question and every generated question embed to the same vector."""

    async def aembed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _judge(**overrides) -> FakeJudge:
    script = {
        "claims": [
            {"claim": "on dupilumab", "kind": "record"},
            {"claim": "every 4 weeks", "kind": "record"},
            {"claim": "call 999 if worse", "kind": "general"},
        ],
        "supported": {"on dupilumab"},
        "relevancy": {"questions": ["a", "b", "c"], "noncommittal": False},
        "useful": {"pat_x:pdf:e155:p1:0"},
        "facts": {"dupilumab": ("record", True), "ask your GP": ("other", False)},
    }
    return FakeJudge(**{**script, **overrides})


ROW = {
    "question": "Which biologic am I on?",
    "message": "You are on dupilumab, every 4 weeks. Call 999 if worse.",
    "must_cite": ["D03"],
    "must_say": ["dupilumab", "ask your GP"],
    "cite_prefixes": ["pdf:e155"],
    "contexts": [
        _passage("pat_x:episode:01"),
        _passage("pat_x:pdf:e155:p1:0"),
        _passage("pat_x:episode:01"),  # returned again by a second search
    ],
}


def test_average_precision_rewards_ranking_relevant_first():
    assert average_precision([True, True, False]) == 1.0
    assert average_precision([False, True]) == 0.5
    assert average_precision([True, False, True]) == pytest.approx((1 + 2 / 3) / 2)


def test_average_precision_is_none_with_nothing_relevant():
    assert average_precision([False, False]) is None
    assert average_precision([]) is None


def test_cosine():
    assert cosine([1.0, 0.0], [2.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_chunk_tail_drops_the_patient():
    assert chunk_tail("pat_7f3c:allergy:00") == "allergy:00"
    assert chunk_tail("allergy:00") == "allergy:00"


def test_ranked_contexts_keeps_first_arrival_of_a_repeat():
    ids = [p["chunk_id"] for p in ranked_contexts(ROW)]
    assert ids == ["pat_x:episode:01", "pat_x:pdf:e155:p1:0"]


async def test_score_combines_the_verdicts():
    rag = await score(ROW, _judge(), FakeEmbeddings())

    assert rag["passages"] == 2
    # General advice is out of the ratio: 1 of 2 record claims supported.
    assert rag["faithfulness"] == 0.5
    assert rag["answer_relevancy"] == pytest.approx(1.0)
    # The one useful passage is at rank 2.
    assert rag["context_precision"] == 0.5
    # Guidance is out of the ratio: the one record fact was retrieved.
    assert rag["context_recall"] == 1.0
    assert rag["id_precision"] == 0.5
    assert rag["id_recall"] == 1.0


async def test_noncommittal_scores_zero_only_when_the_record_held_the_answer():
    judge = _judge(relevancy={"questions": ["a"], "noncommittal": True})

    answerable = await score(ROW, judge, FakeEmbeddings())
    refusal = await score(
        {**ROW, "must_cite": [], "cite_prefixes": []}, judge, FakeEmbeddings()
    )

    assert answerable["answer_relevancy"] == 0.0
    assert refusal["answer_relevancy"] == pytest.approx(1.0)


async def test_nothing_useful_retrieved_is_zero_when_answerable_else_none():
    judge = _judge(useful=set())

    answerable = await score(ROW, judge, FakeEmbeddings())
    refusal = await score(
        {**ROW, "must_cite": [], "cite_prefixes": []}, judge, FakeEmbeddings()
    )

    assert answerable["context_precision"] == 0.0
    assert refusal["context_precision"] is None
    assert refusal["id_precision"] is None
    assert refusal["id_recall"] is None


async def test_nothing_to_measure_is_none_not_zero():
    judge = _judge(claims=[{"claim": "hi", "kind": "general"}])
    rag = await score({**ROW, "must_say": [], "contexts": []}, judge, FakeEmbeddings())

    assert rag["faithfulness"] is None
    assert rag["context_recall"] is None
    assert rag["context_precision"] is None
    # A required source that no search returned is a miss, not N/A.
    assert rag["id_recall"] == 0.0


async def test_an_errored_run_is_not_scored():
    assert await score({"error": "boom"}, _judge(), FakeEmbeddings()) == {}
