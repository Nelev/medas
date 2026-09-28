"""Index the PDFs in a patient's file, refusing any that do not belong there."""

import hashlib
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import pdfplumber
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_pipeline.chunks import patient_prefix
from rag_pipeline.vector_store import get_vector_store

__all__ = ["LoadedPdf", "Rejected", "aindex_pdfs", "doc_prefix", "load_pdf"]

# Text smaller than this, or white, is invisible to a reader but still in the
# text layer: the usual place to hide an instruction to the model.
_MIN_VISIBLE_SIZE = 3
_WHITE = {(1,), (1, 1, 1), (0, 0, 0, 0)}

# A page of a letter is about 1,000 characters, so most pages stay whole; a
# denser one is split rather than averaged into one vague vector.
_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=100, add_start_index=True
)


class Rejected(Exception):
    """The document is not indexed; the message says why."""


class LoadedPdf(NamedTuple):
    chunks: list[Document]
    # The file's own text, without the identity line each chunk carries: what
    # a reader of the document, the upload's model check among them, sees.
    text: str


def _has_hidden_text(path: Path) -> bool:
    # Read with pdfplumber directly: the loader keeps each page's text, not
    # the size and colour of its characters.
    with pdfplumber.open(path) as pdf:
        return any(
            c["size"] < _MIN_VISIBLE_SIZE
            or tuple(c["non_stroking_color"] or ()) in _WHITE
            for page in pdf.pages
            for c in page.chars
        )


def doc_prefix(path: Path) -> str:
    """The part of a chunk id, after the patient id, that names this file.

    A hash of the bytes, so the same file under another name produces the
    same ids and the upsert replaces rather than duplicates it.
    """
    return f"pdf:{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}"


def load_pdf(path: Path, record: dict[str, Any]) -> LoadedPdf:
    """The chunks and text of `path`, which must belong to `record`'s patient.

    Belonging means the patient's date of birth and surname are both in the
    text. A name alone is not enough -- a namesake's letter carries it too --
    nor is the date of birth alone, which a stranger born the same day
    shares. A document with no date of birth at all (a leaflet, an insurance
    renewal) is not part of a medical record, so the same check keeps
    unrelated files out. The surname only, since letters often shorten the
    first name to an initial.

    Raises Rejected, so a refused file contributes no chunks at all.
    """
    try:
        pages = PDFPlumberLoader(path).load()
    except Exception as exc:
        # Encrypted, truncated, not a PDF: nothing here can be vouched for.
        raise Rejected("unreadable") from exc
    text = "\n".join(page.page_content for page in pages)
    if not text.strip():
        raise Rejected("no text layer")
    if _has_hidden_text(path):
        raise Rejected("hidden text")

    # ISO, and the UK day-first form the letters use. Any other form (US
    # order, "7 June 1980") is read as not this patient: a miss, never a match.
    dob = record["dob"]
    if dob not in text and f"{date.fromisoformat(dob):%d/%m/%Y}" not in text:
        raise Rejected("not this patient")
    if record["name"].split()[-1].casefold() not in text.casefold():
        raise Rejected("not this patient")

    patient_id = record["id"]
    prefix = doc_prefix(path)
    chunks = []
    for split in _SPLITTER.split_documents(pages):
        n = split.metadata["page"] + 1  # the loader counts pages from 0
        chunks.append(
            Document(
                id=f"{patient_id}:{prefix}:p{n}:{split.metadata['start_index']}",
                # The identity and source lines go on after splitting, so
                # every chunk carries them, not only a page's first.
                page_content=(
                    f"{patient_prefix(record)}. "
                    f"Document {path.name}, page {n}.\n{split.page_content}"
                ),
                metadata={
                    "patient_id": patient_id,
                    "kind": "document",
                    "source_file": path.name,
                    "page": n,
                },
            )
        )
    return LoadedPdf(chunks, text)


async def aindex_pdfs(paths: Iterable[Path], record: dict[str, Any]) -> int:
    """Embed and store the chunks of every PDF in `paths` that belongs to
    `record`, through the shared store, so they are embedded with the same
    model the search uses. Returns how many chunks were written. A refused
    file is printed with its reason; the rest are still indexed."""
    # Keyed on the id, so a copy of a file already seen is embedded once.
    docs: dict[str, Document] = {}
    for path in paths:
        try:
            docs.update((doc.id, doc) for doc in load_pdf(path, record).chunks)
        except Rejected as exc:
            print(f"Skipped {path.name}: {exc}")
    if docs:
        await get_vector_store().aadd_documents(list(docs.values()))
    return len(docs)
