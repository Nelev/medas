"""The export tool: a message asking for a file ends in a file of the conversation.

No real model: a scripted one calls the tool when the last message asks for
the export, so the graph, the tool and the file are the real ones.
"""

import csv
import json

import pdfplumber
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import langchain_agent.export as export
from langchain_agent.agent import export_conversation
from schema import RecordContext

RECORD_ID = "pat_1"

TURNS = [
    {"role": "user", "content": "Can I take ibuprofen?"},
    {"role": "assistant", "content": "Your record lists an allergy."},
]


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **_):
        return self


@pytest.fixture(autouse=True)
def exports(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path)
    return tmp_path


def _text(path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages)


def _export(turns, fmt):
    name, used = export.export_turns(turns, fmt)
    return export.EXPORT_DIR / name, used


async def _ask_for_export(args: dict):
    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "export_conversation", "args": args, "id": "1"}
                    ],
                ),
                AIMessage(content="Your file is ready."),
            ]
        )
    )
    agent = create_agent(
        model=model, tools=[export_conversation], context_schema=RecordContext
    )
    return await agent.ainvoke(
        {
            "messages": [
                *TURNS,
                {"role": "user", "content": "export this conversation"},
            ]
        },
        context=RecordContext(RECORD_ID),
    )


def test_the_model_can_name_a_format_and_nothing_else():
    schema = export_conversation.tool_call_schema.model_json_schema()

    assert list(schema["properties"]) == ["format"]


async def test_asking_for_a_pdf_exports_this_conversation(exports):
    result = await _ask_for_export({})

    tool_result = json.loads(result["messages"][-2].content)
    assert tool_result["status"] == "exported"
    assert tool_result["format"] == "pdf"
    assert tool_result["turns"] == 3

    (pdf,) = exports.iterdir()
    assert pdf.name == tool_result["file"]
    assert pdf.read_bytes().startswith(b"%PDF")

    text = _text(pdf)
    assert "Can I take ibuprofen?" in text
    assert "Your record lists an allergy." in text
    assert "export this conversation" in text
    assert result["messages"][-1].content == "Your file is ready."


async def test_the_tool_reports_the_format_it_used(exports):
    result = await _ask_for_export({"format": "docx"})

    tool_result = json.loads(result["messages"][-2].content)
    assert tool_result["requested"] == "docx"
    assert tool_result["format"] == "pdf"
    (file,) = exports.iterdir()
    assert file.suffix == ".pdf"


async def test_a_csv_is_exported_when_asked_for(exports):
    result = await _ask_for_export({"format": "csv"})

    tool_result = json.loads(result["messages"][-2].content)
    assert tool_result["format"] == "csv"
    (file,) = exports.iterdir()
    assert file.suffix == ".csv"


@pytest.mark.parametrize(
    "asked", ["PDF", ".pdf", " Pdf ", "docx", "", "xlsx", "md", "html"]
)
def test_anything_but_csv_or_json_is_a_pdf(exports, asked):
    path, used = _export(TURNS, asked)

    assert used == "pdf"
    assert path.read_bytes().startswith(b"%PDF")


def test_markup_in_a_turn_is_printed_not_parsed(exports):
    path, _ = _export([{"role": "user", "content": "a <b>bold</b> & <unclosed"}], "pdf")

    assert "a <b>bold</b> & <unclosed" in _text(path)


# Content that markdown, a csv or a spreadsheet would each treat specially.
AWKWARD = [
    "### Medas\nsneaky",
    "# a heading\n\\# already escaped\n```\nnot closed",
    "~~~ tilde",
    "line one\nline two\n\nafter a gap",
    '=SUM(A1:A2), "quoted", and a comma',
]


@pytest.mark.parametrize("content", AWKWARD)
def test_json_carries_the_turns_exactly(exports, content):
    turns = [{"role": "user", "content": content}, *TURNS]

    path, used = _export(turns, "json")

    assert used == "json"
    assert json.loads(path.read_text(encoding="utf-8"))["turns"] == turns


def test_csv_has_a_row_per_turn(exports):
    turns = [{"role": "user", "content": 'a, "b"\nc'}, *TURNS]

    path, _ = _export(turns, "csv")

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["turn"] for r in rows] == ["1", "2", "3"]
    assert [r["role"] for r in rows] == ["user", "user", "assistant"]
    assert rows[0]["content"] == 'a, "b"\nc'


def test_csv_does_not_start_a_cell_like_a_formula(exports):
    path, _ = _export([{"role": "user", "content": "=HYPERLINK(1)"}], "csv")

    with path.open(encoding="utf-8-sig", newline="") as f:
        (row,) = csv.DictReader(f)
    assert row["content"] == "'=HYPERLINK(1)"
