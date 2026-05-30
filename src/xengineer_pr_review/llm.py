from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
import re
from typing import Any

from xengineer_pr_review.locale import normalize_language, prompt_language_instruction
from xengineer_pr_review.models import ReviewFinding, ReviewSuggestion


@dataclass(frozen=True)
class LLMResult:
    summary: str = ""
    risks: list[ReviewFinding] = field(default_factory=list)
    suggestions: list[ReviewSuggestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: str = ""
    raw_output: str = ""


SECTION_ALIASES = {
    "summary": "summary",
    "risk": "risks",
    "risks": "risks",
    "risk assessment": "risks",
    "ai identified risks": "risks",
    "suggestion": "suggestions",
    "suggestions": "suggestions",
    "review suggestions": "suggestions",
    "uncertainty": "notes",
    "uncertainty notes": "notes",
    "notes": "notes",
    "ai notes": "notes",
}

VALID_SEVERITIES = {"high", "medium", "low"}
VALID_SUGGESTION_TYPES = {"comment", "test", "maintainability", "edge-case"}
VALID_CONFIDENCE = {"high", "medium", "low"}
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def parse_llm_output(text: str) -> LLMResult:
    cleaned = _strip_outer_code_fence(text.strip())
    if not cleaned:
        return LLMResult(
            summary="AI review returned no content.",
            warnings=["LLM output was empty."],
            raw_output=text,
        )

    for candidate in _json_output_candidates(cleaned):
        json_result = _parse_json_output(candidate)
        if json_result is not None:
            return json_result

    markdown_result = _parse_markdown_output(cleaned)
    if markdown_result is not None:
        return markdown_result

    return LLMResult(
        summary="AI review returned unstructured notes.",
        warnings=["LLM output could not be parsed into structured sections."],
        raw_output=cleaned,
    )


class MockLLMClient:
    def __init__(self, language: str = "zh") -> None:
        self.language = normalize_language(language)

    def analyze(self, prompt: str) -> LLMResult:
        if self.language == "en":
            return LLMResult(
                summary="Mock summary: this PR changes code that should be reviewed for behavior and tests.",
                risks=[
                    ReviewFinding(
                        severity="low",
                        source="ai",
                        title="Manual behavior review recommended",
                        explanation=(
                            "The mock reviewer cannot inspect runtime behavior beyond the provided diff."
                        ),
                        files=[],
                    )
                ],
                suggestions=[
                    ReviewSuggestion(
                        severity="medium",
                        suggestion_type="test",
                        title="Review behavior and tests",
                        body=(
                            "Check whether the changed code has enough test coverage and "
                            "preserves compatibility."
                        ),
                        files=[],
                        confidence="medium",
                    )
                ],
            )
        return LLMResult(
            summary="模拟摘要：这个 PR 修改了代码，需要重点复核行为变化和测试覆盖。",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="建议人工复核行为",
                    explanation="模拟审查器只能基于提供的 diff 判断，无法检查真实运行时行为。",
                    files=[],
                )
            ],
            suggestions=[
                ReviewSuggestion(
                    severity="medium",
                    suggestion_type="test",
                    title="复核行为和测试",
                    body="检查变更是否有足够测试覆盖，并确认兼容性没有被破坏。",
                    files=[],
                    confidence="medium",
                )
            ],
        )


def _review_system_message(language: str) -> str:
    return (
        "You are a pragmatic senior engineer reviewing a GitHub PR. "
        "Return a compact JSON object with keys: summary, risks, suggestions, notes. "
        "Risk items must include severity, title, explanation, and files. "
        "Suggestion items must include type, text, related_file, and confidence. "
        f"{prompt_language_instruction(language)}"
    )


def build_review_system_message(language: str) -> str:
    return _review_system_message(language)


