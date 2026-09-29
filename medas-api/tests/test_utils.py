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
        {"message": "See your GP this week.", "severity": "S3", "confidence": 0.8}
    )

    assert parse_agent_reply(reply) == (
        "See your GP this week.",
        {"severity": "S3", "confidence": 0.8, "ui": None},
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
