"""Tests for the conversions between stored turns and the agent."""

import json

import pytest

from utils import messages_as_turns, parse_agent_reply


def test_stored_turns_and_the_question_become_chat_turns():
    stored = [
        {"role": "assistant", "text": "Hi Ada, how can I help you?"},
        {"role": "user", "text": "I have been wheezing."},
    ]

    assert messages_as_turns(stored, "Since Tuesday.") == [
        {"role": "assistant", "content": "Hi Ada, how can I help you?"},
        {"role": "user", "content": "I have been wheezing."},
        {"role": "user", "content": "Since Tuesday."},
    ]


def test_a_json_reply_is_its_message_and_its_triage_code():
    reply = json.dumps(
        {"message": "See your GP this week.", "severity": "S3", "confidence": "high"}
    )

    assert parse_agent_reply(reply) == (
        "See your GP this week.",
        {"severity": "S3", "confidence": "high", "ui": None},
    )


def test_a_ui_spec_travels_with_the_turn():
    spec = {"root": "a", "elements": {"a": {"type": "Text", "props": {}}}}
    reply = json.dumps({"message": "Your readings.", "severity": "S5", "ui": spec})

    assert parse_agent_reply(reply)[1]["ui"] == spec


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param("Call 999 now.", id="prose"),
        pytest.param('{"severity": "S1"}', id="no-message"),
        pytest.param('["Call 999 now."]', id="not-an-object"),
    ],
)
def test_a_reply_that_is_not_the_object_asked_for_is_shown_as_it_stands(reply):
    assert parse_agent_reply(reply) == (reply, {})


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param('{"message": null}', id="null-message"),
        pytest.param('{"message": {"a": 1}}', id="object-message"),
        pytest.param('{"message": "  "}', id="blank-message"),
        pytest.param('{"message": 7}', id="number-message"),
    ],
)
def test_a_message_that_is_not_text_is_never_stored_as_one(reply):
    assert parse_agent_reply(reply) == (reply, {})


def test_triage_fields_outside_the_prompts_vocabulary_are_dropped():
    reply = json.dumps(
        {"message": "Rest.", "severity": ["S1"], "confidence": {"a": 1}, "ui": "x"}
    )

    assert parse_agent_reply(reply) == (
        "Rest.",
        {"severity": None, "confidence": None, "ui": None},
    )


def test_a_reply_in_content_blocks_is_read_as_its_text():
    blocks = [{"type": "text", "text": '{"message": "Rest.", "severity": "S5"}'}]

    assert parse_agent_reply(blocks)[0] == "Rest."
