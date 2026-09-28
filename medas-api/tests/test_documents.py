"""controller.documents: an upload is handed to the agent to verify and store,
as turns in a conversation."""

import io
import uuid

import pytest
from fastapi import UploadFile

import rag_pipeline.record as records
from controller import documents
from controller.documents import RecordNotFound, index_upload
from langchain_agent.documents import Attachment

USER_ID = uuid.uuid4()
CONVERSATION_ID = uuid.uuid4()
RECORD = {"id": f"pat_{USER_ID}", "name": "Mattia", "dob": "1980-06-07"}


@pytest.fixture(autouse=True)
def record(monkeypatch):
    # Under find_record, so its id check is the real one.
    monkeypatch.setattr(records, "load_record", lambda: RECORD)


class Session:
    """Nothing is read through it here: the writes are stubbed."""

    async def commit(self) -> None:
        pass


@pytest.fixture
def calls(monkeypatch) -> list:
    """Stand in for the conversation helpers. Returns what each was given."""
    made = []

    async def fake_write(session, user_id, name, role, text, conversation_id):
        made.append(("write", role, text))
        return CONVERSATION_ID, [{"role": role, "text": text}]

    async def fake_answer(session, conversation_id, user_id, turns, attachments):
        made.append(("answer", turns, attachments))
        return {"role": "assistant", "text": "Added."}

    monkeypatch.setattr(documents, "write_user_turn", fake_write)
    monkeypatch.setattr(documents, "answer_and_store", fake_answer)
    return made


def upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="letter.pdf")


async def test_the_agent_is_asked_to_add_the_upload(calls):
    assert await index_upload(Session(), USER_ID, None, upload(), None) == (
        CONVERSATION_ID,
        [
            {"role": "user", "text": "upload file requested: letter.pdf"},
            {"role": "assistant", "text": "Added."},
        ],
    )
    (_, (_, turns, attachments)) = calls
    assert "letter.pdf" in turns[-1]["content"]
    # The upload's own name and bytes.
    assert attachments == [Attachment("letter.pdf", b"%PDF-1.4")]


async def test_a_user_without_a_record_never_reaches_the_agent(calls):
    with pytest.raises(RecordNotFound):
        await index_upload(Session(), uuid.uuid4(), None, upload(), None)
    assert calls == []
