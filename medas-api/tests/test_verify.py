"""rag_pipeline.verify: the model's verdict decides, and doubt refuses."""

from types import SimpleNamespace

import pytest

from rag_pipeline import verify
from rag_pipeline.pdf import Rejected
from rag_pipeline.verify import averify

RECORD = {"name": "Mattia Smacchia", "dob": "1980-06-07", "sex": "male"}


def model_replies(monkeypatch, content: str) -> list:
    """Stand in for the model with a fixed reply. Returns the prompts."""
    prompts = []

    class FakeModel:
        async def ainvoke(self, messages):
            prompts.append(messages)
            return SimpleNamespace(content=content)

    monkeypatch.setattr(verify, "_model", FakeModel)
    return prompts


async def test_a_medical_document_about_the_patient_passes(monkeypatch):
    prompts = model_replies(
        monkeypatch, '{"medical": true, "about_patient": true, "reason": "GP"}'
    )

    await averify("Dear Mr Smacchia", RECORD)

    # Told whose record it is, and given the document.
    human = prompts[0][1][1]
    assert "Patient Mattia Smacchia (DOB 1980-06-07, male)" in human
    assert "Dear Mr Smacchia" in human


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ('{"medical": false, "about_patient": true}', "not a medical document"),
        ('{"medical": true, "about_patient": false}', "not about this patient"),
        ("I think it is medical", "could not be verified"),
        ('{"medical": true}', "could not be verified"),
        # A string is not a yes.
        ('{"medical": "true", "about_patient": true}', "not a medical document"),
    ],
)
async def test_anything_but_a_clear_yes_is_refused(monkeypatch, content, reason):
    model_replies(monkeypatch, content)

    with pytest.raises(Rejected, match=reason):
        await averify("text", RECORD)


async def test_only_the_start_of_a_long_document_is_sent(monkeypatch):
    prompts = model_replies(monkeypatch, '{"medical": true, "about_patient": true}')

    await averify("x" * 10_000, RECORD)

    assert prompts[0][1][1].count("x") == 4000
