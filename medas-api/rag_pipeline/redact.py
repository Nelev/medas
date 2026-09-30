"""Mask the contact and identifier PII in a document's text before it is
chunked, embedded or shown to a model.

The patient's own name and date of birth are kept: they are in the record and
on every chunk's identity line already, and a question about "my" letters
needs them. Dates are kept too, since retrieval leans on them. What is masked
is what only the PDF carries: contact details, national identifiers, and
other people (clinicians, relatives).
"""

import re
from functools import lru_cache
from typing import Any

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

__all__ = ["mask_pii"]

# A fixed list rather than every entity Presidio knows: the small spaCy model
# tags conditions and drugs as ORGANIZATION or LOCATION ("Addison"), which
# would erase exactly what a question is about. URL is left out because it
# fires on the halves of an email address.
_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "UK_NHS",
    "UK_NINO",
    "IBAN_CODE",
    "CREDIT_CARD",
    "IP_ADDRESS",
]
# UK numbers score 0.4 with Presidio's phone recognizer; the NER entity
# (PERSON) scores well above it.
_MIN_SCORE = 0.4


# A bare name in a letter follows a title or is a full name. A one-word PERSON
# with neither is nearly always a term the model misread ("GORD", or Italian
# words in an English-only model): masking it would erase what a question is
# about, so it is kept.
_TITLE = re.compile(r"(?:Dr|Mr|Mrs|Ms|Miss|Prof|Professor|Nurse|Sister)\.?\s+$")


def _is_person(text: str, start: int, end: int) -> bool:
    return len(text[start:end].split()) > 1 or bool(_TITLE.search(text[:start]))


@lru_cache
def _analyzer() -> AnalyzerEngine:
    """Built on first use: loading the spaCy model takes seconds, and
    importing this module must stay cheap."""
    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])


@lru_cache
def _anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def mask_pii(text: str, record: dict[str, Any]) -> str:
    """`text` with each detected entity replaced by `<ENTITY_TYPE>`, except
    the patient of `record`, named by surname as in the identity check."""
    surname = record["name"].split()[-1].casefold()
    found = [
        r
        for r in _analyzer().analyze(
            text, language="en", entities=_ENTITIES, score_threshold=_MIN_SCORE
        )
        if r.entity_type != "PERSON"
        or (
            _is_person(text, r.start, r.end)
            and surname not in text[r.start : r.end].casefold()
        )
    ]
    return _anonymizer().anonymize(text=text, analyzer_results=found).text
