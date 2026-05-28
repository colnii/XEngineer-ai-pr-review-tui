from __future__ import annotations

import argparse
import os

from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.llm import MockLLMClient, OpenAILLMClient
from xengineer_pr_review.pipeline import ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


def build_pipeline(use_mock_llm: bool = False) -> ReviewPipeline:
    llm = MockLLMClient() if use_mock_llm or not os.environ.get("OPENAI_API_KEY") else OpenAILLMClient()
    return ReviewPipeline(github=GitHubClient(), llm=llm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM output")
    args = parser.parse_args()
    ReviewTUI(build_pipeline(use_mock_llm=args.mock_llm)).run()


if __name__ == "__main__":
    main()
