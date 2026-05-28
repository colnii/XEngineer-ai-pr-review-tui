from xengineer_pr_review.locale import (
    display_confidence,
    display_llm_status,
    display_severity,
    display_source,
    display_suggestion_type,
    label,
    normalize_language,
    prompt_language_instruction,
)


def test_normalize_language_defaults_to_chinese() -> None:
    assert normalize_language(None) == "zh"
    assert normalize_language("zh") == "zh"
    assert normalize_language("en") == "en"
    assert normalize_language("fr") == "zh"


def test_locale_labels_and_enum_display_names() -> None:
    assert label("report.title") == "AI PR 审查报告"
    assert label("report.title", "en") == "AI PR Review Report"
    assert display_severity("high") == "高"
    assert display_source("ai") == "AI"
    assert display_suggestion_type("edge-case") == "边界情况"
    assert display_confidence("medium") == "中"
    assert display_llm_status("parsed_with_warnings") == "已解析但有警告"


def test_prompt_language_instruction_keeps_json_keys_english() -> None:
    instruction = prompt_language_instruction("zh")

    assert "中文" in instruction
    assert "JSON key" in instruction
    assert "summary" in instruction
