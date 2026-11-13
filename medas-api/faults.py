"""Fault switches: known bugs that can be turned on, one environment variable
each, so TraceScan can be measured on failures whose cause is known.

All are off unless set, and none is meant for anything but a test run: each
breaks the assistant on purpose. They are read once, when the agent is first
built or a lookup first made, so restart the process after changing one.

    FAULT_EMPTY_RETRIEVAL=medication   the record search finds nothing for
                                       queries of one category (CATEGORIES)
    FAULT_TOOL_SCHEMA=1                search_patient_record is called with an
                                       argument its schema no longer has
    FAULT_TRUNCATED_PROMPT=1           the system prompt is cut before its
                                       Output section, the reply's format
    FAULT_CONTEXT_TOKENS=1000          the model is sent only this many tokens
                                       after the question, so a long search
                                       result is dropped and searched for again
    FAULT_WEAK_MODEL=<openrouter slug> the agent runs on this model instead
    FAULT_UPSTREAM_TIMEOUT=0.5         this share of MedlinePlus and PubMed
                                       calls time out

What each one does to a trace, and what TraceScan should name as its cause, is
in the root README's "Fault switches" section.
"""

import random
from functools import lru_cache

from langchain.agents.middleware import AgentMiddleware
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The words that put a record search in a category, for FAULT_EMPTY_RETRIEVAL.
# Matched in the query the model sends to the search, not the patient's
# question: the search is where the fault sits.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "medication": (
        "medication",
        "medicine",
        "drug",
        "dose",
        "prescri",
        "tablet",
        "inhaler",
        "injection",
    ),
    "allergy": ("allerg", "reaction", "intoleran"),
    "appointment": ("appointment", "follow-up", "follow up", "visit", "booked"),
}

# Where FAULT_TRUNCATED_PROMPT cuts the system prompt: the heading of the
# section that says what the reply must look like.
PROMPT_CUT_AT = "## Output"
# What a timed-out source call is given instead of the usual 10 s: short
# enough that the connection itself times out.
TIMED_OUT_S = 0.001
# The argument FAULT_TOOL_SCHEMA sends in place of `query`: the name a caller
# that was not updated after a rename would still use.
STALE_ARGUMENT = "search_query"
BROKEN_TOOL = "search_patient_record"


class FaultSettings(BaseSettings):
    """Which faults are on, read from the environment or .env."""

    model_config = SettingsConfigDict(
        env_prefix="FAULT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    empty_retrieval: str | None = None
    tool_schema: bool = False
    truncated_prompt: bool = False
    context_tokens: int | None = Field(default=None, ge=1)
    weak_model: str | None = None
    upstream_timeout: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _known_category(self) -> FaultSettings:
        if self.empty_retrieval and self.empty_retrieval not in CATEGORIES:
            known = ", ".join(CATEGORIES)
            raise ValueError(f"empty_retrieval must be one of {known}")
        return self

    def active(self) -> list[str]:
        """The names of the faults that are on, for a run to print."""
        return [
            name
            for name, value in self.model_dump().items()
            if value not in (None, False, 0.0)
        ]


@lru_cache
def get_faults() -> FaultSettings:
    return FaultSettings()


def category_of(query: str) -> str | None:
    """The first category whose words `query` contains, if any."""
    lowered = query.lower()
    return next(
        (
            name
            for name, words in CATEGORIES.items()
            if any(w in lowered for w in words)
        ),
        None,
    )


def finds_nothing(query: str, faults: FaultSettings | None = None) -> bool:
    """Whether FAULT_EMPTY_RETRIEVAL empties the record search for `query`."""
    category = (faults or get_faults()).empty_retrieval
    return category is not None and category_of(query) == category


def times_out(faults: FaultSettings | None = None) -> bool:
    """Whether FAULT_UPSTREAM_TIMEOUT makes this source call time out."""
    share = (faults or get_faults()).upstream_timeout
    return share > 0 and random.random() < share  # noqa: S311 - a share, not a secret


def truncated(prompt: str, faults: FaultSettings | None = None) -> str:
    """The system prompt, cut before its Output section when
    FAULT_TRUNCATED_PROMPT is on."""
    if not (faults or get_faults()).truncated_prompt:
        return prompt
    return prompt[: prompt.index(PROMPT_CUT_AT)].rstrip()


def _tokens(message) -> int:
    """A rough count, four characters a token: the fault needs no tokenizer."""
    content = message.content
    text = content if isinstance(content, str) else str(content)
    return len(text) // 4 + 1


def within(messages: list, budget: int) -> list:
    """The thread up to its last question, then the newest messages after it
    that fit in `budget` tokens. A tool result that does not fit is dropped
    with the call that asked for it, so the model never sees what it found."""
    last_question = max(
        (i for i, m in enumerate(messages) if m.type == "human"), default=-1
    )
    kept: list = []
    used = 0
    for message in reversed(messages[last_question + 1 :]):
        used += _tokens(message)
        if used > budget:
            break
        kept.insert(0, message)
    # A tool result whose call was cut off is rejected by the API.
    while kept and kept[0].type == "tool":
        kept = kept[1:]
    return messages[: last_question + 1] + kept


class FaultMiddleware(AgentMiddleware):
    """The faults that sit between the agent and its model or tools:
    FAULT_CONTEXT_TOKENS and FAULT_TOOL_SCHEMA. Does nothing while both are off.
    """

    def __init__(self, faults: FaultSettings | None = None) -> None:
        super().__init__()
        self.faults = faults or get_faults()

    def _model_request(self, request):
        budget = self.faults.context_tokens
        if budget is None:
            return request
        return request.override(messages=within(request.messages, budget))

    def _tool_request(self, request):
        call = request.tool_call
        if not self.faults.tool_schema or call["name"] != BROKEN_TOOL:
            return request
        args = dict(call["args"])
        if "query" in args:
            args[STALE_ARGUMENT] = args.pop("query")
        return request.override(tool_call={**call, "args": args})

    def wrap_model_call(self, request, handler):
        return handler(self._model_request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._model_request(request))

    def wrap_tool_call(self, request, handler):
        return handler(self._tool_request(request))

    async def awrap_tool_call(self, request, handler):
        return await handler(self._tool_request(request))
