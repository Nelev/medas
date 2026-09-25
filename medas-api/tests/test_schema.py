"""Tests for the request schema -- the validation boundary."""

import pytest
from pydantic import ValidationError

from schema import NewMessage
from schema.schema import MAX_TEXT_LENGTH


def test_accepts_a_normal_message():
    message = NewMessage(role="user", text="What is my last episode?")
    assert (message.role, message.text) == ("user", "What is my last episode?")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param(" ", id="single-space"),
        pytest.param("   ", id="spaces"),
        pytest.param("\t", id="tab"),
        pytest.param("\n", id="newline"),
        pytest.param("\t\n ", id="mixed-whitespace"),
        pytest.param(chr(0xA0), id="non-breaking-space"),
    ],
)
def test_blank_text_is_rejected(value):
    # min_length alone would let every case but "" through: " " is one
    # character. str_strip_whitespace runs first, so these all collapse to ""
    # and fail the length check, producing a 422 at the edge instead of an
    # empty prompt reaching the pipeline.
    with pytest.raises(ValidationError):
        NewMessage(role="user", text=value)


def test_text_over_the_ceiling_is_rejected():
    with pytest.raises(ValidationError):
        NewMessage(role="user", text="x" * (MAX_TEXT_LENGTH + 1))


def test_surrounding_whitespace_is_stripped():
    assert NewMessage(role="user", text="  hello  ").text == "hello"


def test_internal_whitespace_is_preserved():
    # Stripping is an edge concern; it must not reformat the prompt itself.
    message = NewMessage(role="user", text="what about\n\nmy asthma?")
    assert message.text == "what about\n\nmy asthma?"


def test_unknown_fields_are_ignored():
    # Pydantic's default is to ignore extras, so a client sending a stray key
    # -- a message_id, say, which is minted server-side -- gets a 201 rather
    # than a 422. Pinned so a later switch to extra="forbid" is a deliberate,
    # visible change.
    message = NewMessage(role="user", text="hi", message_id="abc")
    assert not hasattr(message, "message_id")
