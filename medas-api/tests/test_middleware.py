"""MessageTrimmingMiddleware: what the model is sent, not what the run keeps."""

from types import SimpleNamespace

from langchain_agent.middleware import MessageTrimmingMiddleware


class _Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **changes):
        return _Request(changes["messages"])


def _msgs(*types):
    return [SimpleNamespace(type=t, n=i) for i, t in enumerate(types)]


async def _handler(request):
    return request.messages


async def test_a_short_thread_is_sent_whole():
    messages = _msgs("human", "ai", "human")

    sent = await MessageTrimmingMiddleware(5).awrap_model_call(
        _Request(messages), _handler
    )

    assert sent == messages


async def test_only_the_latest_messages_are_sent():
    messages = _msgs(*["human", "ai"] * 5)

    sent = await MessageTrimmingMiddleware(4).awrap_model_call(
        _Request(messages), _handler
    )

    assert sent == messages[-4:]


async def test_a_tool_result_cut_from_its_call_is_dropped():
    messages = _msgs("human", "ai", "tool", "ai", "human")

    sent = await MessageTrimmingMiddleware(3).awrap_model_call(
        _Request(messages), _handler
    )

    assert [m.type for m in sent] == ["ai", "human"]
