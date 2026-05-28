from __future__ import annotations

from xengineer_pr_review.models import ReviewReport


def render_markdown(report: ReviewReport) -> str:
    lines: list[str] = [
        "# AI PR Review Report",
        "",
        f"- PR: [{report.pr_title}]({report.pr_url})",
        "",
        "## Summary",
        "",
        report.summary,
        "",
        "## Risks",
        "",
    ]

    if report.findings:
        for finding in report.findings:
            files = ", ".join(finding.files) if finding.files else "n/a"
            lines.extend(
                [
                    f"- **{finding.severity.upper()}** {finding.title}: {finding.explanation}",
                    f"  - Files: {files}",
                ]
            )
    else:
        lines.append("- No deterministic risk findings.")

    lines.extend(["", "## Suggestions", ""])
    if report.suggestions:
        for suggestion in report.suggestions:
            files = ", ".join(suggestion.files) if suggestion.files else "n/a"
            lines.extend(
                [
                    f"- **{suggestion.severity.upper()}** {suggestion.title}: {suggestion.body}",
                    f"  - Files: {files}",
                ]
            )
    else:
        lines.append("- No AI suggestions were generated.")

    lines.extend(["", "## Changed Files", ""])
    lines.extend(f"- `{path}`" for path in report.changed_files)

    if report.omitted_files:
        lines.extend(["", "## Omitted Files", ""])
        lines.extend(f"- `{path}`" for path in report.omitted_files)

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines).rstrip() + "\n"