def _parse_json_output(text: str) -> LLMResult | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    summary = _clean_text(payload.get("summary") or payload.get("overview") or "")
    risks = [_risk_from_mapping(item) for item in _coerce_list(payload.get("risks"))]
    suggestions = [
        _suggestion_from_mapping(item) for item in _coerce_list(payload.get("suggestions"))
    ]
    notes = _clean_text(
        payload.get("notes")
        or payload.get("uncertainty")
        or payload.get("uncertainty_notes")
        or ""
    )
    warnings: list[str] = []
    if not summary:
        summary = "AI review returned structured output without a summary."
        warnings.append("LLM JSON output did not include a summary.")
    return LLMResult(
        summary=summary,
        risks=[risk for risk in risks if risk is not None],
        suggestions=[suggestion for suggestion in suggestions if suggestion is not None],
        warnings=warnings,
        notes=notes,
    )


def _parse_markdown_output(text: str) -> LLMResult | None:
    sections = _split_markdown_sections(text)
    if not sections:
        return None

    summary = _first_paragraph(sections.get("summary", ""))
    risks = _parse_risk_items(sections.get("risks", ""))
    suggestions = _parse_suggestion_items(sections.get("suggestions", ""))
    notes = _clean_text(sections.get("notes", ""))
    warnings: list[str] = []

    if not summary:
        summary = "AI review returned structured output without a summary."
        warnings.append("LLM Markdown output did not include a summary.")

    return LLMResult(
        summary=summary,
        risks=risks,
        suggestions=suggestions,
        warnings=warnings,
        notes=notes,
    )


def _strip_outer_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 2 or not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


def _json_output_candidates(text: str) -> list[str]:
    candidates = [text]
    fence_pattern = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*(.*?)```", re.DOTALL)
    for match in fence_pattern.finditer(text):
        fenced = match.group(1).strip()
        if fenced:
            candidates.append(fenced)
    return candidates


def _split_markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    heading_pattern = re.compile(r"^#{1,6}\s+(.+?)\s*$")

    for line in text.splitlines():
        match = heading_pattern.match(line.strip())
        if match:
            heading = _normalize_heading(match.group(1))
            current = SECTION_ALIASES.get(heading)
            if current is not None:
                sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _normalize_heading(value: str) -> str:
    cleaned = re.sub(r"[*_`:#]+", "", value).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _parse_risk_items(text: str) -> list[ReviewFinding]:
    return [_risk_from_text(item) for item in _markdown_items(text)]


def _parse_suggestion_items(text: str) -> list[ReviewSuggestion]:
    return [_suggestion_from_text(item) for item in _markdown_items(text)]


def _markdown_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        bullet_match = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", stripped)
        if bullet_match:
            if current:
                items.append(_clean_text(" ".join(current)))
            current = [bullet_match.group(1)]
        elif current:
            current.append(stripped)
    if current:
        items.append(_clean_text(" ".join(current)))
    if items:
        return items
    cleaned = _clean_text(text)
    return [cleaned] if cleaned else []


def _risk_from_mapping(item: Any) -> ReviewFinding | None:
    if isinstance(item, str):
        return _risk_from_text(item)
    if not isinstance(item, dict):
        return None
    explanation = _clean_text(item.get("explanation") or item.get("body") or item.get("text") or "")
    title = _clean_text(item.get("title") or _title_from_text(explanation) or "AI-identified risk")
    return ReviewFinding(
        severity=_severity(item.get("severity")),
        source="ai",
        title=title,
        explanation=explanation or title,
        files=_files_from_value(item.get("files") or item.get("related_files") or item.get("related_file")),
    )


def _suggestion_from_mapping(item: Any) -> ReviewSuggestion | None:
    if isinstance(item, str):
        return _suggestion_from_text(item)
    if not isinstance(item, dict):
        return None
    body = _clean_text(item.get("body") or item.get("text") or item.get("suggestion") or "")
    suggestion_type = _suggestion_type(item.get("type") or item.get("category"))
    return ReviewSuggestion(
        severity=_severity(item.get("severity"), default="medium"),
        suggestion_type=suggestion_type,
        title=_clean_text(item.get("title") or _title_from_text(body) or suggestion_type.title()),
        body=body or "Review this item manually.",
        files=_files_from_value(item.get("files") or item.get("related_files") or item.get("related_file")),
        confidence=_confidence(item.get("confidence")),
    )


