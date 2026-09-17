"""Flatten a patient record into standalone chunks ready for embedding."""

from collections.abc import Iterator
from typing import Any, TypedDict


class Chunk(TypedDict):
    """One embeddable unit: the text, plus what you need to filter and cite."""

    chunk_id: str
    kind: str
    text: str
    metadata: dict[str, Any]


def _patient_prefix(doc: dict[str, Any]) -> str:
    """Identity line repeated on every chunk.

    Retrieval hands the model one chunk with no surrounding document, so a
    chunk that says "Reaction: rash" without naming the patient or the
    substance is unusable on its own.
    """
    return f"Patient {doc['name']} (DOB {doc['dob']}, {doc['sex']})"


def _episode_text(doc: dict[str, Any], ep: dict[str, Any]) -> str:
    return (
        f"{_patient_prefix(doc)}. "
        f"Clinical episode on {ep['date']} "
        f"({ep['type'].replace('_', ' ')}, {ep['setting'].replace('_', ' ')}). "
        f"{ep['description']}"
    )


def _allergy_text(doc: dict[str, Any], al: dict[str, Any]) -> str:
    return (
        f"{_patient_prefix(doc)}. "
        f"Allergy: {al['substance']} ({al['type'].replace('_', ' ')}). "
        f"Reaction: {al['reaction']}. "
        f"Severity: {al['severity']}. "
        f"Status: {al['status'].replace('_', ' ')}, onset {al['onset_date']}."
    )


def _medication_text(doc: dict[str, Any], med: dict[str, Any]) -> str:
    return (
        f"{_patient_prefix(doc)}. "
        f"Current medication: {med['name']} {med['strength']}, {med['form']}. "
        f"Dose: {med['dose']}. "
        f"Indication: {med['indication']}. Started {med['started']}."
    )


def _pathology_text(doc: dict[str, Any], path: dict[str, Any]) -> str:
    return (
        f"{_patient_prefix(doc)}. "
        f"Diagnosis: {path['condition']} (ICD-10 {path['icd10']}), "
        f"{path['status']}, diagnosed {path['diagnosed']}. "
        f"{path['notes']}"
    )


def iter_chunks(doc: dict[str, Any]) -> Iterator[Chunk]:
    """Yield one chunk per clinical record.

    One embedding per record rather than one for the whole document: a single
    vector averaged over 21 unrelated facts matches everything weakly and
    nothing precisely.
    """
    patient_id = doc["id"]

    for ep in doc.get("episodes", []):
        yield Chunk(
            chunk_id=f"{patient_id}:episode:{ep['episode_id']}",
            kind="episode",
            text=_episode_text(doc, ep),
            metadata={
                "patient_id": patient_id,
                "date": ep["date"],
                "type": ep["type"],
                "setting": ep["setting"],
            },
        )

    for i, al in enumerate(doc.get("allergies", [])):
        yield Chunk(
            chunk_id=f"{patient_id}:allergy:{i:02d}",
            kind="allergy",
            text=_allergy_text(doc, al),
            metadata={
                "patient_id": patient_id,
                "substance": al["substance"],
                "severity": al["severity"],
                "status": al["status"],
            },
        )

    for i, med in enumerate(doc.get("current_medication", [])):
        yield Chunk(
            chunk_id=f"{patient_id}:medication:{i:02d}",
            kind="medication",
            text=_medication_text(doc, med),
            metadata={
                "patient_id": patient_id,
                "name": med["name"],
                "started": med["started"],
            },
        )

    for path in doc.get("pathologies", []):
        yield Chunk(
            chunk_id=f"{patient_id}:pathology:{path['icd10']}",
            kind="pathology",
            text=_pathology_text(doc, path),
            metadata={
                "patient_id": patient_id,
                "icd10": path["icd10"],
                "status": path["status"],
                "diagnosed": path["diagnosed"],
            },
        )
