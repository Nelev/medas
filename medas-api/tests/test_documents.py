"""controller.documents: an upload becomes chunks in the user's record."""

import io
import uuid

import pytest
from fastapi import UploadFile

from controller import documents
from controller.documents import RecordNotFound, index_upload
from rag_pipeline.pdf import LoadedPdf, Rejected

USER_ID = uuid.uuid4()
RECORD = {"id": f"pat_{USER_ID}", "name": "Mattia", "dob": "1980-06-07"}
LOADED = LoadedPdf(chunks=["chunk 1", "chunk 2"], text="Dear Mattia")


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
    monkeypatch.setattr(documents, "load_pdf", lambda *_: LOADED)
    return store


def verify_with(monkeypatch, verdict=None) -> list:
    """Stand in for the model check: pass, or raise `verdict`. Returns the
    texts it was asked about."""
    seen = []

    async def fake_averify(text, record):
        seen.append((text, record))
        if verdict:
            raise verdict

    monkeypatch.setattr(documents, "averify", fake_averify)
    return seen


def upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="letter.pdf")


async def test_the_chunks_are_added_to_the_store(monkeypatch, store):
    seen = {}

    def fake_load_pdf(path, record):
        seen.update(name=path.name, bytes=path.read_bytes(), record=record)
        return LOADED

    monkeypatch.setattr(documents, "load_pdf", fake_load_pdf)
    verify_with(monkeypatch)

    assert await index_upload(USER_ID, upload()) == 2
    assert store.added == LOADED.chunks
    # The upload's own name and bytes, checked against this user's record.
    assert seen == {"name": "letter.pdf", "bytes": b"%PDF-1.4", "record": RECORD}


async def test_a_user_without_a_record_stores_nothing(monkeypatch, store):
    monkeypatch.setattr(documents, "load_pdf", lambda *_: pytest.fail("loaded"))

    with pytest.raises(RecordNotFound):
        await index_upload(uuid.uuid4(), upload())
    assert store.added == []


async def test_the_document_text_is_verified(monkeypatch, store):
    seen = verify_with(monkeypatch)

    await index_upload(USER_ID, upload())

    assert seen == [("Dear Mattia", RECORD)]


async def test_a_document_the_model_refuses_stores_nothing(monkeypatch, store):
    verify_with(monkeypatch, Rejected("not a medical document"))

    with pytest.raises(Rejected, match="not a medical document"):
        await index_upload(USER_ID, upload())
    assert store.added == []
