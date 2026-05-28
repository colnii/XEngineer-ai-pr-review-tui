from __future__ import annotations

from typing import Protocol

from xengineer_pr_review.context import build_llm_context
from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import PullRequestData, PullRequestRef, ReviewReport
from xengineer_pr_review.pr_url import parse_pr_url
from xengineer_pr_review.rules import analyze_rules


class GitHubLike(Protocol):
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData: ...


class LLMLike(Protocol):
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
        )

        findings = analyze_rules(files)
        context = build_llm_context(pr, findings)
        try:
            llm_result = self.llm.analyze(context.prompt)
            summary = llm_result.summary
            suggestions = llm_result.suggestions
            warnings = llm_result.warnings
        except Exception as exc:
            summary = "LLM analysis failed; showing deterministic rule-based findings only."
            suggestions = []
            warnings = [f"LLM failure: {exc}"]

        return ReviewReport(
            pr_title=pr.title,
            pr_url=pr_url,
            summary=summary,
            findings=findings,
            suggestions=suggestions,
            changed_files=[file.path for file in files],
            omitted_files=context.omitted_files,
            warnings=warnings,
        )
