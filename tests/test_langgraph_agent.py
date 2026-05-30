from types import SimpleNamespace

from xengineer_pr_review.langgraph_agent import LangGraphReviewClient


def test_langgraph_review_client_loops_until_model_returns_final_json() -> None:
    completions = FakeChatCompletions(
        [
            _tool_call_message("call-1", "read_file", {"path": "src/app.py", "max_lines": 5}),
            _assistant_message(
                '{"summary": "Read extra context.", "risks": [], "suggestions": [], "notes": ""}'
            ),
        ]
    )
    toolbox = FakeToolbox()
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        chat_completions=completions,
    )

    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Read extra context."
    assert toolbox.calls == [("read_file", "src/app.py", 5)]
    assert [call["tool_choice"] for call in completions.calls] == ["auto", "auto"]
    assert completions.calls[0]["tools"][0]["function"]["name"] == "read_file"
    assert completions.calls[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "File: src/app.py\n1: print('hello')",
    }


def test_langgraph_review_client_defaults_to_twenty_tool_rounds() -> None:
    client = LangGraphReviewClient(model="test-model", chat_completions=FakeChatCompletions([]))

    assert client.max_tool_rounds == 20


def test_langgraph_review_client_reports_tool_round_limit() -> None:
    completions = FakeChatCompletions(
        [
            _tool_call_message("call-1", "grep_code", {"pattern": "SECRET"}),
            _assistant_message(
                '{"summary": "Limited review.", "risks": [], "suggestions": [], "notes": "Tool round limit reached."}'
            ),
        ]
    )
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        max_tool_rounds=0,
        chat_completions=completions,
    )

    result = client.analyze("PR title: demo", toolbox=FakeToolbox())

    assert result.summary == "Limited review."
    assert result.warnings == ["Tool round limit reached before the model returned a final report."]
    assert completions.calls[1]["tools"] == []
    assert completions.calls[1]["messages"][-2] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "tool skipped: Tool round limit reached before the model returned a final report.",
    }
    assert "Tool round limit reached" in completions.calls[1]["messages"][-1]["content"]


def test_langgraph_review_client_tolerates_bad_integer_tool_args() -> None:
    completions = FakeChatCompletions(
        [
            _tool_call_message("call-1", "read_file", {"path": "src/app.py", "max_lines": "bad"}),
            _assistant_message(
                '{"summary": "Recovered from bad args.", "risks": [], "suggestions": []}'
            ),
        ]
    )
    toolbox = FakeToolbox()
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        chat_completions=completions,
    )

    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Recovered from bad args."
    assert toolbox.calls == [("read_file", "src/app.py", 1000)]


def test_langgraph_review_client_does_not_warn_on_file_content_with_error_word() -> None:
    completions = FakeChatCompletions(
        [
            _tool_call_message("call-1", "read_file", {"path": "src/app.py"}),
            _assistant_message(
                '{"summary": "Read file content.", "risks": [], "suggestions": []}'
            ),
        ]
    )
    toolbox = FakeToolbox()
    toolbox.read_file_result = "File: src/app.py\n1: raise error"
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        chat_completions=completions,
    )

    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Read file content."
    assert result.warnings == []


def test_langgraph_review_client_exposes_web_search_only_when_configured() -> None:
    completions = FakeChatCompletions(
        [
            _assistant_message(
                '{"summary": "No tools needed.", "risks": [], "suggestions": []}'
            ),
        ]
    )
    toolbox = FakeToolbox()
    toolbox.web_searcher = None
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        chat_completions=completions,
    )

    client.analyze("PR title: demo", toolbox=toolbox)

    tool_names = [tool["function"]["name"] for tool in completions.calls[0]["tools"]]
    assert tool_names == ["read_file", "grep_code"]
    assert completions.calls[0]["tools"][0]["function"]["parameters"]["properties"]["max_lines"][
        "maximum"
    ] == 1000


def test_web_search_tool_defaults_to_five_results() -> None:
    completions = FakeChatCompletions(
        [
            _tool_call_message("call-1", "web_search", {"query": "security advisory"}),
            _assistant_message(
                '{"summary": "Searched web.", "risks": [], "suggestions": []}'
            ),
        ]
    )
    toolbox = FakeToolbox()
    toolbox.web_searcher = object()
    client = LangGraphReviewClient(
        model="test-model",
        language="en",
        chat_completions=completions,
    )

    result = client.analyze("PR title: demo", toolbox=toolbox)

    assert result.summary == "Searched web."
    assert toolbox.calls == [("web_search", "security advisory", 5)]


class FakeToolbox:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.read_file_result = "File: src/app.py\n1: print('hello')"

    def read_file(self, path: str, max_lines: int = 1000) -> str:
        self.calls.append(("read_file", path, max_lines))
        return self.read_file_result

    def grep_code(
        self,
        pattern: str,
        path_glob: str | None = None,
        max_results: int = 20,
    ) -> str:
        self.calls.append(("grep_code", pattern, path_glob, max_results))
        return "grep_code found no matches"

    def web_search(self, query: str, max_results: int = 3) -> str:
        self.calls.append(("web_search", query, max_results))
        return "web_search unavailable"


class FakeChatCompletions:
    def __init__(self, messages: list[SimpleNamespace]) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.messages.pop(0))])


def _assistant_message(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=None)


def _tool_call_message(call_id: str, name: str, arguments: dict[str, object]) -> SimpleNamespace:
    import json

    return SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
            )
        ],
    )
