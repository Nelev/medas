"""Agent middleware."""

from langchain.agents.middleware import AgentMiddleware


class MessageTrimmingMiddleware(AgentMiddleware):
    """Send the model only the most recent messages, to stay under token limits.

    Trims the request, not the agent's state: `export_conversation` reads the
    whole thread from state, and the `messages` reducer merges by id, so a
    `before_model` update could not drop messages anyway.
    """

    def __init__(self, max_messages: int = 20):
        super().__init__()
        self.max_messages = max_messages

    def _trim(self, request):
        if len(request.messages) <= self.max_messages:
            return request
        kept = request.messages[-self.max_messages :]
        # A tool result whose call was cut off is rejected by the API.
        while kept and kept[0].type == "tool":
            kept = kept[1:]
        return request.override(messages=kept)

    def wrap_model_call(self, request, handler):
        return handler(self._trim(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._trim(request))
