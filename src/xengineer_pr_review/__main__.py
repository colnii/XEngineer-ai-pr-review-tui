from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from xengineer_pr_review.export import render_markdown
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.judge_demo import JUDGE_DEMO_URL, JudgeDemoGitHubClient
from xengineer_pr_review.langgraph_agent import (
    DEFAULT_MAX_TOOL_ROUNDS,
    DEFAULT_OPENAI_MODEL,
    LangGraphReviewClient,
)
from xengineer_pr_review.llm import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    MockLLMClient,
)
from xengineer_pr_review.locale import normalize_language
from xengineer_pr_review.models import ReviewReport
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
    if use_mock_llm:
        llm = MockLLMClient(language=language)
    elif os.environ.get("DEEPSEEK_API_KEY"):
        llm = LangGraphReviewClient(
            model=os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL,
            language=language,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL,
            max_tool_rounds=_max_tool_rounds_from_env(),
        )
    elif os.environ.get("OPENAI_API_KEY"):
        llm = LangGraphReviewClient(
            model=os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
            language=language,
            api_key=os.environ.get("OPENAI_API_KEY"),
            max_tool_rounds=_max_tool_rounds_from_env(),
        )
    else:
        llm = MockLLMClient(language=language)
    return ReviewPipeline(github=GitHubClient(), llm=llm)


def _max_tool_rounds_from_env() -> int:
    raw_value = os.environ.get("XENGINEER_MAX_TOOL_ROUNDS")
    if raw_value is None:
        return DEFAULT_MAX_TOOL_ROUNDS
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_TOOL_ROUNDS
    return max(1, parsed)


def publish_review_comment(pipeline: ReviewPipeline, pr_url: str, language: str) -> str:
    report, markdown = analyze_review_report(pipeline, pr_url, language)
    if report.llm_status == "failed":
        raise RuntimeError("LLM analysis failed; PR comment was not published.")
    posted = pipeline.post_review_comment(pr_url, markdown)
    return posted.html_url


def analyze_review_report(
    pipeline: ReviewPipeline,
    pr_url: str,
    language: str,
) -> tuple[ReviewReport, str]:
    report = pipeline.run(pr_url)
    markdown = render_markdown(report, language=language)
    return report, markdown


def write_review_output(markdown: str, output: str) -> None:
    if output == "-":
        print(markdown, end="")
        return
    output_path = Path(output)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote review report: {output_path}")


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
        "--output",
        help="Analyze a PR and write the Markdown report to this path; use '-' for stdout",
    )
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
    if args.output is not None and args.publish_comment:
        parser.error("--output cannot be used with --publish-comment")
    if args.output == "":
        parser.error("--output must not be empty")

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

    if args.output is not None:
        if not args.pr_url and not args.judge_demo:
            parser.error("--output requires --pr-url or --judge-demo")
        pr_url = args.pr_url or JUDGE_DEMO_URL
        _, markdown = analyze_review_report(
            build_pipeline(
                use_mock_llm=args.mock_llm,
                language=args.language,
                judge_demo=args.judge_demo,
            ),
            pr_url,
            args.language,
        )
        write_review_output(markdown, args.output)
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
