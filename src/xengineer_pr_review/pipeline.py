from __future__ import annotations

import logging
from typing import Protocol, TypeGuard

from xengineer_pr_review.context import build_llm_context
from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import PullRequestData, PullRequestRef, ReviewReport
from xengineer_pr_review.pr_url import parse_pr_url
from xengineer_pr_review.review_tools import ReviewToolbox, default_web_searcher
from xengineer_pr_review.rules import analyze_rules


LOGGER = logging.getLogger(__name__)


class GitHubLike(Protocol):
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData: ...
    def post_pr_comment(self, ref: PullRequestRef, body: str): ...


class GitHubReadLike(GitHubLike, Protocol):
    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str: ...
    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]: ...


class LLMLike(Protocol):
    supports_review_tools: bool

    def analyze(self, prompt: str): ...


class ReviewPipeline:
    def __init__(self, github: GitHubLike | None = None, llm: LLMLike | None = None) -> None:
        self.github = github or GitHubClient()
        self.llm = llm or MockLLMClient()

    def run(self, pr_url: str) -> ReviewReport:
        ref = parse_pr_url(pr_url)
        pr = self.github.fetch_pr(ref)
        files = pr.files or parse_unified_diff(pr.diff_text)
        pr = PullRequestData(
            ref=pr.ref,
            title=pr.title,
            author=pr.author,
            base_branch=pr.base_branch,
            head_branch=pr.head_branch,
            files=files,
            diff_text=pr.diff_text,
            head_sha=pr.head_sha,
        )

        findings = analyze_rules(files)
        context = build_llm_context(pr, findings)
        try:
            llm_result = self._analyze_with_optional_tools(context.prompt, pr)
            summary = llm_result.summary
            findings = [*findings, *llm_result.risks]
            suggestions = llm_result.suggestions
            warnings = llm_result.warnings
            llm_status = "parsed_with_warnings" if warnings else "ok"
            ai_notes = llm_result.notes
            raw_ai_output = llm_result.raw_output
        except Exception as exc:
            summary = "LLM analysis failed; showing deterministic rule-based findings only."
            suggestions = []
            warnings = [f"LLM failure: {exc}"]
            llm_status = "failed"
            ai_notes = ""
            raw_ai_output = ""

        return ReviewReport(
            pr_title=pr.title,
            pr_url=pr_url,
            repo=f"{ref.owner}/{ref.repo}",
            pr_number=ref.number,
            author=pr.author,
            additions=sum(file.additions for file in files),
            deletions=sum(file.deletions for file in files),
            summary=summary,
            findings=findings,
            suggestions=suggestions,
            changed_files=[file.path for file in files],
            omitted_files=context.omitted_files,
            warnings=warnings,
            llm_status=llm_status,
            ai_notes=ai_notes,
            raw_ai_output=raw_ai_output,
        )

    def post_review_comment(self, pr_url: str, body: str):
        ref = parse_pr_url(pr_url)
        return self.github.post_pr_comment(ref, body)

    def _analyze_with_optional_tools(self, prompt: str, pr: PullRequestData):
        if not getattr(self.llm, "supports_review_tools", False):
            return self.llm.analyze(prompt)
        if not _github_supports_read_tools(self.github):
            LOGGER.info("Review tools disabled: GitHub client does not support file read/search tools.")
            return self.llm.analyze(prompt, toolbox=None)
        toolbox = ReviewToolbox(
            github=self.github,
            ref=pr.ref,
            git_ref=pr.head_sha or pr.head_branch,
            web_searcher=default_web_searcher(),
        )
        return self.llm.analyze(prompt, toolbox=toolbox)


def _github_supports_read_tools(github: GitHubLike) -> TypeGuard[GitHubReadLike]:
    return hasattr(github, "fetch_file_text") and hasattr(github, "fetch_tree_paths")
