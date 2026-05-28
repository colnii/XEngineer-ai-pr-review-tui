from xengineer_pr_review.llm import MockLLMClient


def test_mock_llm_returns_structured_sections() -> None:
    result = MockLLMClient().analyze("PR title: demo")

    assert result.summary
    assert result.suggestions
    assert result.warnings == []
