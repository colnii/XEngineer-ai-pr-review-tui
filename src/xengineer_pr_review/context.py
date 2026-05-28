from __future__ import annotations

from dataclasses import dataclass

from xengineer_pr_review.models import PullRequestData, ReviewFinding


@dataclass(frozen=True)
class LLMContext:
    prompt: str
    omitted_files: list[str]


def build_llm_context(
    pr: PullRequestData,
    findings: list[ReviewFinding],
    max_files: int = 8,
    max_hunk_chars: int = 3000,
) -> LLMContext:
    included = list(pr.files[:max_files])
    omitted = [file.path for file in pr.files[max_files:]]
    finding_lines = [
        f"- {finding.severity}: {finding.title} ({', '.join(finding.files)})"
        for finding in findings
    ]
    file_blocks: list[str] = []

    for file in included:
        hunk_text = "\n".join(file.hunks)
        if len(hunk_text) > max_hunk_chars:
            hunk_text = hunk_text[:max_hunk_chars] + "\n[truncated]"
        file_blocks.append(
            f"File: {file.path}\nAdditions: {file.additions}, Deletions: {file.deletions}\n{hunk_text}"
        )

    prompt = "\n\n".join(
        [
            f"PR title: {pr.title}",
            f"Author: {pr.author}",
            f"Branches: {pr.base_branch} <- {pr.head_branch}",
            "Rule findings:\n" + ("\n".join(finding_lines) if finding_lines else "- none"),
            "Changed files:\n" + "\n\n".join(file_blocks),
            "Return concise review output with summary, risks, and reviewer suggestions.",
        ]
    )
    return LLMContext(prompt=prompt, omitted_files=omitted)
