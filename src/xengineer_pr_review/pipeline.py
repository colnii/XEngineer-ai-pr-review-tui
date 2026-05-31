from __future__ import annotations

import logging
import re
from typing import Any, Literal, Protocol, TypeGuard
from urllib.parse import quote, urlparse

from xengineer_pr_review.context import build_llm_context
from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import (
    ChangedFile,
    EvidenceReference,
    InlineReviewComment,
    PullRequestData,
    PullRequestRef,
    ReviewAction,
    ReviewFinding,
    ReviewReport,
    ReviewSuggestion,
)
from xengineer_pr_review.pr_url import parse_pr_url
from xengineer_pr_review.review_tools import ReviewToolbox, default_web_searcher
from xengineer_pr_review.rules import analyze_rules


LOGGER = logging.getLogger(__name__)
CommentMode = Literal["conversation", "review"]
MAX_INLINE_REVIEW_COMMENTS = 10
MAX_EXTERNAL_FACT_SEARCHES = 3
EXTERNAL_URL_PATTERN = re.compile(r"https?://[^\s\"'<>),]+")


class GitHubLike(Protocol):
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData: ...
    def post_pr_comment(self, ref: PullRequestRef, body: str): ...


class GitHubReadLike(GitHubLike, Protocol):
    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str: ...
    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]: ...


class GitHubReviewLike(GitHubLike, Protocol):
    def post_pr_review(
        self,
        ref: PullRequestRef,
        body: str,
        review_action: ReviewAction = "comment",
        comments: list[InlineReviewComment] | None = None,
        commit_id: str = "",
    ): ...


class LLMLike(Protocol):
    supports_review_tools: bool

    def analyze(self, prompt: str, toolbox: Any | None = None): ...


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
            activities=pr.activities,
        )

        findings = analyze_rules(files)
        context = build_llm_context(pr, findings)
        try:
            llm_result = self._analyze_with_optional_tools(context.prompt, pr, context.file_ids)
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

        _enrich_review_item_evidence(findings, suggestions, pr, context.file_ids)
        return ReviewReport(
            pr_title=pr.title,
            pr_url=pr_url,
            repo=f"{ref.owner}/{ref.repo}",
            pr_number=ref.number,
            head_sha=pr.head_sha,
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

    def post_review_comment(
        self,
        pr_url: str,
        body: str,
        comment_mode: CommentMode = "conversation",
        review_action: ReviewAction = "comment",
        include_inline_comments: bool = False,
        report: ReviewReport | None = None,
    ):
        ref = parse_pr_url(pr_url)
        if comment_mode == "conversation":
            if include_inline_comments:
                raise ValueError("Inline review comments require pull request review mode.")
            return self.github.post_pr_comment(ref, body)
        if comment_mode == "review":
            if _github_supports_pr_reviews(self.github):
                comments: list[InlineReviewComment] = []
                commit_id = ""
                if include_inline_comments:
                    if report is None or not report.head_sha:
                        raise ValueError(
                            "Inline review comments require a review report with head SHA."
                        )
                    comments = build_inline_review_comments(report)
                    commit_id = report.head_sha
                return self.github.post_pr_review(
                    ref,
                    body,
                    review_action=review_action,
                    comments=comments,
                    commit_id=commit_id,
                )
            raise ValueError("GitHub client does not support pull request review comments.")
        raise ValueError(f"Unsupported PR comment mode: {comment_mode}")

    def _analyze_with_optional_tools(
        self,
        prompt: str,
        pr: PullRequestData,
        file_ids: dict[str, str],
    ):
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
            file_ids=file_ids,
            activities=pr.activities,
        )
        prompt = _with_external_fact_search_context(prompt, pr, toolbox)
        result = self.llm.analyze(prompt, toolbox=toolbox)
        _hydrate_web_evidence(result.risks, result.suggestions, toolbox.web_sources)
        return result


def _github_supports_read_tools(github: GitHubLike) -> TypeGuard[GitHubReadLike]:
    return hasattr(github, "fetch_file_text") and hasattr(github, "fetch_tree_paths")


def _github_supports_pr_reviews(github: GitHubLike) -> TypeGuard[GitHubReviewLike]:
    return hasattr(github, "post_pr_review")


