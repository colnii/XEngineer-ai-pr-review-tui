from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from xengineer_pr_review.models import (
    ChangedFile,
    PullRequestActivity,
    PullRequestData,
    ReviewFinding,
)

LOW_SIGNAL_FILENAMES = {
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.sum",
    "package-lock.json",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
LOW_SIGNAL_PATH_PARTS = {
    ".cache",
    ".next",
    ".nuxt",
    ".pytest_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
LOW_SIGNAL_SUFFIXES = (
    ".generated.css",
    ".generated.js",
    ".generated.ts",
    ".gen.go",
    ".map",
    ".min.css",
    ".min.js",
    "_pb2.py",
)
LOW_SIGNAL_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bmp",
    ".br",
    ".bz2",
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".tar",
    ".tgz",
    ".ttf",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}


@dataclass(frozen=True)
class LLMContext:
    prompt: str
    omitted_files: list[str]
    file_ids: dict[str, str]


def build_llm_context(
    pr: PullRequestData,
    findings: list[ReviewFinding],
    max_files: int | None = None,
    max_hunk_chars: int = 3000,
) -> LLMContext:
    included: list[ChangedFile] = []
    omitted: list[str] = []
    for file in pr.files:
        if _has_review_signal(file.path):
            included.append(file)
        else:
            omitted.append(file.path)
    if max_files is not None:
        omitted.extend(file.path for file in included[max_files:])
        included = included[:max_files]
    file_ids = {
        f"F{index}": file.path
        for index, file in enumerate(included, start=1)
    }
    file_id_by_path = {path: file_id for file_id, path in file_ids.items()}

    finding_lines = [
        f"- {finding.severity}: {finding.title} ({', '.join(finding.files)})"
        for finding in findings
    ]
    file_index_lines = [
        f"- {file_id}: {path}"
        for file_id, path in file_ids.items()
    ]
    file_blocks: list[str] = []
    activity_context = "\n".join(format_pr_activity_lines(pr.activities))
    if pr.activities:
        activity_context = "\n".join(
            [
                (
                    "If prior PR comments, reviews, commits, or timeline events affect your "
                    "review, call read_pr_activity to get citeable [A1] IDs and cite those IDs "
                    "as pr_activity evidence in the final JSON."
                ),
                activity_context,
            ]
        )

    for file in included:
        hunk_text = "\n".join(file.hunks)
        if len(hunk_text) > max_hunk_chars:
            hunk_text = hunk_text[:max_hunk_chars] + "\n[truncated]"
        line_ranges = _format_line_ranges(file.line_ranges)
        file_blocks.append(
            f"File ID: {file_id_by_path[file.path]}\n"
            f"File: {file.path}\n"
            f"Additions: {file.additions}, Deletions: {file.deletions}\n"
            f"Changed line ranges: {line_ranges}\n"
            f"{hunk_text}"
        )

    prompt = "\n\n".join(
        [
            f"PR title: {pr.title}",
            f"Author: {pr.author}",
            f"Branches: {pr.base_branch} <- {pr.head_branch}",
            "Rule findings:\n" + ("\n".join(finding_lines) if finding_lines else "- none"),
            "PR activity history:\n" + activity_context,
            "Changed file index:\n" + ("\n".join(file_index_lines) if file_index_lines else "- none"),
            "Changed files:\n" + "\n\n".join(file_blocks),
            "Return concise review output with summary, risks, and reviewer suggestions.",
        ]
    )
    return LLMContext(prompt=prompt, omitted_files=omitted, file_ids=file_ids)


def _has_review_signal(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    lower_path = normalized.lower()
    lower_name = parsed.name.lower()
    path_parts = {part.lower() for part in parsed.parts}

    if lower_name in LOW_SIGNAL_FILENAMES:
        return False
    if path_parts & LOW_SIGNAL_PATH_PARTS:
        return False
    if lower_path.endswith(LOW_SIGNAL_SUFFIXES):
        return False
    return parsed.suffix.lower() not in LOW_SIGNAL_EXTENSIONS


def has_review_signal(path: str) -> bool:
    return _has_review_signal(path)


def format_pr_activity_lines(
    activities: tuple[PullRequestActivity, ...],
    max_items: int = 200,
    max_body_chars: int = 1200,
) -> list[str]:
    if not activities:
        return ["- none"]
    lines = [
        _format_activity(activity, max_body_chars=max_body_chars)
        for activity in activities[:max_items]
    ]
    if len(activities) > max_items:
        lines.append(f"- [truncated {len(activities) - max_items} additional PR activity items]")
    return lines


def _format_activity(activity: PullRequestActivity, max_body_chars: int) -> str:
    if activity.kind == "commit":
        prefix = f"commit {activity.commit_sha or 'unknown'} by {activity.author or 'unknown'}"
    elif activity.kind == "event":
        event_name = activity.event or activity.state or "unknown"
        prefix = f"event {event_name} by {activity.author or 'unknown'}"
    else:
        prefix = f"{activity.kind} by {activity.author or 'unknown'}"
    if activity.state:
        prefix += f" [{activity.state}]"
    if activity.path:
        prefix += f" on {activity.path}"
        if activity.line is not None:
            prefix += f":{activity.line}"
    if activity.created_at:
        prefix += f" at {activity.created_at}"

    body = _trim_activity_body(activity.body, max_body_chars)
    if activity.url:
        body = f"{body} ({activity.url})" if body else activity.url
    return f"- {prefix}: {body}" if body else f"- {prefix}"


def _trim_activity_body(body: str, max_body_chars: int) -> str:
    cleaned = " ".join(body.split())
    if len(cleaned) <= max_body_chars:
        return cleaned
    return cleaned[:max_body_chars].rstrip() + " [truncated]"


def _format_line_ranges(line_ranges: tuple[tuple[int, int], ...]) -> str:
    if not line_ranges:
        return "unknown"
    return ", ".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in line_ranges
    )
