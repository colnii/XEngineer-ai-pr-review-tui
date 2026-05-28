from __future__ import annotations

from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion


def render_markdown(report: ReviewReport) -> str:
    ai_risks = [finding for finding in report.findings if finding.source == "ai"]
    rule_signals = [finding for finding in report.findings if finding.source == "rule"]
    review_mode = "Rules + LLM" if report.llm_status != "failed" else "Rules only"
    lines: list[str] = [
        "# AI PR Review Report",
        "",
        f"- PR: [{report.pr_title}]({report.pr_url})",
        f"- Repository: {report.repo or 'unknown'}",
        f"- PR number: {report.pr_number if report.pr_number is not None else 'unknown'}",
        f"- Author: {report.author or 'unknown'}",
        f"- Files changed: {len(report.changed_files)}",
        f"- Additions / deletions: +{report.additions} / -{report.deletions}",
        f"- Review mode: {review_mode}",
        f"- LLM status: {report.llm_status}",
        "",
        "## Summary",
        "",
        report.summary,
        "",
        "## Risk Assessment",
        "",
        "### AI-Identified Risks",
        "",
    ]

    if ai_risks:
        for finding in ai_risks:
            lines.extend(_render_finding(finding))
    else:
        lines.append("- No AI-identified risks were parsed.")

    lines.extend(["", "### Rule-Based Signals", ""])
    if rule_signals:
        for finding in rule_signals:
            lines.extend(_render_finding(finding))
    else:
        lines.append("- No deterministic risk signals.")

    lines.extend(["", "## Review Suggestions", ""])
    if report.suggestions:
        for suggestion in report.suggestions:
            lines.extend(_render_suggestion(suggestion))
    else:
        lines.append("- No AI suggestions were generated.")

    lines.extend(["", "## Changed Files", ""])
    lines.extend(f"- `{path}`" for path in report.changed_files)

    lines.extend(["", "## Coverage Notes", ""])
    if report.omitted_files:
        lines.append("The LLM prompt omitted these files because of context limits:")
        lines.extend(f"- `{path}`" for path in report.omitted_files)
    else:
        lines.append("- All changed files were included in the LLM context.")

    if report.ai_notes:
        lines.extend(["", "## AI Notes", "", report.ai_notes])

    if report.raw_ai_output:
        lines.extend(["", "## Raw AI Output", "", report.raw_ai_output])

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines).rstrip() + "\n"


def _render_finding(finding: ReviewFinding) -> list[str]:
    files = ", ".join(f"`{path}`" for path in finding.files) if finding.files else "n/a"
    return [
        f"- **Severity:** {finding.severity}",
        f"  - **Source:** {finding.source}",
        f"  - **Title:** {finding.title}",
        f"  - **Explanation:** {finding.explanation}",
        f"  - **Related files:** {files}",
    ]


def _render_suggestion(suggestion: ReviewSuggestion) -> list[str]:
    files = ", ".join(f"`{path}`" for path in suggestion.files) if suggestion.files else "n/a"
    return [
        f"- **Type:** {suggestion.suggestion_type}",
        f"  - **Suggestion:** {suggestion.body}",
        f"  - **Related file:** {files}",
        f"  - **Confidence:** {suggestion.confidence}",
    ]
