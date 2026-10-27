"""Bounded structured output contract. Opinions never overwrite static findings."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=2400)]
Short = Annotated[str, Field(min_length=1, max_length=600)]


class Reasoning(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    verdict: Literal["confirmed", "likely", "possible", "false_positive", "uncertain"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float = Field(ge=0, le=1)
    root_cause: Text
    impact: Text
    explanation: Text
    code_path: Text
    fix_strategy: Text
    fix_risks: Text
    tests_required: list[Short] = Field(min_length=1, max_length=8)
    uncertainty: list[Short] = Field(min_length=1, max_length=8)
    evidence_refs: list[Annotated[str, Field(pattern=r"^E[0-9]+$", max_length=12)]] = Field(max_length=12)


class ProviderError(Exception):
    """Contains only safe, user-facing error text, never provider payloads."""


class LLMProvider(Protocol):
    def models(self) -> list[dict]: ...
    def reason(self, model: str, context: dict) -> Reasoning: ...
