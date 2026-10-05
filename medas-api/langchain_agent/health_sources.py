"""General medical information from two free, official sources, for the
agent's tools: MedlinePlus (plain-language health topics) and PubMed
(research abstracts), both run by the US National Library of Medicine.

Nothing here knows about a patient: a query goes out to a third party, so the
tools' descriptions and the prompt keep identifiers out of it.
"""

import html
import re
import xml.etree.ElementTree as ET

import httpx
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

__all__ = ["SOURCE_ERRORS", "search_medlineplus", "search_pubmed"]

# What a source being down, or sending something unreadable, raises.
SOURCE_ERRORS = (httpx.HTTPError, ET.ParseError, DefusedXmlException)

MEDLINEPLUS = "https://wsearch.nlm.nih.gov/ws/query"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 10.0
MAX_RESULTS = 3
MAX_CHARS = 700


async def _get(url: str, params: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    return response


def _plain(text: str | None) -> str:
    """Text without markup or runs of whitespace, cut to a size the model
    can use. The sources send HTML inside their XML."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return " ".join(text.split())[:MAX_CHARS]


def _all_text(element: ET.Element | None) -> str:
    return "".join(element.itertext()) if element is not None else ""


async def search_medlineplus(query: str) -> list[dict]:
    """Health topics matching `query`: title, page and a short summary."""
    response = await _get(
        MEDLINEPLUS, {"db": "healthTopics", "term": query, "retmax": MAX_RESULTS}
    )

    def content(document: ET.Element, name: str) -> str:
        found = (c for c in document.iter("content") if c.get("name") == name)
        return _plain(_all_text(next(found, None)))

    return [
        {
            "title": content(d, "title"),
            "url": d.get("url"),
            "summary": content(d, "FullSummary"),
        }
        for d in SafeET.fromstring(response.text).iter("document")
    ]


async def search_pubmed(query: str) -> list[dict]:
    """Articles matching `query`, most relevant first: title, journal, year,
    a short abstract and the page."""
    found = await _get(
        f"{EUTILS}/esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmax": MAX_RESULTS,
            "sort": "relevance",
            "retmode": "json",
        },
    )
    ids = found.json()["esearchresult"]["idlist"]
    if not ids:
        return []

    response = await _get(
        f"{EUTILS}/efetch.fcgi",
        {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"},
    )
    return [
        {
            "title": _plain(_all_text(a.find(".//ArticleTitle"))),
            "journal": a.findtext(".//Journal/Title"),
            "year": a.findtext(".//PubDate/Year"),
            "abstract": _plain(" ".join(_all_text(t) for t in a.iter("AbstractText"))),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{a.findtext('.//PMID')}/",
        }
        for a in SafeET.fromstring(response.text).iter("PubmedArticle")
    ]
