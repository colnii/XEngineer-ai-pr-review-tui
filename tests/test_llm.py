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
    client = OpenAILLMClient(
        model="gpt-test",
        language="en",
        base_url="https://openai-compatible.example",
    )
    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Wrapped OpenAI."
    assert calls == [
        (
            "init",
            {
                "model": "gpt-test",
                "language": "en",
                "api_key": None,
                "base_url": "https://openai-compatible.example",
            },
        ),
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
              "files": ["src/requests/models.py"],
              "evidence": [
                {
                  "kind": "code",
                  "path": "src/requests/models.py",
                  "line_start": 42,
                  "line_end": 45,
                  "snippet": "is_stream = ..."
                },
                {
                  "kind": "web",
                  "label": "W1",
                  "title": "urllib3 docs",
                  "url": "https://urllib3.readthedocs.io/example",
                  "snippet": "Wrapper behavior changed upstream."
                }
              ]
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
    risk_evidence = getattr(result.risks[0], "evidence", [])
    assert risk_evidence[0].path == "src/requests/models.py"
    assert risk_evidence[0].line_start == 42
    assert risk_evidence[1].kind == "web"
    assert risk_evidence[1].url == "https://urllib3.readthedocs.io/example"
    assert result.suggestions[0].suggestion_type == "test"
    assert result.suggestions[0].files == ["tests/test_requests.py"]
    assert result.notes == "Assumes urllib3 behavior is unchanged."
    assert result.warnings == []


def test_parse_llm_json_output_accepts_citations_alias_on_suggestions() -> None:
    result = parse_llm_output(
        """
        {
          "summary": "Add tests for the changed path.",
          "risks": [],
          "suggestions": [
            {
              "type": "test",
              "text": "Cover the new parser branch.",
              "related_file": "tests/test_parser.py",
              "citations": [
                {"kind": "code", "path": "src/parser.py", "line": 88}
              ],
              "confidence": "high"
            }
          ]
        }
        """
    )

    suggestion_evidence = getattr(result.suggestions[0], "evidence", [])
    assert suggestion_evidence[0].kind == "code"
    assert suggestion_evidence[0].path == "src/parser.py"
    assert suggestion_evidence[0].line_start == 88
    assert suggestion_evidence[0].line_end == 88


def test_parse_llm_json_output_treats_url_citation_as_web_evidence() -> None:
    result = parse_llm_output(
        """
        {
          "summary": "External behavior matters.",
          "risks": [
            {
              "severity": "low",
              "title": "External API changed",
              "explanation": "The dependency docs describe a behavior change.",
              "citations": [
                {"label": "W1", "url": "https://example.test/api-change"}
              ]
            }
          ],
          "suggestions": []
        }
        """
    )

    evidence = result.risks[0].evidence[0]
    assert evidence.kind == "web"
    assert evidence.label == "W1"
    assert evidence.url == "https://example.test/api-change"


def test_parse_llm_json_output_accepts_pr_activity_citation_id() -> None:
    result = parse_llm_output(
        """
        {
          "summary": "Prior PR discussion matters.",
          "risks": [
            {
              "severity": "low",
              "title": "Reviewer already raised this",
              "explanation": "A previous PR comment asked for the same check.",
              "citations": [
                {"kind": "pr_activity", "label": "A1"}
              ]
            }
          ],
          "suggestions": []
        }
        """
    )

    evidence = result.risks[0].evidence[0]
    assert evidence.kind == "pr_activity"
    assert evidence.label == "A1"


def test_parse_llm_json_output_keeps_path_and_url_citation_as_code_evidence() -> None:
    result = parse_llm_output(
        """
        {
          "summary": "Code location matters.",
          "risks": [
            {
              "severity": "low",
              "title": "Code behavior changed",
              "explanation": "The changed line has a related source link.",
              "citations": [
                {
                  "path": "src/app.py",
                  "line": 9,
                  "url": "https://github.com/owner/repo/blob/abc/src/app.py#L9"
                }
              ]
            }
          ],
          "suggestions": []
        }
        """
    )

    evidence = result.risks[0].evidence[0]
    assert evidence.kind == "code"
    assert evidence.path == "src/app.py"
    assert evidence.url == "https://github.com/owner/repo/blob/abc/src/app.py#L9"


def test_parse_llm_markdown_output_extracts_evidence_metadata() -> None:
    result = parse_llm_output(
        """
        ### Summary
        The PR adds structured evidence.

        ### Risks
        - Low: Citation fallback can be missing. File: src/review.py. Evidence: src/review.py:12-16; [W1] https://example.test/source; [A2]

        ### Suggestions
        - Test: Add coverage for markdown evidence parsing. File: tests/test_llm.py. Evidence: tests/test_llm.py:45. Confidence: high.
        """
    )

    risk_evidence = result.risks[0].evidence
    assert risk_evidence[0].kind == "code"
    assert risk_evidence[0].path == "src/review.py"
    assert risk_evidence[0].line_start == 12
    assert risk_evidence[0].line_end == 16
    assert risk_evidence[1].kind == "web"
    assert risk_evidence[1].label == "W1"
    assert risk_evidence[1].url == "https://example.test/source"
    assert risk_evidence[2].kind == "pr_activity"
    assert risk_evidence[2].label == "A2"
    suggestion_evidence = result.suggestions[0].evidence[0]
    assert suggestion_evidence.path == "tests/test_llm.py"
    assert suggestion_evidence.line_start == 45
    assert result.suggestions[0].confidence == "high"


def test_parse_llm_markdown_pr_activity_url_does_not_duplicate_as_web_evidence() -> None:
    result = parse_llm_output(
        """
        ### Summary
        The PR cites prior activity.

        ### Risks
        - Low: Prior comment applies. Evidence: [A2] https://github.com/owner/repo/pull/1#issuecomment-10
        """
    )

    evidence = result.risks[0].evidence
    assert len(evidence) == 1
    assert evidence[0].kind == "pr_activity"
    assert evidence[0].label == "A2"
    assert evidence[0].url == "https://github.com/owner/repo/pull/1#issuecomment-10"


def test_parse_llm_markdown_keeps_distinct_bare_url_with_pr_activity_url() -> None:
    result = parse_llm_output(
        """
        ### Summary
        The PR cites prior activity and docs.

        ### Risks
        - Low: Prior comment applies. Evidence: [A2] https://github.com/owner/repo/pull/1#issuecomment-10 and https://docs.example.com/parser
        """
    )

    evidence = result.risks[0].evidence
    assert len(evidence) == 2
    assert evidence[0].kind == "pr_activity"
    assert evidence[0].url == "https://github.com/owner/repo/pull/1#issuecomment-10"
    assert evidence[1].kind == "web"
    assert evidence[1].url == "https://docs.example.com/parser"


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
