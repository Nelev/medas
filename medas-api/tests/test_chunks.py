"""Tests for the chunker that flattens a patient record for embedding."""

import copy

import pytest

from rag_pipeline.chunks import iter_chunks

# A hand-built record rather than medical_history.json: the fixture has to
# stay fixed while the real corpus is free to change, and some cases below
# need shapes the real file does not contain.
PATIENT_ID = "pat_test_0001"


@pytest.fixture
def doc() -> dict:
    return copy.deepcopy(
        {
            "id": PATIENT_ID,
            "name": "Jane Doe",
            "dob": "1980-06-07",
            "sex": "female",
            "episodes": [
                {
                    "episode_id": "ep_01",
                    "date": "1986-11-02",
                    "type": "diagnosis",
                    "setting": "primary_care",
                    "description": "First presentation with wheeze.",
                },
                {
                    "episode_id": "ep_02",
                    "date": "2019-01-22",
                    "type": "hospital_admission",
                    "setting": "inpatient",
                    "description": "Severe exacerbation, four-day admission.",
                },
            ],
            "allergies": [
                {
                    "substance": "Amoxicillin",
                    "type": "drug_allergy",
                    "reaction": "Urticarial rash",
                    "severity": "moderate",
                    "status": "active_confirmed",
                    "onset_date": "1998-06-20",
                }
            ],
            "current_medication": [
                {
                    "name": "Salbutamol",
                    "strength": "100 micrograms",
                    "form": "inhaler",
                    "dose": "Two puffs as required",
                    "indication": "Asthma",
                    "started": "1986-11-02",
                }
            ],
            "pathologies": [
                {
                    "condition": "Asthma",
                    "icd10": "J45.0",
                    "status": "active",
                    "diagnosed": "1986-11-02",
                    "notes": "Allergic, early onset.",
                }
            ],
        }
    )


def test_yields_one_chunk_per_clinical_record(doc):
    chunks = list(iter_chunks(doc))
    expected = (
        len(doc["episodes"])
        + len(doc["allergies"])
        + len(doc["current_medication"])
        + len(doc["pathologies"])
    )
    assert len(chunks) == expected


def test_chunk_kinds_cover_every_section(doc):
    kinds = [c["kind"] for c in iter_chunks(doc)]
    assert kinds == ["episode", "episode", "allergy", "medication", "pathology"]


def test_chunk_ids_are_unique(doc):
    # Chroma upsert is keyed on the id: a collision silently replaces the
    # earlier record instead of erroring, so the corpus loses a chunk.
    ids = [c["chunk_id"] for c in iter_chunks(doc)]
    assert len(ids) == len(set(ids))


def test_chunk_ids_are_namespaced_by_patient(doc):
    for chunk in iter_chunks(doc):
        assert chunk["chunk_id"].startswith(f"{PATIENT_ID}:")


def test_every_chunk_names_the_patient(doc):
    # The module's premise: retrieval hands the model one chunk with no
    # surrounding document, so each has to identify its subject alone.
    for chunk in iter_chunks(doc):
        assert doc["name"] in chunk["text"]
        assert doc["dob"] in chunk["text"]
        assert doc["sex"] in chunk["text"]


def test_enumerated_codes_are_humanised_in_the_text(doc):
    # Underscored enum values read as tokens to an embedding model; the
    # chunker spells them out.
    episode = next(c for c in iter_chunks(doc) if c["chunk_id"].endswith("ep_02"))
    assert "hospital admission" in episode["text"]
    assert "hospital_admission" not in episode["text"]


def test_every_chunk_carries_the_patient_id_in_metadata(doc):
    for chunk in iter_chunks(doc):
        assert chunk["metadata"]["patient_id"] == PATIENT_ID


def test_metadata_values_are_chroma_scalars(doc):
    # Chroma rejects None and nested values in metadata. Catching it here
    # points at the offending source field; catching it at upsert does not.
    for chunk in iter_chunks(doc):
        for key, value in chunk["metadata"].items():
            assert isinstance(value, str | int | float | bool), (
                f"{chunk['chunk_id']} metadata[{key!r}] is {type(value).__name__}"
            )


def test_absent_sections_yield_no_chunks():
    # Sections are read with .get(), so a record with none is empty, not an
    # error. Identity fields are not -- see the next test.
    identity_only = {"id": "p", "name": "n", "dob": "1970-01-01", "sex": "male"}
    assert list(iter_chunks(identity_only)) == []


def test_missing_patient_id_fails_loudly():
    with pytest.raises(KeyError):
        list(iter_chunks({"name": "n", "dob": "1970-01-01", "sex": "male"}))


def test_missing_field_within_a_record_fails_loudly(doc):
    del doc["episodes"][0]["description"]
    with pytest.raises(KeyError):
        list(iter_chunks(doc))


@pytest.mark.xfail(
    strict=True,
    reason="Pathology ids derive from icd10 and episode ids from episode_id, "
    "so duplicates in the source collide and the later record silently "
    "overwrites the earlier one on upsert. Pending a decision: raise, or "
    "disambiguate with an enumerate() index as allergies and medications do.",
)
def test_duplicate_icd10_does_not_collide(doc):
    doc["pathologies"].append(
        {
            "condition": "Asthma, unspecified",
            "icd10": "J45.0",
            "status": "resolved",
            "diagnosed": "1990-01-01",
            "notes": "Duplicate code, different record.",
        }
    )
    ids = [c["chunk_id"] for c in iter_chunks(doc)]
    assert len(ids) == len(set(ids))