def _with_external_fact_search_context(
    prompt: str,
    pr: PullRequestData,
    toolbox: ReviewToolbox,
) -> str:
    if getattr(toolbox, "web_searcher", None) is None:
        return prompt
    search_outputs: list[str] = []
    changed_urls: list[str] = []
    fact_findings: list[str] = []
    for changed_url, query in _external_fact_search_queries(pr):
        result = toolbox.web_search(query, max_results=3)
        if result.startswith(("web_search error", "web_search unavailable")):
            continue
        changed_urls.append(changed_url)
        if changed_url not in result:
            fact_findings.append(
                "External fact-check finding: no web result explicitly documents "
                f"{changed_url}; flag this changed endpoint as unverified."
            )
        search_outputs.append(result)
    if not search_outputs:
        return prompt
    changed_url_lines = [
        f"Changed external URL under review: {changed_url}"
        for changed_url in changed_urls
    ]
    return "\n\n".join(
        [
            prompt,
            "External fact-check context:",
            *changed_url_lines,
            *fact_findings,
            *search_outputs,
            (
                "Use these W1/W2 web citation ids when the final review discusses "
                "external endpoint, version, advisory, or public-documentation facts."
            ),
            (
                "Only treat the changed URL as verified when a web result explicitly "
                "documents it; otherwise flag the changed endpoint as unverified."
            ),
        ]
    )


def _external_fact_search_queries(pr: PullRequestData) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    for file in pr.files:
        for hunk in file.hunks:
            for line in hunk.splitlines():
                if not line.startswith("+") or line.startswith("+++"):
                    continue
                for url in EXTERNAL_URL_PATTERN.findall(line):
                    query = _official_docs_query_for_url(url)
                    if query and (url, query) not in queries:
                        queries.append((url, query))
                    if len(queries) >= MAX_EXTERNAL_FACT_SEARCHES:
                        return queries
    return queries


def _official_docs_query_for_url(url: str) -> str:
    parsed = urlparse(url.rstrip(".,;"))
    if not parsed.netloc:
        return ""
    path_terms = " ".join(part for part in parsed.path.split("/") if part)
    query_parts = [parsed.netloc]
    if path_terms:
        query_parts.append(path_terms)
    query_parts.append("official docs API endpoint")
    return " ".join(query_parts)


def build_inline_review_comments(report: ReviewReport | None) -> list[InlineReviewComment]:
    if report is None:
        return []
    comments: list[InlineReviewComment] = []
    for finding in report.findings:
        comments.extend(
            _inline_comments_from_evidence(
                finding.evidence,
                f"XEngineer AI risk: {finding.title}\n\n{finding.explanation}",
            )
        )
    for suggestion in report.suggestions:
        comments.extend(
            _inline_comments_from_evidence(
                suggestion.evidence,
                f"XEngineer AI suggestion: {suggestion.title}\n\n{suggestion.body}",
            )
        )
    comments = _deduplicate_inline_comments(comments)
    if len(comments) > MAX_INLINE_REVIEW_COMMENTS:
        LOGGER.warning(
            "Inline review comments truncated from %s to %s.",
            len(comments),
            MAX_INLINE_REVIEW_COMMENTS,
        )
        return comments[:MAX_INLINE_REVIEW_COMMENTS]
    return comments


def _inline_comments_from_evidence(
    evidence: list[EvidenceReference],
    comment_body: str,
) -> list[InlineReviewComment]:
    comments: list[InlineReviewComment] = []
    for reference in evidence:
        comment = _inline_comment_from_evidence(reference, comment_body)
        if comment is not None:
            comments.append(comment)
    return comments


def _inline_comment_from_evidence(
    reference: EvidenceReference,
    comment_body: str,
) -> InlineReviewComment | None:
    if reference.kind != "code" or not reference.path or reference.line_start is None:
        return None
    raw_end = reference.line_end or reference.line_start
    line_start, line_end = sorted((reference.line_start, raw_end))
    start_line = line_start if line_start != line_end else None
    return InlineReviewComment(
        path=reference.path,
        body=comment_body,
        line=line_end,
        start_line=start_line,
    )


def _deduplicate_inline_comments(
    comments: list[InlineReviewComment],
) -> list[InlineReviewComment]:
    deduplicated: list[InlineReviewComment] = []
    seen: set[tuple[str, int, int | None, str]] = set()
    for comment in comments:
        key = (comment.path, comment.line, comment.start_line, comment.side)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(comment)
    return deduplicated


def _enrich_review_item_evidence(
    findings: list[ReviewFinding],
    suggestions: list[ReviewSuggestion],
    pr: PullRequestData,
    file_ids: dict[str, str],
) -> None:
    files_by_path = {file.path: file for file in pr.files}
    for item in [*findings, *suggestions]:
        item.files = _normalize_item_files(item.files, file_ids, files_by_path)
        _hydrate_code_evidence_urls(item.evidence, pr, file_ids, files_by_path)
        for path in item.files:
            if not _has_code_evidence_for_path(item.evidence, path):
                item.evidence.extend(_code_evidence_for_path(path, files_by_path, pr))


