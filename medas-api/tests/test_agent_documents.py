"""langchain_agent.documents: an attached PDF is checked, then stored, against one record."""

import pytest

import langchain_agent.documents as documents
import rag_pipeline.record as records
from langchain_agent.documents import add_document
from rag_pipeline.pdf import LoadedPdf
from schema import Attachment, Rejected

RECORD = {"id": "pat_1", "name": "Mattia", "dob": "1980-06-07"}
LOADED = LoadedPdf(chunks=["chunk 1", "chunk 2"], text="Dear Mattia")
LETTER = Attachment("letter.pdf", b"%PDF-1.4")


class FakeStore:
    def __init__(self):
        self.added = []

    async def aadd_documents(self, docs):
        self.added.extend(docs)


@pytest.fixture
def seen(monkeypatch) -> dict:
    """What load_pdf and averify were given."""
    seen = {}

    def fake_load_pdf(path, record):
        seen.update(name=path.name, bytes=path.read_bytes(), record=record)
        return LOADED

    async def fake_averify(text, record):
        seen["verified"] = (text, record)

    # Under find_record, so its id check is the real one.
    monkeypatch.setattr(records, "load_record", lambda: RECORD)
    monkeypatch.setattr(documents, "load_pdf", fake_load_pdf)
    monkeypatch.setattr(documents, "averify", fake_averify)
    return seen


@pytest.fixture
def store(monkeypatch) -> FakeStore:
    store = FakeStore()
    monkeypatch.setattr(documents, "get_vector_store", lambda: store)
    return store


async def test_a_document_that_passes_both_checks_is_stored(seen, store):
    assert await add_document(LETTER, "pat_1") == 2

    # The attachment's own name and bytes, checked against this record.
    assert seen == {
        "name": "letter.pdf",
        "bytes": b"%PDF-1.4",
        "record": RECORD,
        "verified": ("Dear Mattia", RECORD),
    }
    assert store.added == LOADED.chunks


async def test_a_file_load_pdf_refuses_is_not_sent_to_the_model(
    monkeypatch, seen, store
):
    def refuse(*_):
        raise Rejected("hidden text")

    monkeypatch.setattr(documents, "load_pdf", refuse)

    with pytest.raises(Rejected, match="hidden text"):
        await add_document(LETTER, "pat_1")
    assert "verified" not in seen
    assert store.added == []


async def test_a_document_the_model_refuses_stores_nothing(monkeypatch, seen, store):
    async def refuse(*_):
        raise Rejected("not a medical document")

    monkeypatch.setattr(documents, "averify", refuse)

    with pytest.raises(Rejected, match="not a medical document"):
        await add_document(LETTER, "pat_1")
    assert store.added == []


async def test_a_patient_without_a_record_is_refused(seen, store):
    with pytest.raises(Rejected, match="no record"):
        await add_document(LETTER, "pat_2")
    assert seen == {}
    assert store.added == []
