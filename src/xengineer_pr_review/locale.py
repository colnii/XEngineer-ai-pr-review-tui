from __future__ import annotations

import re
from typing import Literal


Language = Literal["zh", "en"]


LABELS: dict[str, dict[Language, str]] = {
    "common.none": {"zh": "无", "en": "n/a"},
    "common.unknown": {"zh": "未知", "en": "unknown"},
    "app.title": {"zh": "PR 审查助手", "en": "PR Review Assistant"},
    "button.analyze": {"zh": "分析", "en": "Analyze"},
    "button.export": {"zh": "导出", "en": "Export"},
    "button.publish": {"zh": "发布评论", "en": "Publish Comment"},
    "button.confirm_publish": {"zh": "确认发布", "en": "Confirm Publish"},
    "button.comment_mode_conversation": {"zh": "发布到对话", "en": "Conversation"},
    "button.comment_mode_review": {"zh": "发布为 PR Review", "en": "PR Review"},
    "button.inline_comments_off": {"zh": "行内评论：关", "en": "Inline: Off"},
    "button.inline_comments_on": {"zh": "行内评论：开", "en": "Inline: On"},
    "input.pr_url": {
        "zh": "粘贴公开 PR，或已配置 token 的私有 PR 地址",
        "en": "Paste public PR, or private PR with configured token",
    },
    "status.ready": {"zh": "状态：就绪", "en": "Status: Ready"},
    "status.running": {"zh": "状态：运行中", "en": "Status: Running"},
    "status.complete": {"zh": "状态：完成", "en": "Status: Complete"},
    "status.error": {"zh": "错误", "en": "Error"},
    "status.export_first": {"zh": "请先分析 PR 再导出", "en": "Analyze a PR before exporting"},
    "status.exported": {"zh": "已导出", "en": "Exported"},
    "status.publish_first": {
        "zh": "请先分析 PR 再发布评论",
        "en": "Analyze a PR before publishing a comment",
    },
    "status.publish_confirm": {
        "zh": (
            "即将把当前报告发布到 PR Conversation。需要 GitHub Issues: write "
            "或 Pull requests: write 权限；再次点击确认发布。"
        ),
        "en": (
            "This will publish the current report to the PR conversation. Requires "
            "GitHub Issues: write or Pull requests: write; click again to confirm."
        ),
    },
    "status.publish_confirm_review": {
        "zh": (
            "即将把当前报告发布为正式 PR Review。需要 GitHub Pull requests: write "
            "权限；再次点击确认发布。"
        ),
        "en": (
            "This will publish the current report as a pull request review. Requires "
            "GitHub Pull requests: write; click again to confirm."
        ),
    },
    "status.publish_confirm_review_inline": {
        "zh": (
            "即将发布正式 PR Review，并把有行号证据的 AI 发现挂到代码行上。"
            "需要 GitHub Pull requests: write 权限；再次点击确认发布。"
        ),
        "en": (
            "This will publish a pull request review and attach line comments for AI "
            "items with line evidence. Requires GitHub Pull requests: write; click again."
        ),
    },
    "status.publishing": {"zh": "正在发布 PR 评论...", "en": "Publishing PR comment..."},
    "status.published": {"zh": "已发布评论", "en": "Published comment"},
    "status.publish_failed": {"zh": "发布评论失败", "en": "Failed to publish comment"},
    "phase.fetch": {"zh": "获取 PR", "en": "Fetch PR"},
    "phase.parse": {"zh": "解析 Diff", "en": "Parse Diff"},
    "phase.rules": {"zh": "规则扫描", "en": "Rule Scan"},
    "phase.llm": {"zh": "LLM 审查", "en": "LLM Review"},
    "phase.render": {"zh": "渲染报告", "en": "Render Report"},
    "phase.done": {"zh": "完成", "en": "done"},
    "tab.overview": {"zh": "概览", "en": "Overview"},
    "tab.risks": {"zh": "风险", "en": "Risks"},
    "tab.suggestions": {"zh": "建议", "en": "Suggestions"},
    "tab.files": {"zh": "文件", "en": "Files"},
    "tab.raw": {"zh": "原始 / 调试", "en": "Raw / Debug"},
    "meta.changed_files": {"zh": "变更文件数", "en": "Changed files"},
    "meta.risk_count": {"zh": "风险数量", "en": "Risk count"},
    "meta.suggestion_count": {"zh": "建议数量", "en": "Suggestion count"},
    "meta.llm_status_idle": {"zh": "LLM 状态：空闲", "en": "LLM status: idle"},
    "overview.by": {"zh": "作者", "en": "by"},
    "overview.additions_deletions": {"zh": "新增/删除", "en": "Additions/deletions"},
    "overview.risks": {"zh": "风险", "en": "Risks"},
    "overview.suggestions": {"zh": "建议", "en": "Suggestions"},
    "tui.no_risks": {"zh": "未识别到风险。", "en": "No risks were identified."},
    "tui.no_files": {"zh": "未检测到变更文件。", "en": "No changed files detected."},
    "tui.no_raw": {
        "zh": "没有警告或原始降级输出。",
        "en": "No warnings or raw fallback output.",
    },
    "report.title": {"zh": "AI PR 审查报告", "en": "AI PR Review Report"},
    "report.pr": {"zh": "PR", "en": "PR"},
    "report.repository": {"zh": "仓库", "en": "Repository"},
    "report.pr_number": {"zh": "PR 编号", "en": "PR number"},
    "report.author": {"zh": "作者", "en": "Author"},
    "report.files_changed": {"zh": "变更文件数", "en": "Files changed"},
    "report.additions_deletions": {"zh": "新增 / 删除", "en": "Additions / deletions"},
    "report.review_mode": {"zh": "审查模式", "en": "Review mode"},
    "report.llm_status": {"zh": "LLM 状态", "en": "LLM status"},
    "report.summary": {"zh": "摘要", "en": "Summary"},
    "report.risk_assessment": {"zh": "风险评估", "en": "Risk Assessment"},
    "report.ai_risks": {"zh": "AI 识别的风险", "en": "AI-Identified Risks"},
    "report.rule_signals": {"zh": "规则信号", "en": "Rule-Based Signals"},
    "report.review_suggestions": {"zh": "审查建议", "en": "Review Suggestions"},
    "report.changed_files": {"zh": "变更文件", "en": "Changed Files"},
    "report.coverage_notes": {"zh": "覆盖说明", "en": "Coverage Notes"},
    "report.ai_notes": {"zh": "AI 备注", "en": "AI Notes"},
    "report.raw_ai_output": {"zh": "AI 原始输出", "en": "Raw AI Output"},
    "report.warnings": {"zh": "警告", "en": "Warnings"},
    "report.severity": {"zh": "严重程度", "en": "Severity"},
    "report.source": {"zh": "来源", "en": "Source"},
    "report.finding_title": {"zh": "标题", "en": "Title"},
    "report.explanation": {"zh": "说明", "en": "Explanation"},
    "report.related_files": {"zh": "相关文件", "en": "Related files"},
    "report.evidence": {"zh": "证据", "en": "Evidence"},
    "report.type": {"zh": "类型", "en": "Type"},
    "report.suggestion": {"zh": "建议", "en": "Suggestion"},
    "report.related_file": {"zh": "相关文件", "en": "Related file"},
    "report.confidence": {"zh": "置信度", "en": "Confidence"},
    "report.no_ai_risks": {
        "zh": "未解析到 AI 识别的风险。",
        "en": "No AI-identified risks were parsed.",
    },
    "report.no_rule_signals": {
        "zh": "没有确定性的规则风险信号。",
        "en": "No deterministic risk signals.",
    },
    "report.no_ai_suggestions": {
        "zh": "没有生成 AI 审查建议。",
        "en": "No AI suggestions were generated.",
    },
    "report.omitted_files": {
        "zh": "LLM prompt 省略了这些低信号、生成物或二进制文件：",
        "en": "The LLM prompt skipped these low-signal, generated, or binary files:",
    },
    "report.all_files_included": {
        "zh": "所有适合审查的变更文件都已包含在 LLM 上下文中。",
        "en": "All review-relevant changed files were included in the LLM context.",
    },
    "mode.rules_llm": {"zh": "规则 + LLM", "en": "Rules + LLM"},
    "mode.rules_only": {"zh": "仅规则", "en": "Rules only"},
}