def _hydrate_web_evidence(
    findings: list[ReviewFinding],
    suggestions: list[ReviewSuggestion],
    web_sources: list[EvidenceReference],
) -> None:
    if not web_sources:
        return
    by_label = {source.label: source for source in web_sources if source.label}
    by_url = {source.url: source for source in web_sources if source.url}
    for item in [*findings, *suggestions]:
        hydrated: list[EvidenceReference] = []
        for reference in item.evidence:
            if reference.kind != "web":
                hydrated.append(reference)
                continue
            source = by_label.get(reference.label) or by_url.get(reference.url)
            if source is None:
                hydrated.append(reference)
                continue
            hydrated.append(
                reference.model_copy(
                    update={
                        "label": reference.label or source.label,
                        "url": reference.url or source.url,
                        "title": reference.title or source.title,
                        "snippet": reference.snippet or source.snippet,
                    }
                )
            )
        item.evidence = hydrated


def _hydrate_code_evidence_urls(
    evidence: list[EvidenceReference],
    pr: PullRequestData,
    file_ids: dict[str, str],
    files_by_path: dict[str, ChangedFile],
) -> None:
    hydrated: list[EvidenceReference] = []
    for reference in evidence:
        if reference.kind != "code":
            hydrated.append(reference)
            continue
        file_id = reference.file_id
        path = reference.path
        if path in file_ids:
            file_id = file_id or path
            path = file_ids[path]
        elif not path and file_id:
            path = file_ids.get(file_id, "")
        if not path or path not in files_by_path:
            continue
        if not _line_range_fits_changed_file(reference, files_by_path[path]):
            continue
        if reference.url and reference.path and reference.path not in file_ids:
            hydrated.append(_without_code_snippet(reference))
            continue
        hydrated.append(
            reference.model_copy(
                update={
                    "file_id": file_id,
                    "path": path,
                    "url": reference.url
                    or _github_blob_url(pr, path, reference.line_start, reference.line_end),
                    "snippet": "",
                }
            )
        )
    evidence[:] = hydrated


def _line_range_fits_changed_file(
    reference: EvidenceReference,
    changed_file: ChangedFile,
) -> bool:
    if reference.line_start is None:
        return True
    if not changed_file.line_ranges:
        return False
    raw_end = reference.line_end or reference.line_start
    line_start, line_end = sorted((reference.line_start, raw_end))
    return any(
        line_start >= range_start and line_end <= range_end
        for range_start, range_end in changed_file.line_ranges
    )


def _normalize_item_files(
    paths: list[str],
    file_ids: dict[str, str],
    files_by_path: dict[str, ChangedFile],
) -> list[str]:
    normalized: list[str] = []
    for path in paths:
        mapped = file_ids.get(path, path)
        if mapped not in files_by_path or mapped in normalized:
            continue
        normalized.append(mapped)
    return normalized


def _without_code_snippet(reference: EvidenceReference) -> EvidenceReference:
    if not reference.snippet:
        return reference
    return reference.model_copy(update={"snippet": ""})


def _has_code_evidence_for_path(evidence: list[EvidenceReference], path: str) -> bool:
    return any(reference.kind == "code" and reference.path == path for reference in evidence)


def _code_evidence_for_path(
    path: str,
    files_by_path: dict[str, ChangedFile],
    pr: PullRequestData,
) -> list[EvidenceReference]:
    changed_file = files_by_path.get(path)
    line_ranges = changed_file.line_ranges if changed_file is not None else ()
    if not line_ranges:
        return [
            EvidenceReference(
                kind="code",
                path=path,
                url=_github_blob_url(pr, path, None, None),
            )
        ]
    return [
        EvidenceReference(
            kind="code",
            path=path,
            line_start=start,
            line_end=end,
            url=_github_blob_url(pr, path, start, end),
        )
        for start, end in line_ranges
    ]


def _github_blob_url(
    pr: PullRequestData,
    path: str,
    line_start: int | None,
    line_end: int | None,
) -> str:
    git_ref = pr.head_sha or pr.head_branch
    encoded_path = quote(path.strip("/"), safe="/")
    url = f"https://github.com/{pr.ref.owner}/{pr.ref.repo}/blob/{git_ref}/{encoded_path}"
    if line_start is None:
        return url
    if line_end is not None and line_end != line_start:
        return f"{url}#L{line_start}-L{line_end}"
    return f"{url}#L{line_start}"
