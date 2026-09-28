"""controller.documents: an upload becomes chunks in the user's record."""

import io
import uuid

import pytest
from fastapi import UploadFile

from controller import documents
from controller.documents import RecordNotFound, index_upload

USER_ID = uuid.uuid4()
RECORD = {"id": f"pat_{USER_ID}", "name": "Mattia", "dob": "1980-06-07"}


class FakeStore:
    def __init__(self):
        self.added = []

    async def aadd_documents(self, docs):
        self.added.extend(docs)


@pytest.fixture
def store(monkeypatch) -> FakeStore:
    store = FakeStore()
    monkeypatch.setattr(documents, "load_record", lambda: RECORD)
    monkeypatch.setattr(documents, "get_vector_store", lambda: store)
    return store


def upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="letter.pdf")


async def test_the_chunks_are_added_to_the_store(monkeypatch, store):
    seen = {}

    def fake_load_pdf(path, record):
        seen.update(name=path.name, bytes=path.read_bytes(), record=record)
        return ["chunk 1", "chunk 2"]

    monkeypatch.setattr(documents, "load_pdf", fake_load_pdf)

    assert await index_upload(USER_ID, upload()) == 2
    assert store.added == ["chunk 1", "chunk 2"]
    # The upload's own name and bytes, checked against this user's record.
    assert seen == {"name": "letter.pdf", "bytes": b"%PDF-1.4", "record": RECORD}


async def test_a_user_without_a_record_stores_nothing(monkeypatch, store):
    monkeypatch.setattr(documents, "load_pdf", lambda *_: pytest.fail("loaded"))

    with pytest.raises(RecordNotFound):
        await index_upload(uuid.uuid4(), upload())
    assert store.added == []
