"""Shared constants, and the conversions between stored turns and the agent.

Pure functions only: nothing here touches the database, the network or the
environment, so each can be tested alone.
"""

import json

__all__ = ["OPENROUTER_BASE_URL", "messages_as_turns", "parse_agent_reply"]

# Both the chat model and the embeddings are reached through OpenRouter.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def messages_as_turns(messages: list[dict], question: str) -> list[dict]:
    """The stored turns and the new question, as a chat model takes them.

    The wire calls the field `text`; a chat model calls it `content`. Roles
    are already "user" and "assistant" on both sides. No system turn: the
    prompt belongs to the agent, and a second copy would be sent twice.
    """
    return [
        *({"role": m["role"], "content": m["text"]} for m in messages),
        {"role": "user", "content": question},
    ]


SEVERITIES = frozenset({"S1", "S2", "S3", "S4", "S5"})
CONFIDENCES = frozenset({"high", "moderate", "low"})


def _text(reply: object) -> str:
    """The reply as a string. A model can answer in content blocks (a list)
    rather than one string; their text is what the patient would read."""
    if isinstance(reply, str):
        return reply
    if isinstance(reply, list):
        return "".join(
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in reply
            if isinstance(block, str | dict)
        )
    return ""


def _one_of(value: object, allowed: frozenset[str]) -> str | None:
    # isinstance first: a list or object from the model is unhashable.
    return value if isinstance(value, str) and value in allowed else None


def parse_agent_reply(reply: object) -> tuple[str, dict]:
    """The text the patient sees, and the triage metadata stored with it.

    The prompt asks for one JSON object, so the reply is read as one: the
    patient sees `message`, and the triage code travels with the turn as
    metadata because which code was given, and when, is what an audit asks
    about later.

    The model's output is untrusted, so each field is checked before it is
    stored: `message` must be a non-empty string, `severity` one of S1-S5,
    `confidence` one of high/moderate/low, `ui` an object. A bad triage field
    is dropped (None) rather than stored; a bad `message` makes the whole
    reply prose.

    `ui`, when the model sent one, is a json-render spec the UI draws under
    the message. It is stored as given: its catalog lives in the UI, which
    validates it before rendering and drops it if it does not fit.
    """
    text = _text(reply)
    try:
        answer = json.loads(text)
        message = answer["message"]
    except json.JSONDecodeError, KeyError, TypeError:
        # Prose where an object was asked for. The model does this on its own
        # judgement -- most often on a red flag, where it drops the format and
        # writes the warning out directly. That reply is a good answer, so it
        # is shown as it stands; only the triage code is lost with it.
        return text, {}

    if not isinstance(message, str) or not message.strip():
        return text, {}

    ui = answer.get("ui")
    return message, {
        "severity": _one_of(answer.get("severity"), SEVERITIES),
        "confidence": _one_of(answer.get("confidence"), CONFIDENCES),
        "ui": ui if isinstance(ui, dict) else None,
    }
