"""Tests for the request schemas -- the validation boundary."""

import pytest
from pydantic import ValidationError

from schema import MessageRequest


def test_accepts_a_normal_message():
    request = MessageRequest(message="What is my last episode?", user_name="mattia")
    assert request.message == "What is my last episode?"
    assert request.user_name == "mattia"


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
def test_blank_message_is_rejected(value):
    # min_length alone would let every case but "" through: " " is one
    # character. str_strip_whitespace runs first, so these all collapse to ""
    # and fail the length check, producing a 422 at the edge instead of an
    # empty prompt reaching the pipeline.
    with pytest.raises(ValidationError):
        MessageRequest(message=value, user_name="mattia")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param(" ", id="single-space"),
        pytest.param("\t\n ", id="mixed-whitespace"),
    ],
)
def test_blank_user_name_is_rejected(value):
    with pytest.raises(ValidationError):
        MessageRequest(message="hello", user_name=value)


def test_surrounding_whitespace_is_stripped():
    request = MessageRequest(message="  hello  ", user_name="  mattia  ")
    assert request.message == "hello"
    assert request.user_name == "mattia"


def test_internal_whitespace_is_preserved():
    # Stripping is an edge concern; it must not reformat the prompt itself.
    request = MessageRequest(message="what about\n\nmy asthma?", user_name="m")
    assert request.message == "what about\n\nmy asthma?"


def test_both_fields_are_required():
    with pytest.raises(ValidationError):
        MessageRequest(message="hello")


def test_unknown_fields_are_ignored():
    # Pydantic's default is to ignore extras, so a client sending a stray key
    # gets a 200 rather than a 422. Pinned so a later switch to extra="forbid"
    # is a deliberate, visible change.
    request = MessageRequest(message="hi", user_name="m", session_id="abc")
    assert not hasattr(request, "session_id")
