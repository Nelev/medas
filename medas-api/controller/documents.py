"""Indexing a PDF the user uploads into their record's vector store.

The same path the ingest script takes for dataset/documents/ -- load_pdf checks
the file belongs to the record and chunks it, and the shared store embeds the
chunks with the model the search uses -- plus the model check in
rag_pipeline/verify.py, which the ingest script, over its own curated files,
does not pay for.
"""

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from agent.patient import record_id
from controller.conversation import NotFound
from langchain_agent.rag import load_record
from rag_pipeline.pdf import LoadedPdf, load_pdf
from rag_pipeline.vector_store import get_vector_store
from rag_pipeline.verify import averify

__all__ = ["RecordNotFound", "index_upload"]


class RecordNotFound(NotFound):
    """The signed-in user has no medical record to add a document to."""

    detail = "Record not found"


def _load_upload(file: UploadFile, record: dict[str, Any]) -> LoadedPdf:
    # load_pdf reads a path, not a stream. A directory rather than a
    # NamedTemporaryFile, which Windows will not let pdfplumber reopen; the
    # upload's own name is kept because it goes into every chunk. Copied from
    # the upload's own spool rather than read into memory first.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(file.filename or "upload.pdf").name
        with path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        return load_pdf(path, record)


async def index_upload(user_id: uuid.UUID, file: UploadFile) -> int:
    """Embed and store the chunks of `file`. Returns how many were written.

    Raises Rejected (from load_pdf or averify) when the file does not belong to the
    record, so a refused upload stores nothing.
    """
    # One seeded record for now: any other user has none to upload into.
    record = load_record()
    if record["id"] != record_id(user_id):
        raise RecordNotFound

    # Blocking work -- the copy to disk and the PDF parse -- off the event
    # loop, so other requests are not held up behind it.
    chunks, text = await run_in_threadpool(_load_upload, file, record)
    # Before the store write, so a refused document costs no embeddings.
    await averify(text, record)

    await get_vector_store().aadd_documents(chunks)
    return len(chunks)
