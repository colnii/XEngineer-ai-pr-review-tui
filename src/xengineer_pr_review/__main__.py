from __future__ import annotations

import argparse
import os

from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.llm import MockLLMClient, OpenAILLMClient
from xengineer_pr_review.locale import normalize_language
from xengineer_pr_review.pipeline import ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


def build_pipeline(use_mock_llm: bool = False, language: str = "zh") -> ReviewPipeline:
    language = normalize_language(language)
    llm = (
        MockLLMClient(language=language)
        if use_mock_llm or not os.environ.get("OPENAI_API_KEY")
        else OpenAILLMClient(language=language)
    )
    return ReviewPipeline(github=GitHubClient(), llm=llm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM output")
    parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default="zh",
        help="TUI and report language, default: zh",
    )
    args = parser.parse_args()
    ReviewTUI(
        build_pipeline(use_mock_llm=args.mock_llm, language=args.language),
        language=args.language,
    ).run()


if __name__ == "__main__":
    main()
