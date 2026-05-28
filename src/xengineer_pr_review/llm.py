from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

from xengineer_pr_review.models import ReviewSuggestion


@dataclass(frozen=True)
class LLMResult:
    summary: str
    suggestions: list[ReviewSuggestion]
    warnings: list[str]


class MockLLMClient:
    def analyze(self, prompt: str) -> LLMResult:
        return LLMResult(
            summary="Mock summary: this PR changes code that should be reviewed for behavior and tests.",
            suggestions=[
                ReviewSuggestion(
                    severity="medium",
                    title="Review behavior and tests",
                    body="Check whether the changed code has enough test coverage and preserves compatibility.",
                    files=[],
                )
            ],
            warnings=[],
        )


class OpenAILLMClient:
    def __init__(self, model: str = "gpt-4.1-mini") -> None:
        self.model = model
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def analyze(self, prompt: str) -> LLMResult:
        response = self.client.responses.create(
            model=self.model,
            input=(
                "You are a pragmatic senior engineer reviewing a GitHub PR. "
                "Return concise Markdown with Summary, Risks, and Suggestions.\n\n"
                f"{prompt}"
            ),
        )
        text = response.output_text.strip()
        return LLMResult(
            summary=text,
            suggestions=[],
            warnings=["LLM returned Markdown text; structured suggestion extraction is not enabled yet."],
        )
