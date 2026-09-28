"""Tests for the PDF gate, over the committed synthetic documents."""

from pathlib import Path

import pytest

from rag_pipeline import pdf
from rag_pipeline.pdf import Rejected, aindex_pdfs, load_pdf

DOCUMENTS = Path(__file__).parent.parent / "dataset" / "documents"

# The date of birth is what the documents are matched on; the rest only has
# to be enough for the identity line.
RECORD = {
    "id": "pat_test_0001",
    "name": "Mattia Smacchia",
    "dob": "1980-06-07",
    "sex": "male",
}


def _chunks(name: str) -> list:
    return load_pdf(DOCUMENTS / name, RECORD)


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("D09_scanned_discharge_summary_2019-01-26.pdf", "no text layer"),
        ("D10_misfiled_namesake_cardiology_2026-10-19.pdf", "not this patient"),
        ("D11_leaflet_inhaler_with_hidden_injection.pdf", "hidden text"),
        ("D12_unrelated_motor_insurance_renewal.pdf", "not this patient"),
        ("D15_encrypted_prescription.pdf", "unreadable"),
        ("D16_truncated_corrupt.pdf", "unreadable"),
    ],
)
def test_rejects(name, reason):
    with pytest.raises(Rejected, match=reason):
        _chunks(name)


def test_chunks_carry_identity_source_and_metadata():
    chunks = _chunks("D02_letter_ent_clinic_2026-09-10.pdf")

    assert [c.metadata["page"] for c in chunks] == [1, 2]
    # Page 2 has no patient block of its own; the prefix is what ties it to
    # the patient once it is retrieved alone.
    assert chunks[1].page_content.startswith("Patient Mattia Smacchia (DOB 1980-06-07")
    assert "D02_letter_ent_clinic_2026-09-10.pdf, page 2" in chunks[1].page_content
    assert "dupilumab" in chunks[1].page_content
    # The store's metadata columns, which the search filters on.
    assert all(c.metadata["patient_id"] == RECORD["id"] for c in chunks)
    assert all(c.metadata["kind"] == "document" for c in chunks)


def test_a_long_page_is_split_and_every_chunk_is_prefixed():
    chunks = _chunks("D03_prescription_dupilumab_2026-09-22.pdf")

    assert len(chunks) > 1
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(c.page_content.startswith("Patient Mattia Smacchia") for c in chunks)


def test_the_same_file_under_another_name_gets_the_same_ids():
    original = _chunks("D04_prescription_gp_2026-08-18.pdf")
    duplicate = _chunks("D14_duplicate_of_D04_scan_export.pdf")

    assert [c.id for c in original] == [c.id for c in duplicate]


async def test_index_skips_refused_files_and_embeds_a_copy_once(monkeypatch):
    added = []

    class FakeStore:
        async def aadd_documents(self, docs):
            added.extend(docs)

    monkeypatch.setattr(pdf, "get_vector_store", FakeStore)
    names = [
        "D04_prescription_gp_2026-08-18.pdf",
        "D14_duplicate_of_D04_scan_export.pdf",
        "D12_unrelated_motor_insurance_renewal.pdf",
    ]

    written = await aindex_pdfs([DOCUMENTS / n for n in names], RECORD)

    assert written == len(added) == len(_chunks(names[0]))
