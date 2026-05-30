from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from xengineer_pr_review.llm import LLMResult, build_review_system_message, parse_llm_output
from xengineer_pr_review.locale import normalize_language


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
TOOL_ROUND_LIMIT_WARNING = "Tool round limit reached before the model returned a final report."


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    tool_rounds: int
    warnings: list[str]
    force_final: bool


class LangGraphReviewClient:
    supports_review_tools = True

    def __init__(
        self,
        model: str = DEFAULT_OPENAI_MODEL,
        language: str = "zh",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tool_rounds: int = 10,
        chat_completions: Any | None = None,
    ) -> None:
        self.model = model
        self.language = normalize_language(language)
        self.max_tool_rounds = max_tool_rounds
        if chat_completions is not None:
            self.chat_completions = chat_completions
        else:
            self.chat_completions = OpenAI(api_key=api_key, base_url=base_url).chat.completions

    def analyze(self, prompt: str, toolbox: Any | None = None) -> LLMResult:
        initial_state: AgentState = {
            "messages": self._initial_messages(prompt, toolbox),
            "pending_tool_calls": [],
            "tool_rounds": 0,
            "warnings": [],
            "force_final": False,
        }
        graph = self._build_graph(toolbox)
        final_state = graph.invoke(initial_state)
        final_text = str(final_state["messages"][-1].get("content") or "")
        result = parse_llm_output(final_text.strip())
        return LLMResult(
            summary=result.summary,
            risks=result.risks,
            suggestions=result.suggestions,
            warnings=[*result.warnings, *final_state["warnings"]],
            notes=result.notes,
            raw_output=result.raw_output,
        )

    def _build_graph(self, toolbox: Any | None):
        graph = StateGraph(AgentState)
        graph.add_node("model", lambda state: self._call_model(state, toolbox))
        graph.add_node("tools", lambda state: self._run_tools(state, toolbox))
        graph.add_node("force_final", self._force_final)
        graph.add_edge(START, "model")
        graph.add_conditional_edges(
            "model",
            self._route_after_model,
            {
                "tools": "tools",
                "force_final": "force_final",
                "end": END,
            },
        )
        graph.add_edge("tools", "model")
        graph.add_edge("force_final", "model")
        return graph.compile()

    def _call_model(self, state: AgentState, toolbox: Any | None) -> AgentState:
        tools = (
            []
            if state["force_final"] or toolbox is None
            else _tool_schemas(web_search_enabled=_web_search_enabled(toolbox))
        )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": state["messages"],
            "tools": tools,
            "stream": False,
        }
        if tools:
            kwargs["tool_choice"] = "auto"
        response = self.chat_completions.create(**kwargs)
        message = response.choices[0].message
        message_dict = _assistant_message_to_dict(message)
        return {
            **state,
            "messages": [*state["messages"], message_dict],
            "pending_tool_calls": message_dict.get("tool_calls", []),
        }

    def _run_tools(self, state: AgentState, toolbox: Any | None) -> AgentState:
        tool_messages: list[dict[str, str]] = []
        warnings = list(state["warnings"])
        for call in state["pending_tool_calls"]:
            result = _dispatch_tool_call(toolbox, call)
            if _is_tool_warning(result):
                warnings.append(result.splitlines()[0])
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id", "")),
                    "content": result,
                }
            )
        return {
            **state,
            "messages": [*state["messages"], *tool_messages],
            "pending_tool_calls": [],
            "tool_rounds": state["tool_rounds"] + 1,
            "warnings": warnings,
        }

    def _force_final(self, state: AgentState) -> AgentState:
        skipped_tool_messages = [
            {
                "role": "tool",
                "tool_call_id": str(call.get("id", "")),
                "content": f"tool skipped: {TOOL_ROUND_LIMIT_WARNING}",
            }
            for call in state["pending_tool_calls"]
        ]
        return {
            **state,
            "messages": [
                *state["messages"],
                *skipped_tool_messages,
                {
                    "role": "system",
                    "content": (
                        f"{TOOL_ROUND_LIMIT_WARNING} Return the final JSON review now and "
                        "mention this limitation in notes."
                    ),
                },
            ],
            "pending_tool_calls": [],
            "warnings": [*state["warnings"], TOOL_ROUND_LIMIT_WARNING],
            "force_final": True,
        }

    def _route_after_model(self, state: AgentState) -> str:
        if not state["pending_tool_calls"]:
            return "end"
        if state["tool_rounds"] >= self.max_tool_rounds:
            return "force_final"
        return "tools"

    def _initial_messages(self, prompt: str, toolbox: Any | None) -> list[dict[str, Any]]:
        system = build_review_system_message(self.language)
        if toolbox is not None:
            tool_names = "read_file and grep_code"
            if _web_search_enabled(toolbox):
                tool_names = "read_file, grep_code, and web_search"
            system += (
                f" You may call {tool_names} when the diff is not enough. "
                "Continue using tools only while they add review value. "
                "When you have enough evidence, stop calling tools and return the final JSON report."
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    message_dict: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        message_dict["tool_calls"] = [
            {
                "id": call.id,
                "type": getattr(call, "type", "function"),
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in tool_calls
        ]
    return message_dict


def _dispatch_tool_call(toolbox: Any | None, call: dict[str, Any]) -> str:
    if toolbox is None:
        return "tool error: review tools are unavailable."
    function = call.get("function", {})
    name = function.get("name", "")
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        return f"{name or 'tool'} error: invalid JSON arguments: {exc}"
    if name == "read_file":
        return toolbox.read_file(
            str(arguments.get("path", "")),
            max_lines=_int_argument(arguments, "max_lines", 1000),
        )
    if name == "grep_code":
        return toolbox.grep_code(
            str(arguments.get("pattern", "")),
            path_glob=arguments.get("path_glob"),
            max_results=_int_argument(arguments, "max_results", 20),
        )
    if name == "web_search":
        return toolbox.web_search(
            str(arguments.get("query", "")),
            max_results=_int_argument(arguments, "max_results", 3),
        )
    return f"tool error: unknown tool {name}"


def _is_tool_warning(result: str) -> bool:
    first_line = result.splitlines()[0] if result else ""
    return first_line.startswith(
        (
            "read_file error",
            "grep_code error",
            "web_search error",
            "web_search unavailable",
            "tool error",
        )
    )


def _int_argument(arguments: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(arguments.get(name, default))
    except (TypeError, ValueError):
        return default


def _web_search_enabled(toolbox: Any) -> bool:
    return getattr(toolbox, "web_searcher", None) is not None


def _tool_schemas(web_search_enabled: bool) -> list[dict[str, Any]]:
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a repository file from the pull request head commit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "grep_code",
                "description": "Search repository files at the pull request head commit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path_glob": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
            },
        },
    ]
    if web_search_enabled:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for public context when enabled by configuration.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 5},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    return schemas
