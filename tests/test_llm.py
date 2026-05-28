from xengineer_pr_review.llm import MockLLMClient, parse_llm_output


def test_mock_llm_returns_structured_sections() -> None:
    result = MockLLMClient().analyze("PR title: demo")

    assert result.summary
    assert result.suggestions
    assert result.warnings == []


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