SEVERITY_LABELS = {
    "high": {"zh": "高", "en": "high"},
    "medium": {"zh": "中", "en": "medium"},
    "low": {"zh": "低", "en": "low"},
}

SOURCE_LABELS = {
    "rule": {"zh": "规则", "en": "rule"},
    "ai": {"zh": "AI", "en": "ai"},
}

SUGGESTION_TYPE_LABELS = {
    "comment": {"zh": "评论", "en": "comment"},
    "test": {"zh": "测试", "en": "test"},
    "maintainability": {"zh": "可维护性", "en": "maintainability"},
    "edge-case": {"zh": "边界情况", "en": "edge-case"},
}

CONFIDENCE_LABELS = {
    "high": {"zh": "高", "en": "high"},
    "medium": {"zh": "中", "en": "medium"},
    "low": {"zh": "低", "en": "low"},
}

LLM_STATUS_LABELS = {
    "ok": {"zh": "正常", "en": "ok"},
    "failed": {"zh": "失败", "en": "failed"},
    "parsed_with_warnings": {"zh": "已解析但有警告", "en": "parsed_with_warnings"},
    "unknown": {"zh": "未知", "en": "unknown"},
}

BUILTIN_TEXT = {
    "Sensitive path changed": "敏感路径变更",
    "Auth path changed.": "认证路径发生变更。",
    "Large file change": "大文件变更",
    "Deletion-heavy change": "删除较多的变更",
    "Source changed without tests": "源码变更但没有测试",
    "Manual behavior review recommended": "建议人工复核行为",
    "Review behavior and tests": "复核行为和测试",
    "This PR touches configuration, auth, secret, CI, or migration related paths.": (
        "这个 PR 触及配置、认证、密钥、CI 或 migration 相关路径。"
    ),
    "This file removes much more code than it adds; check behavior compatibility.": (
        "这个文件删除的代码远多于新增代码，请检查行为兼容性。"
    ),
    "Source files changed, but no test file change was detected in this PR.": (
        "这个 PR 修改了源码，但没有检测到测试文件变更。"
    ),
    "The mock reviewer cannot inspect runtime behavior beyond the provided diff.": (
        "模拟审查器只能基于提供的 diff 判断，无法检查真实运行时行为。"
    ),
    "Check whether the changed code has enough test coverage and preserves compatibility.": (
        "检查变更代码是否有足够测试覆盖，并确认兼容性没有被破坏。"
    ),
}


