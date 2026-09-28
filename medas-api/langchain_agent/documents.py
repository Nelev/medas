"""Adding a PDF the patient attached to their record, for the agent's tool.

No database of its own: the file comes with the request, in the run's
context, and lives no longer than the run.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from rag_pipeline.pdf import LoadedPdf, Rejected, load_pdf
from rag_pipeline.record import find_record
from rag_pipeline.vector_store import get_vector_store
from rag_pipeline.verify import averify

__all__ = ["Attachment", "add_document"]


@dataclass(frozen=True)
class Attachment:
    """A PDF sent with the question. `name` is what the model calls it by."""

    name: str
    content: bytes


def _load(attachment: Attachment, record: dict) -> LoadedPdf:
    # load_pdf reads a path. A directory rather than a NamedTemporaryFile,
    # which Windows will not let pdfplumber reopen; the name is kept because
    # it goes into every chunk.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(attachment.name).name
        path.write_bytes(attachment.content)
        return load_pdf(path, record)


async def add_document(attachment: Attachment, record_id: str) -> int:
    """Verify `attachment` belongs in `record_id`'s record, then embed and
    store its chunks. Returns how many were written.

    Raises Rejected when it does not belong -- load_pdf's checks, then the
    model's, which only runs if they pass -- so a refused file stores nothing
    and costs no embeddings.
    """
    record = find_record(record_id)
    if record is None:
        raise Rejected("no record")
    # The disk write and the PDF parse off the event loop.
    loaded = await run_in_threadpool(_load, attachment, record)
    await averify(loaded.text, record)

    await get_vector_store().aadd_documents(loaded.chunks)
    return len(loaded.chunks)
