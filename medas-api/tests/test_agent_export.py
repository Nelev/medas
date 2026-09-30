"""The export tool: a message asking for a PDF ends in a PDF of the conversation.

No real model: a scripted one calls the tool when the last message asks for
the export, so the graph, the tool and the PDF are the real ones.
"""

import json

import pdfplumber
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import langchain_agent.export as export
from langchain_agent.agent import RecordContext, export_conversation_pdf

RECORD_ID = "pat_1"


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


def test_the_model_can_name_nothing():
    schema = export_conversation_pdf.tool_call_schema.model_json_schema()

    assert schema["properties"] == {}


async def test_asking_for_a_pdf_exports_this_conversation(exports):
    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "export_conversation_pdf", "args": {}, "id": "1"}
                    ],
                ),
                AIMessage(content="Your PDF is ready."),
            ]
        )
    )
    agent = create_agent(
        model=model, tools=[export_conversation_pdf], context_schema=RecordContext
    )

    result = await agent.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "Can I take ibuprofen?"},
                {"role": "assistant", "content": "Your record lists an allergy."},
                {"role": "user", "content": "export this conversation as pdf"},
            ]
        },
        context=RecordContext(RECORD_ID),
    )

    tool_result = json.loads(result["messages"][-2].content)
    assert tool_result["status"] == "exported"
    assert tool_result["turns"] == 3

    (pdf,) = exports.iterdir()
    assert pdf.name == tool_result["file"]
    assert pdf.read_bytes().startswith(b"%PDF")

    text = _text(pdf)
    assert "Can I take ibuprofen?" in text
    assert "Your record lists an allergy." in text
    assert "export this conversation as pdf" in text
    assert result["messages"][-1].content == "Your PDF is ready."


def test_markup_in_a_turn_is_printed_not_parsed(exports):
    export.conversation_pdf(
        [{"role": "user", "content": "a <b>bold</b> & <unclosed"}],
        exports / "c.pdf",
    )

    assert "a <b>bold</b> & <unclosed" in _text(exports / "c.pdf")