def normalize_language(language: str | None) -> Language:
    return "en" if language == "en" else "zh"


def label(key: str, language: str | None = "zh") -> str:
    lang = normalize_language(language)
    values = LABELS.get(key)
    if values is None:
        return key
    return values[lang]


def display_severity(value: str, language: str | None = "zh") -> str:
    return _display(SEVERITY_LABELS, value, language)


def display_source(value: str, language: str | None = "zh") -> str:
    return _display(SOURCE_LABELS, value, language)


def display_suggestion_type(value: str, language: str | None = "zh") -> str:
    return _display(SUGGESTION_TYPE_LABELS, value, language)


def display_confidence(value: str, language: str | None = "zh") -> str:
    return _display(CONFIDENCE_LABELS, value, language)


def display_llm_status(value: str, language: str | None = "zh") -> str:
    return _display(LLM_STATUS_LABELS, value, language)


def translate_builtin_text(text: str, language: str | None = "zh") -> str:
    if normalize_language(language) == "en":
        return text
    large_change = re.fullmatch(r"(.+) changes (\d+) lines and deserves focused review\.", text)
    if large_change:
        path, changed_lines = large_change.groups()
        return f"{path} 变更了 {changed_lines} 行，需要重点审查。"
    return BUILTIN_TEXT.get(text, text)


def prompt_language_instruction(language: str | None = "zh") -> str:
    if normalize_language(language) == "en":
        return (
            "Use English for all natural-language values. Keep JSON keys in English: "
            "summary, risks, suggestions, notes."
        )
    return (
        "请使用中文填写所有自然语言内容。JSON key 必须保持英文："
        "summary, risks, suggestions, notes。"
    )


def _display(
    mapping: dict[str, dict[Language, str]],
    value: str,
    language: str | None,
) -> str:
    lang = normalize_language(language)
    values = mapping.get(value)
    if values is None:
        return value
    return values[lang]
