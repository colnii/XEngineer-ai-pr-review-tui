from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from xengineer_pr_review.export import render_markdown
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


def publish_review_comment(pipeline: ReviewPipeline, pr_url: str, language: str) -> str:
    report = pipeline.run(pr_url)
    if report.llm_status == "failed":
        raise RuntimeError("LLM analysis failed; PR comment was not published.")
    markdown = render_markdown(report, language=language)
    posted = pipeline.post_review_comment(pr_url, markdown)
    return posted.html_url


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge-demo",
        action="store_true",
        help="Run a zero-config built-in demo for judges; no API keys or network required",
    )
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM output")
    parser.add_argument("--pr-url", help="Prefill or publish a specific GitHub PR URL")
    parser.add_argument(
        "--publish-comment",
        action="store_true",
        help="Analyze --pr-url and publish the report as a PR conversation comment",
    )
    parser.add_argument(
        "--confirm-publish",
        action="store_true",
        help="Required with --publish-comment to confirm the GitHub write operation",
    )
    parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default="zh",
        help="TUI and report language, default: zh",
    )
    args = parser.parse_args(argv)
    if args.publish_comment:
        if not args.pr_url:
            parser.error("--publish-comment requires --pr-url")
        if not args.confirm_publish:
            parser.error("--publish-comment requires --confirm-publish")
        if args.judge_demo:
            parser.error("--publish-comment cannot be used with --judge-demo")
        url = publish_review_comment(
            build_pipeline(
                use_mock_llm=args.mock_llm,
                language=args.language,
                judge_demo=False,
            ),
            args.pr_url,
            args.language,
        )
        print(f"Published PR comment: {url}")
        return

    initial_pr_url = args.pr_url or (JUDGE_DEMO_URL if args.judge_demo else "")
    ReviewTUI(
        build_pipeline(
            use_mock_llm=args.mock_llm,
            language=args.language,
            judge_demo=args.judge_demo,
        ),
        language=args.language,
        initial_pr_url=initial_pr_url,
        auto_analyze=args.judge_demo,
    ).run()


if __name__ == "__main__":
    main()
