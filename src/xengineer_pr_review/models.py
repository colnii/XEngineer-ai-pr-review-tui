from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["high", "medium", "low"]
FindingSource = Literal["rule", "ai"]
SuggestionType = Literal["comment", "test", "maintainability", "edge-case"]
Confidence = Literal["high", "medium", "low"]
EvidenceKind = Literal["code", "web", "pr_activity"]
PullRequestActivityKind = Literal["commit", "conversation", "review", "inline", "event"]
ReviewAction = Literal["comment", "approve", "request-changes"]
ReviewCommentSide = Literal["LEFT", "RIGHT"]


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


@dataclass(frozen=True)
class ChangedFile:
    path: str
    additions: int = 0
    deletions: int = 0
    hunks: tuple[str, ...] = ()
    line_ranges: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class PullRequestActivity:
    kind: PullRequestActivityKind
    author: str = ""
    body: str = ""
    created_at: str = ""
    url: str = ""
    state: str = ""
    event: str = ""
    path: str = ""
    line: int | None = None
    commit_sha: str = ""


@dataclass(frozen=True)
class PullRequestData:
    ref: PullRequestRef
    title: str
    author: str
    base_branch: str
    head_branch: str
    files: tuple[ChangedFile, ...]
    diff_text: str
    head_sha: str = ""
    activities: tuple[PullRequestActivity, ...] = ()


@dataclass(frozen=True)
class PostedComment:
    html_url: str


@dataclass(frozen=True)
class InlineReviewComment:
    """Line-level PR review comment payload for GitHub's review comments array."""

    path: str
    body: str
    line: int
    side: ReviewCommentSide = "RIGHT"
    start_line: int | None = None
    start_side: ReviewCommentSide | None = None


class EvidenceReference(BaseModel):
    kind: EvidenceKind = "code"
    file_id: str = ""
    label: str = ""
    path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    url: str = ""
    title: str = ""
    snippet: str = ""


class ReviewFinding(BaseModel):
    severity: Severity
    source: FindingSource = "rule"
    title: str
    explanation: str
    files: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ReviewSuggestion(BaseModel):
    severity: Severity
    suggestion_type: SuggestionType = "maintainability"
    title: str
    body: str
    files: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ReviewReport(BaseModel):
    pr_title: str
    pr_url: str
    repo: str = ""
    pr_number: int | None = None
    head_sha: str = ""
    author: str = ""
    additions: int = 0
    deletions: int = 0
    summary: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    suggestions: list[ReviewSuggestion] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    llm_status: str = "unknown"
    ai_notes: str = ""
    raw_ai_output: str = ""
