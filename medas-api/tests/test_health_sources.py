"""The MedlinePlus and PubMed tools, with the HTTP call stubbed."""

import json
from types import SimpleNamespace

import httpx

import langchain_agent.agent as agent
import langchain_agent.health_sources as sources

MEDLINEPLUS_XML = """<nlmSearchResult><list>
<document rank="0" url="https://medlineplus.gov/painrelievers.html">
<content name="title">&lt;span class="qt0"&gt;Pain&lt;/span&gt; Relievers</content>
<content name="FullSummary">&lt;p&gt;Medicines   that relieve pain.&lt;/p&gt;</content>
</document></list></nlmSearchResult>"""

PUBMED_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>1</PMID><Article>
<Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue>
<Title>Some Journal</Title></Journal>
<ArticleTitle>Ibuprofen and <i>omeprazole</i>.</ArticleTitle>
<Abstract><AbstractText Label="A">First.</AbstractText>
<AbstractText>Second.</AbstractText></Abstract>
</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


def _stub(monkeypatch, **responses):
    """Answer each request by the last path segment of its url."""
    calls = []

    async def _get(url, params):
        calls.append((url, params))
        return responses[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(sources, "_get", _get)
    return calls


async def test_medlineplus_strips_the_markup(monkeypatch):
    _stub(monkeypatch, query=SimpleNamespace(text=MEDLINEPLUS_XML))

    assert await sources.search_medlineplus("ibuprofen") == [
        {
            "title": "Pain Relievers",
            "url": "https://medlineplus.gov/painrelievers.html",
            "summary": "Medicines that relieve pain.",
        }
    ]


async def test_pubmed_searches_then_fetches_the_abstracts(monkeypatch):
    calls = _stub(
        monkeypatch,
        **{
            "esearch.fcgi": SimpleNamespace(
                json=lambda: {"esearchresult": {"idlist": ["1", "2"]}}
            ),
            "efetch.fcgi": SimpleNamespace(text=PUBMED_XML),
        },
    )

    assert await sources.search_pubmed("ibuprofen omeprazole") == [
        {
            "title": "Ibuprofen and omeprazole.",
            "journal": "Some Journal",
            "year": "2026",
            "abstract": "First. Second.",
            "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        }
    ]
    assert calls[1][1]["id"] == "1,2"


async def test_pubmed_with_no_hits_makes_no_second_call(monkeypatch):
    calls = _stub(
        monkeypatch,
        **{
            "esearch.fcgi": SimpleNamespace(
                json=lambda: {"esearchresult": {"idlist": []}}
            )
        },
    )

    assert await sources.search_pubmed("zzzz") == []
    assert len(calls) == 1


def test_the_model_can_only_pass_a_query():
    for tool in (agent.search_medlineplus, agent.search_pubmed):
        schema = tool.tool_call_schema.model_json_schema()

        assert set(schema["properties"]) == {"query"}


async def test_a_source_outage_is_reported_to_the_model(monkeypatch):
    async def _down(_query):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(sources, "search_pubmed", _down)

    reply = await agent.search_pubmed.coroutine("anything")

    assert json.loads(reply) == {"error": "source unavailable"}


def _tool(name, content):
    return SimpleNamespace(type="tool", name=name, content=json.dumps(content))


def test_sources_are_the_top_pages_the_lookups_returned():
    pages = [{"url": f"https://x/{i}"} for i in range(3)]
    messages = [
        SimpleNamespace(type="human", name=None, content="hi"),
        _tool("search_medlineplus", pages),
        _tool("search_patient_record", [{"url": "https://record/"}]),
        _tool("search_pubmed", pages[1:]),
        _tool("search_pubmed", {"error": "source unavailable"}),
    ]

    assert agent._source_urls(messages) == ["https://x/0", "https://x/1", "https://x/2"]


def test_sources_go_at_the_end_of_the_message():
    reply = json.dumps({"message": "Hi", "severity": "S5"})

    out = json.loads(agent._with_sources(reply, ["https://x/0", "https://x/1"]))

    assert out["message"] == "Hi\n\nSources:\n- https://x/0\n- https://x/1"
    assert out["severity"] == "S5"


def test_sources_go_after_a_prose_reply_and_never_after_nothing():
    assert agent._with_sources("Call 112.", ["https://x/0"]).endswith("- https://x/0")
    assert agent._with_sources("Call 112.", []) == "Call 112."
