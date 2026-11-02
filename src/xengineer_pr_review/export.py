from __future__ import annotations

from xengineer_pr_review.locale import (
    display_confidence,
    display_llm_status,
    display_severity,
    display_source,
    display_suggestion_type,
    label,
    normalize_language,
    translate_builtin_text,
)
from xengineer_pr_review.models import EvidenceReference, ReviewFinding, ReviewReport, ReviewSuggestion


def render_markdown(report: ReviewReport, language: str = "zh") -> str:
    language = normalize_language(language)
    ai_risks = [finding for finding in report.findings if finding.source == "ai"]
    rule_signals = [finding for finding in report.findings if finding.source == "rule"]
    review_mode_key = "mode.rules_llm" if report.llm_status != "failed" else "mode.rules_only"
    unknown = label("common.unknown", language)
    lines: list[str] = [
        f"# {label('report.title', language)}",
        "",
        f"- {label('report.pr', language)}: [{report.pr_title}]({report.pr_url})",
        f"- {label('report.repository', language)}: {report.repo or unknown}",
        f"- {label('report.pr_number', language)}: "
        f"{report.pr_number if report.pr_number is not None else unknown}",
        f"- {label('report.author', language)}: {report.author or unknown}",
        f"- {label('report.files_changed', language)}: {len(report.changed_files)}",
        f"- {label('report.additions_deletions', language)}: "
        f"+{report.additions} / -{report.deletions}",
        f"- {label('report.review_mode', language)}: {label(review_mode_key, language)}",
        f"- {label('report.llm_status', language)}: "
        f"{display_llm_status(report.llm_status, language)}",
        "",
        f"## {label('report.summary', language)}",
        "",
        report.summary,
        "",
        f"## {label('report.risk_assessment', language)}",
        "",
        f"### {label('report.ai_risks', language)}",
        "",
    ]

    if ai_risks:
        for finding in ai_risks:
            lines.extend(_render_finding(finding, language))
    else:
        lines.append(f"- {label('report.no_ai_risks', language)}")

    lines.extend(["", f"### {label('report.rule_signals', language)}", ""])
    if rule_signals:
        for finding in rule_signals:
            lines.extend(_render_finding(finding, language))
    else:
        lines.append(f"- {label('report.no_rule_signals', language)}")

    lines.extend(["", f"## {label('report.review_suggestions', language)}", ""])
    if report.suggestions:
        for suggestion in report.suggestions:
            lines.extend(_render_suggestion(suggestion, language))
    else:
        lines.append(f"- {label('report.no_ai_suggestions', language)}")

    lines.extend(["", f"## {label('report.changed_files', language)}", ""])
    lines.extend(f"- `{path}`" for path in report.changed_files)

    lines.extend(["", f"## {label('report.coverage_notes', language)}", ""])
    if report.omitted_files:
        lines.append(label("report.omitted_files", language))
        lines.extend(f"- `{path}`" for path in report.omitted_files)
    else:
        lines.append(f"- {label('report.all_files_included', language)}")

    if report.ai_notes:
        lines.extend(["", f"## {label('report.ai_notes', language)}", "", report.ai_notes])

    if report.raw_ai_output:
        lines.extend(
            ["", f"## {label('report.raw_ai_output', language)}", "", report.raw_ai_output]
        )

    if report.warnings:
        lines.extend(["", f"## {label('report.warnings', language)}", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines).rstrip() + "\n"


def _render_finding(finding: ReviewFinding, language: str) -> list[str]:
    files = (
        ", ".join(f"`{path}`" for path in finding.files)
        if finding.files
        else label("common.none", language)
    )
    lines = [
        f"- **{label('report.severity', language)}:** "
        f"{display_severity(finding.severity, language)}",
        f"  - **{label('report.source', language)}:** "
        f"{display_source(finding.source, language)}",
        f"  - **{label('report.finding_title', language)}:** "
        f"{translate_builtin_text(finding.title, language)}",
        f"  - **{label('report.explanation', language)}:** "
        f"{translate_builtin_text(finding.explanation, language)}",
        f"  - **{label('report.related_files', language)}:** {files}",
    ]
    lines.extend(_render_evidence(finding.evidence, language))
    return lines


def _render_suggestion(suggestion: ReviewSuggestion, language: str) -> list[str]:
    files = (
        ", ".join(f"`{path}`" for path in suggestion.files)
        if suggestion.files
        else label("common.none", language)
    )
    lines = [
        f"- **{label('report.type', language)}:** "
        f"{display_suggestion_type(suggestion.suggestion_type, language)}",
        f"  - **{label('report.suggestion', language)}:** "
        f"{translate_builtin_text(suggestion.body, language)}",
        f"  - **{label('report.related_file', language)}:** {files}",
        f"  - **{label('report.confidence', language)}:** "
        f"{display_confidence(suggestion.confidence, language)}",
    ]
    lines.extend(_render_evidence(suggestion.evidence, language))
    return lines


def _render_evidence(evidence: list[EvidenceReference], language: str) -> list[str]:
    if not evidence:
        return []
    return [
        f"  - **{label('report.evidence', language)}:**",
        *[f"    - {_format_evidence(reference)}" for reference in evidence],
    ]


def _format_evidence(reference: EvidenceReference) -> str:
    if reference.kind == "web":
        return _format_web_evidence(reference)
    if reference.kind == "pr_activity":
        return _format_pr_activity_evidence(reference)
    return _format_code_evidence(reference)


def _format_code_evidence(reference: EvidenceReference) -> str:
    location = reference.path or "unknown"
    if reference.line_start is not None:
        if reference.line_end is not None and reference.line_end != reference.line_start:
            location = f"{location}:{reference.line_start}-{reference.line_end}"
        else:
            location = f"{location}:{reference.line_start}"
    text = f"`{location}`"
    if reference.url:
        text = f"[{text}]({reference.url})"
    if reference.snippet:
        text += f" - {reference.snippet}"
    return text


def _format_web_evidence(reference: EvidenceReference) -> str:
    label_text = f"[{reference.label}] " if reference.label else ""
    title = reference.title or reference.url or "Web source"
    if reference.url:
        text = f"{label_text}[{title}]({reference.url})"
    else:
        text = f"{label_text}{title}"
    if reference.snippet:
        text += f" - {reference.snippet}"
    return text


def _format_pr_activity_evidence(reference: EvidenceReference) -> str:
    label_text = f"[{reference.label}] " if reference.label else ""
    title = reference.title or reference.url or "PR activity"
    if reference.url:
        text = f"{label_text}[{title}]({reference.url})"
    else:
        text = f"{label_text}{title}"
    if reference.snippet:
        text += f" - {reference.snippet}"
    return text
