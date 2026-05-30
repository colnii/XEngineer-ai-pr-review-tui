from __future__ import annotations

import re

from xengineer_pr_review.models import ChangedFile


HUNK_HEADER_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(diff_text: str) -> tuple[ChangedFile, ...]:
    files: list[ChangedFile] = []
    current_path: str | None = None
    additions = 0
    deletions = 0
    hunk_lines: list[str] = []
    line_ranges: list[tuple[int, int]] = []

    def flush() -> None:
        nonlocal additions, deletions, hunk_lines, line_ranges, current_path
        if current_path is not None:
            files.append(
                ChangedFile(
                    path=current_path,
                    additions=additions,
                    deletions=deletions,
                    hunks=("\n".join(hunk_lines),) if hunk_lines else (),
                    line_ranges=tuple(line_ranges),
                )
            )
        current_path = None
        additions = 0
        deletions = 0
        hunk_lines = []
        line_ranges = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            current_path = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else None
            continue
        if current_path is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
            hunk_lines.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            hunk_lines.append(line)
        elif line.startswith("@@"):
            line_ranges.extend(_line_ranges_from_hunk_header(line))
            hunk_lines.append(line)
        elif line.startswith(" "):
            hunk_lines.append(line)

    flush()
    return tuple(files)


def _line_ranges_from_hunk_header(line: str) -> list[tuple[int, int]]:
    match = HUNK_HEADER_PATTERN.match(line)
    if not match:
        return []
    start = int(match.group(1))
    count = int(match.group(2) or "1")
    end = start + max(count, 1) - 1
    return [(start, end)]
