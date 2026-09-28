"""controller.documents: an upload is handed to the agent to verify and store."""

import io
import json
import uuid

import pytest
from fastapi import UploadFile

import rag_pipeline.record as records
from controller import documents
from controller.documents import DocumentNotStored, RecordNotFound, index_upload
from langchain_agent.documents import Attachment

USER_ID = uuid.uuid4()
RECORD = {"id": f"pat_{USER_ID}", "name": "Mattia", "dob": "1980-06-07"}


@pytest.fixture(autouse=True)
def record(monkeypatch):
    # Under find_record, so its id check is the real one.
    monkeypatch.setattr(records, "load_record", lambda: RECORD)


def agent_replies(monkeypatch, message: str, stored: dict) -> list:
    """Stand in for the agent run. Returns the calls made to it."""
    calls = []

    async def fake_answer(messages, *, record_id, attachments):
        calls.append((messages, record_id, attachments))
        return json.dumps({"message": message, "severity": None}), stored

    monkeypatch.setattr(documents, "answer", fake_answer)
    return calls


def upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="letter.pdf")


async def test_the_agent_is_asked_to_add_the_upload(monkeypatch):
    calls = agent_replies(monkeypatch, "Added.", {"letter.pdf": 2})

    assert await index_upload(USER_ID, upload()) == {
        "chunks": 2,
        "message": "Added.",
    }
    ((messages, record_id, attachments),) = calls
    assert "letter.pdf" in messages[-1]["content"]
    # The upload's own name and bytes, for this user's record.
    assert record_id == RECORD["id"]
    assert attachments == [Attachment("letter.pdf", b"%PDF-1.4")]


async def test_a_document_the_agent_did_not_store_is_rejected(monkeypatch):
    # Whatever the model says: stored is what the store tool wrote.
    agent_replies(monkeypatch, "That is not a medical document.", {})

    with pytest.raises(DocumentNotStored, match="not a medical document"):
        await index_upload(USER_ID, upload())


async def test_a_user_without_a_record_never_reaches_the_agent(monkeypatch):
    calls = agent_replies(monkeypatch, "Added.", {"letter.pdf": 2})

    with pytest.raises(RecordNotFound):
        await index_upload(uuid.uuid4(), upload())
    assert calls == []
