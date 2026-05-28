from __future__ import annotations

from xengineer_pr_review.models import ChangedFile


def parse_unified_diff(diff_text: str) -> tuple[ChangedFile, ...]:
    files: list[ChangedFile] = []
    current_path: str | None = None
    additions = 0
    deletions = 0
    hunk_lines: list[str] = []

    def flush() -> None:
        nonlocal additions, deletions, hunk_lines, current_path
        if current_path is not None:
            files.append(
                ChangedFile(
                    path=current_path,
                    additions=additions,
                    deletions=deletions,
                    hunks=("\n".join(hunk_lines),) if hunk_lines else (),
                )
            )
        current_path = None
        additions = 0
        deletions = 0
        hunk_lines = []

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
        elif line.startswith("@@") or line.startswith(" "):
            hunk_lines.append(line)

    flush()
    return tuple(files)
