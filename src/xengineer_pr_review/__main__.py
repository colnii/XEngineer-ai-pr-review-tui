from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from xengineer_pr_review.action_workflow import DEFAULT_ACTION_USES, init_action_workflow
from xengineer_pr_review.credentials import (
    format_missing_required_credentials_message,
    read_credential_status,
)
from xengineer_pr_review.env import loaded_dotenv
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
from xengineer_pr_review.models import ReviewAction, ReviewReport
from xengineer_pr_review.pipeline import CommentMode, ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


MODEL_CONFIG_ERROR = (
    "Real model review requires DEEPSEEK_API_KEY or OPENAI_API_KEY. "
    "Use --judge-demo for zero-config evaluation."
)


class MissingModelConfigurationError(RuntimeError):
    pass


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
        raise MissingModelConfigurationError(MODEL_CONFIG_ERROR)
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


def publish_review_comment(
    pipeline: ReviewPipeline,
    pr_url: str,
    language: str,
    comment_mode: CommentMode = "conversation",
    review_action: ReviewAction = "comment",
) -> str:
    report, markdown = analyze_review_report(pipeline, pr_url, language)
    if report.llm_status == "failed":
        raise RuntimeError("LLM analysis failed; PR comment was not published.")
    posted = pipeline.post_review_comment(
        pr_url,
        markdown,
        comment_mode=comment_mode,
        review_action=review_action,
    )
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


def _build_pipeline_or_error(parser: argparse.ArgumentParser, **kwargs) -> ReviewPipeline:
    try:
        return build_pipeline(**kwargs)
    except MissingModelConfigurationError:
        language = kwargs.get("language", "zh")
        parser.error(format_missing_required_credentials_message(language))


def main(argv: Sequence[str] | None = None) -> None:
    argv = list(argv) if argv is not None else sys.argv[1:]
    _run_main(argv)


def _run_main(argv: Sequence[str]) -> None:
    parser = argparse.ArgumentParser()
    init_action_parser = _add_init_action_subcommand(parser)
    parser.add_argument(
        "--judge-demo",
        action="store_true",
        help="Run a zero-config built-in demo for judges; no API keys or network required",
    )
    parser.add_argument("--mock-llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pr-url", help="Prefill or publish a specific GitHub PR URL")
    parser.add_argument(
        "--output",
        help="Analyze a PR and write the Markdown report to this path; use '-' for stdout",
    )
    parser.add_argument(
        "--publish-comment",
        action="store_true",
        help="Analyze --pr-url and publish the report as a PR comment",
    )
    parser.add_argument(
        "--comment-mode",
        choices=("conversation", "review"),
        default="conversation",
        help="Comment publish target, default: conversation",
    )
    parser.add_argument(
        "--review-action",
        choices=("comment", "approve", "request-changes"),
        default="comment",
        help="Pull request review action when --comment-mode review is used, default: comment",
    )
    parser.add_argument(
        "--confirm-publish",
        action="store_true",
        help="Required with --publish-comment to confirm the GitHub write operation",
    )
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="Automation alias for --confirm-publish when used with --publish-comment",
    )
    parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default="zh",
        help="TUI and report language, default: zh",
    )
    args = parser.parse_args(argv)
    if args.command == "init-action":
        _run_init_action(args, init_action_parser)
        return

    if args.output is not None and args.publish_comment:
        parser.error("--output cannot be used with --publish-comment")
    if args.output == "":
        parser.error("--output must not be empty")
    if args.auto_publish and not args.publish_comment:
        parser.error("--auto-publish requires --publish-comment")
    if args.review_action != "comment" and not args.publish_comment:
        parser.error("--review-action requires --publish-comment")
    if args.review_action != "comment" and args.comment_mode != "review":
        parser.error("--review-action approve/request-changes requires --comment-mode review")

    if args.publish_comment:
        if not args.pr_url:
            parser.error("--publish-comment requires --pr-url")
        if not (args.confirm_publish or args.auto_publish):
            parser.error("--publish-comment requires --confirm-publish or --auto-publish")
        if args.judge_demo:
            parser.error("--publish-comment cannot be used with --judge-demo")
        with loaded_dotenv():
            url = publish_review_comment(
                _build_pipeline_or_error(
                    parser,
                    use_mock_llm=args.mock_llm,
                    language=args.language,
                    judge_demo=False,
                ),
                args.pr_url,
                args.language,
                comment_mode=args.comment_mode,
                review_action=args.review_action,
            )
        published_label = "Published PR review" if args.comment_mode == "review" else "Published PR comment"
        print(f"{published_label}: {url}")
        return

    if args.output is not None:
        if not args.pr_url and not args.judge_demo:
            parser.error("--output requires --pr-url or --judge-demo")
        pr_url = args.pr_url or JUDGE_DEMO_URL
        with loaded_dotenv():
            _, markdown = analyze_review_report(
                _build_pipeline_or_error(
                    parser,
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
    with loaded_dotenv():
        credential_status = read_credential_status()
        pipeline_factory = None
        if not args.mock_llm and not args.judge_demo and not credential_status.has_model_key:
            print(
                format_missing_required_credentials_message(
                    args.language,
                    include_tui_onboarding=True,
                ),
                file=sys.stderr,
            )
            pipeline = None

            def build_tui_pipeline() -> ReviewPipeline:
                return build_pipeline(
                    use_mock_llm=args.mock_llm,
                    language=args.language,
                    judge_demo=args.judge_demo,
                )

            pipeline_factory = build_tui_pipeline
        else:
            pipeline = _build_pipeline_or_error(
                parser,
                use_mock_llm=args.mock_llm,
                language=args.language,
                judge_demo=args.judge_demo,
            )
        ReviewTUI(
            pipeline,
            pipeline_factory=pipeline_factory,
            credential_status=credential_status,
            language=args.language,
            initial_pr_url=initial_pr_url,
            auto_analyze=args.judge_demo,
        ).run()


def _add_init_action_subcommand(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(dest="command")
    init_action_parser = subparsers.add_parser(
        "init-action",
        help="Generate a GitHub Actions workflow for a target repository",
    )
    init_action_parser.add_argument(
        "--repo-path",
        default=".",
        help="Repository path where .github/workflows/xengineer-pr-review.yml will be written",
    )
    init_action_parser.add_argument(
        "--action-uses",
        default=DEFAULT_ACTION_USES,
        help="Action reference used in the generated workflow",
    )
    init_action_parser.add_argument(
        "--comment-mode",
        choices=("conversation", "review"),
        default="conversation",
        help="Comment target used in the generated workflow, default: conversation",
    )
    init_action_parser.add_argument(
        "--review-action",
        choices=("comment", "approve", "request-changes"),
        default="comment",
        help="Review action used when generated workflow publishes PR reviews, default: comment",
    )
    init_action_parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default="zh",
        help="Generated workflow report language, default: zh",
    )
    init_action_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing xengineer-pr-review workflow file",
    )
    return init_action_parser


def _run_init_action(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        workflow_path = init_action_workflow(
            repo_path=args.repo_path,
            action_uses=args.action_uses,
            comment_mode=args.comment_mode,
            review_action=args.review_action,
            language=args.language,
            overwrite=args.overwrite,
        )
    except (FileExistsError, NotADirectoryError) as exc:
        parser.error(str(exc))

    print(f"Wrote GitHub Actions workflow: {workflow_path}")


if __name__ == "__main__":
    main()
