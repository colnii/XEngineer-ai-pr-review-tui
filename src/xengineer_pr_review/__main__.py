from __future__ import annotations

import argparse
import os

from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.judge_demo import JUDGE_DEMO_URL, JudgeDemoGitHubClient
from xengineer_pr_review.llm import MockLLMClient, OpenAILLMClient
from xengineer_pr_review.locale import normalize_language
from xengineer_pr_review.pipeline import ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


def build_pipeline(
    use_mock_llm: bool = False,
    language: str = "zh",
    judge_demo: bool = False,
) -> ReviewPipeline:
    language = normalize_language(language)
    if judge_demo:
        return ReviewPipeline(
            github=JudgeDemoGitHubClient(),
            llm=MockLLMClient(language=language),
        )
    llm = (
        MockLLMClient(language=language)
        if use_mock_llm or not os.environ.get("OPENAI_API_KEY")
        else OpenAILLMClient(language=language)
    )
    return ReviewPipeline(github=GitHubClient(), llm=llm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge-demo",
        action="store_true",
        help="Run a zero-config built-in demo for judges; no API keys or network required",
    )
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM output")
    parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default="zh",
        help="TUI and report language, default: zh",
    )
    args = parser.parse_args()
    ReviewTUI(
        build_pipeline(
            use_mock_llm=args.mock_llm,
            language=args.language,
            judge_demo=args.judge_demo,
        ),
        language=args.language,
        initial_pr_url=JUDGE_DEMO_URL if args.judge_demo else "",
        auto_analyze=args.judge_demo,
    ).run()


if __name__ == "__main__":
    main()
