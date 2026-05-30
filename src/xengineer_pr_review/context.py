from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from xengineer_pr_review.models import ChangedFile, PullRequestData, ReviewFinding

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


def _format_line_ranges(line_ranges: tuple[tuple[int, int], ...]) -> str:
    if not line_ranges:
        return "unknown"
    return ", ".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in line_ranges
    )
