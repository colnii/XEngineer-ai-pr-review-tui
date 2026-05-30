from xengineer_pr_review import llm as llm_module
from xengineer_pr_review.llm import (
    DeepSeekLLMClient,
    MockLLMClient,
    OpenAILLMClient,
    build_review_system_message,
    parse_llm_output,
)


def test_mock_llm_returns_structured_sections() -> None:
    result = MockLLMClient().analyze("PR title: demo")

    assert "模拟摘要" in result.summary
    assert result.suggestions
    assert result.warnings == []


def test_mock_llm_can_return_english_output() -> None:
    result = MockLLMClient(language="en").analyze("PR title: demo")

    assert result.summary.startswith("Mock summary")


def test_mock_llm_declares_tools_not_supported() -> None:
    assert MockLLMClient.supports_review_tools is False


def test_review_prompt_uses_selected_language_instruction() -> None:
    prompt = build_review_system_message("zh")

    assert "请使用中文" in prompt
    assert "JSON key" in prompt
    assert "summary" in prompt


def test_legacy_openai_client_wraps_langgraph_client(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls: list[tuple[str, object]] = []

    class FakeLangGraphReviewClient:
        supports_review_tools = True

        def __init__(self, **kwargs: object) -> None:
            calls.append(("init", kwargs))

        def analyze(self, prompt: str, toolbox=None):
            calls.append(("analyze", (prompt, toolbox)))
            return parse_llm_output(
                '{"summary": "Wrapped OpenAI.", "risks": [], "suggestions": []}'
            )

    monkeypatch.setattr(llm_module, "_langgraph_review_client", lambda: FakeLangGraphReviewClient)

    toolbox = object()
    client = OpenAILLMClient(model="gpt-test", language="en")
    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Wrapped OpenAI."
    assert calls == [
        ("init", {"model": "gpt-test", "language": "en", "api_key": None}),
        ("analyze", ("PR title: demo", toolbox)),
    ]


def test_legacy_deepseek_client_wraps_langgraph_client(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeLangGraphReviewClient:
        supports_review_tools = True

        def __init__(self, **kwargs: object) -> None:
            calls.append(("init", kwargs))

        def analyze(self, prompt: str, toolbox=None):
            calls.append(("analyze", (prompt, toolbox)))
            return parse_llm_output(
                '{"summary": "Wrapped DeepSeek.", "risks": [], "suggestions": []}'
            )

    monkeypatch.setattr(llm_module, "_langgraph_review_client", lambda: FakeLangGraphReviewClient)

    client = DeepSeekLLMClient(
        model="deepseek-test",
        language="zh",
        api_key="deepseek-key",
        base_url="https://deepseek.example",
    )
    result = client.analyze("PR title: demo")

    assert result.summary == "Wrapped DeepSeek."
    assert calls == [
        (
            "init",
            {
                "model": "deepseek-test",
                "language": "zh",
                "api_key": "deepseek-key",
                "base_url": "https://deepseek.example",
            },
        ),
        ("analyze", ("PR title: demo", None)),
    ]


def test_parse_llm_json_output() -> None:
    result = parse_llm_output(
        """
        {
          "summary": "This PR tightens stream detection.",
          "risks": [
            {
              "severity": "medium",
              "title": "Wrapper compatibility",
              "explanation": "Custom wrappers may still expose partial file APIs.",
              "files": ["src/requests/models.py"]
            }
          ],
          "suggestions": [
            {
              "type": "test",
              "text": "Add a regression test for __getattr__ wrappers.",
              "related_file": "tests/test_requests.py",
              "confidence": "high"
            }
          ],
          "notes": "Assumes urllib3 behavior is unchanged."
        }
        """
    )

    assert result.summary == "This PR tightens stream detection."
    assert result.risks[0].source == "ai"
    assert result.risks[0].title == "Wrapper compatibility"
    assert result.suggestions[0].suggestion_type == "test"
    assert result.suggestions[0].files == ["tests/test_requests.py"]
    assert result.notes == "Assumes urllib3 behavior is unchanged."
    assert result.warnings == []


def test_parse_llm_json_output_embedded_in_markdown_fence() -> None:
    result = parse_llm_output(
        """
        I now have enough context to write the final review.

        ```json
        {
          "summary": "The PR adds repository read tools.",
          "risks": [
            {
              "severity": "low",
              "title": "API budget",
              "explanation": "Repeated grep calls can spend API budget.",
              "files": ["src/xengineer_pr_review/review_tools.py"]
            }
          ],
          "suggestions": [],
          "notes": "The JSON was wrapped in a code fence."
        }
        ```
        """
    )

    assert result.summary == "The PR adds repository read tools."
    assert result.risks[0].title == "API budget"
    assert result.risks[0].files == ["src/xengineer_pr_review/review_tools.py"]
    assert result.notes == "The JSON was wrapped in a code fence."
    assert result.warnings == []


def test_parse_llm_markdown_headings_output() -> None:
    result = parse_llm_output(
        """
        ### Summary
        The PR fixes file-like wrapper detection and adds regression coverage.

        ### Risks
        - Medium: Stream detection could still misclassify unusual wrappers.
        - Low: Tests may not cover every adapter path.

        ### Suggestions
        - Test: Add an edge-case test for wrappers with dynamic attributes. File: tests/test_requests.py. Confidence: high.
        - Maintainability: Keep the helper name tied to stream detection. File: src/requests/models.py.

        ### Uncertainty
        I did not run the full requests test matrix.
        """
    )

    assert result.summary == "The PR fixes file-like wrapper detection and adds regression coverage."
    assert result.risks[0].severity == "medium"
    assert result.risks[0].title == "Stream detection could still misclassify unusual wrappers"
    assert len(result.risks) == 2
    assert result.suggestions[0].suggestion_type == "test"
    assert result.suggestions[0].confidence == "high"
    assert result.suggestions[0].files == ["tests/test_requests.py"]
    assert len(result.suggestions) == 2
    assert result.suggestions[1].files == ["src/requests/models.py"]
    assert result.notes == "I did not run the full requests test matrix."


def test_parse_llm_markdown_fenced_block_output() -> None:
    result = parse_llm_output(
        """```markdown
### Summary
Only the concise summary should be kept here.

### Risks
- Low: The fallback path may need manual review.

### Suggestions
- Maintainability: Name the new helper after the behavior it detects.
```"""
    )

    assert result.summary == "Only the concise summary should be kept here."
    assert "```markdown" not in result.summary
    assert result.risks
    assert result.suggestions


def test_parse_llm_unstructured_output_falls_back_to_raw_output() -> None:
    result = parse_llm_output("Looks okay overall, but I would inspect the tests manually.")

    assert result.summary == "AI review returned unstructured notes."
    assert result.raw_output == "Looks okay overall, but I would inspect the tests manually."
    assert result.warnings == ["LLM output could not be parsed into structured sections."]
