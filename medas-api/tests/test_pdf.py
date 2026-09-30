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
    return load_pdf(DOCUMENTS / name, RECORD).chunks


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


def test_rejects_the_right_date_of_birth_under_another_surname():
    # Born the same day is not the same patient.
    with pytest.raises(Rejected, match="not this patient"):
        load_pdf(
            DOCUMENTS / "D04_prescription_gp_2026-08-18.pdf",
            {**RECORD, "name": "Mattia Rossi"},
        )


def test_the_text_is_the_files_own_without_the_identity_line():
    # What the upload's model check reads: an identity line naming the
    # patient on every document would answer its question for it.
    loaded = load_pdf(DOCUMENTS / "D02_letter_ent_clinic_2026-09-10.pdf", RECORD)

    assert "Smacchia" in loaded.text
    assert "Patient Mattia Smacchia (DOB" not in loaded.text


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


def test_contact_details_and_other_people_are_masked_but_the_patient_is_not():
    loaded = load_pdf(DOCUMENTS / "D02_letter_ent_clinic_2026-09-10.pdf", RECORD)
    text = "\n".join(c.page_content for c in loaded.chunks) + loaded.text

    assert "Smacchia" in loaded.text
    assert "1980" in loaded.text or "07/06/1980" in loaded.text
    assert "<" in text  # something was masked
    assert "@" not in text


def test_mask_pii_replaces_identifiers_and_keeps_dates_and_the_patient():
    from rag_pipeline.redact import mask_pii

    masked = mask_pii(
        "Mr Smacchia, seen by Dr Patel on 12/03/2026. Call 020 7946 0958 or "
        "a.patel@nhs.net. NHS number 943 476 5919.",
        RECORD,
    )

    assert "Smacchia" in masked
    assert "12/03/2026" in masked
    for leaked in ("Patel", "020 7946", "a.patel@nhs.net", "943 476"):
        assert leaked not in masked
