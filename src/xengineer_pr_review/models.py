from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["high", "medium", "low"]


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


@dataclass(frozen=True)
class PullRequestData:
    ref: PullRequestRef
    title: str
    author: str
    base_branch: str
    head_branch: str
    files: tuple[ChangedFile, ...]
    diff_text: str


class ReviewFinding(BaseModel):
    severity: Severity
    title: str
    explanation: str
    files: list[str] = Field(default_factory=list)


class ReviewSuggestion(BaseModel):
    severity: Severity
    title: str
    body: str
    files: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    pr_title: str
    pr_url: str
    summary: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    suggestions: list[ReviewSuggestion] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