def _risk_from_text(text: str) -> ReviewFinding:
    body = _clean_text(_remove_inline_metadata(text))
    severity = _severity(_extract_labeled_value(text, "severity") or _leading_label(text))
    title, explanation = _split_title_body(body)
    return ReviewFinding(
        severity=severity,
        source="ai",
        title=title,
        explanation=explanation,
        files=_extract_files(text),
    )


def _suggestion_from_text(text: str) -> ReviewSuggestion:
    body = _clean_text(_remove_inline_metadata(text))
    suggestion_type = _suggestion_type(_extract_labeled_value(text, "type") or _leading_label(text))
    title, explanation = _split_title_body(body)
    return ReviewSuggestion(
        severity="medium",
        suggestion_type=suggestion_type,
        title=title,
        body=explanation,
        files=_extract_files(text),
        confidence=_confidence(_extract_labeled_value(text, "confidence")),
    )


def _split_title_body(text: str) -> tuple[str, str]:
    text = re.sub(r"^(high|medium|low|comment|test|maintainability|edge-case)\s*:\s*", "", text, flags=re.I)
    if ":" in text:
        title, body = text.split(":", 1)
    elif " - " in text:
        title, body = text.split(" - ", 1)
    else:
        title, body = text, text
    title = _title_from_text(title) or "AI review note"
    body = _clean_text(body) or title
    return title, body


def _first_paragraph(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return ""
    return _clean_text(paragraphs[0])


def _title_from_text(text: str) -> str:
    cleaned = _clean_text(text).rstrip(".")
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0].rstrip(".")
    if len(sentence) <= 96:
        return sentence
    return sentence[:93].rstrip() + "..."


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _files_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return []


def _extract_files(text: str) -> list[str]:
    labeled_matches = re.findall(
        r"\bFiles?\s*:\s*([^\n]+?)(?=\s+\b(?:Confidence|Severity|Type)\b\s*:|$)",
        text,
        re.I,
    )
    if labeled_matches:
        labeled = labeled_matches[-1].strip().rstrip(".;")
        return [item.strip("` ") for item in re.split(r"[, ]+", labeled) if item.strip("` ")]
    return [match.strip("`") for match in re.findall(r"`?[\w./-]+\.[\w-]+`?", text)]


def _extract_labeled_value(text: str, label: str) -> str:
    match = re.search(rf"\b{re.escape(label)}\s*:\s*([^.;\n]+)", text, re.I)
    return _clean_text(match.group(1)) if match else ""


def _leading_label(text: str) -> str:
    match = re.match(r"\s*([A-Za-z-]+)\s*:", text)
    return _clean_text(match.group(1)) if match else ""


def _remove_inline_metadata(text: str) -> str:
    text = re.sub(
        r"\bFile(?:s)?\s*:\s*[^\n]+?(?=\s+\bConfidence\b\s*:|$)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bConfidence\s*:\s*(high|medium|low)[.;]?", "", text, flags=re.I)
    text = re.sub(r"\bSeverity\s*:\s*(high|medium|low)[.;]?", "", text, flags=re.I)
    return text


def _severity(value: Any, default: str = "medium") -> str:
    cleaned = _clean_text(value).lower()
    return cleaned if cleaned in VALID_SEVERITIES else default


def _suggestion_type(value: Any) -> str:
    cleaned = _clean_text(value).lower()
    if cleaned in VALID_SUGGESTION_TYPES:
        return cleaned
    if cleaned in {"edge", "edge case", "edgecase"}:
        return "edge-case"
    return "maintainability"


def _confidence(value: Any) -> str:
    cleaned = _clean_text(value).lower()
    return cleaned if cleaned in VALID_CONFIDENCE else "medium"
