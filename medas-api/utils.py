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


def parse_agent_reply(reply: str) -> tuple[str, dict]:
    """The text the patient sees, and the triage metadata stored with it.

    The prompt asks for one JSON object, so the reply is read as one: the
    patient sees `message`, and the triage code travels with the turn as
    metadata because which code was given, and when, is what an audit asks
    about later.

    `ui`, when the model sent one, is a json-render spec the UI draws under
    the message. It is stored as given: its catalog lives in the UI, which
    validates it before rendering and drops it if it does not fit.
    """
    try:
        answer = json.loads(reply)
        return answer["message"], {
            "severity": answer.get("severity"),
            "confidence": answer.get("confidence"),
            "ui": answer.get("ui"),
        }
    except json.JSONDecodeError, KeyError, TypeError:
        # Prose where an object was asked for. The model does this on its own
        # judgement -- most often on a red flag, where it drops the format and
        # writes the warning out directly. That reply is a good answer, so it
        # is shown as it stands; only the triage code is lost with it.
        return reply, {}
