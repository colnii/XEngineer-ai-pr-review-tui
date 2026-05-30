from __future__ import annotations

import os
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Protocol

import httpx

from xengineer_pr_review.context import has_review_signal
from xengineer_pr_review.models import PullRequestRef


MAX_READ_LINES = 1000
MAX_GREP_FILES = 80
MAX_GREP_RESULTS = 20


class GitHubReadLike(Protocol):
    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str: ...
    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]: ...


class WebSearchLike(Protocol):
    def search(self, query: str, max_results: int) -> list[dict[str, str]]: ...


@dataclass
class ReviewToolbox:
    github: GitHubReadLike
    ref: PullRequestRef
    git_ref: str
    web_searcher: WebSearchLike | None = None

    def read_file(self, path: str, max_lines: int = MAX_READ_LINES) -> str:
        try:
            path = _validate_relative_path(path)
            max_lines = _bounded_int(
                max_lines,
                default=MAX_READ_LINES,
                minimum=1,
                maximum=MAX_READ_LINES,
            )
            text = self.github.fetch_file_text(self.ref, path, self.git_ref)
        except Exception as exc:
            return f"read_file error for {path}: {exc}"

        lines = text.splitlines()
        selected = lines[:max_lines]
        numbered = [f"{index}: {line}" for index, line in enumerate(selected, start=1)]
        if len(lines) > max_lines:
            numbered.append(
                f"[truncated after {max_lines} lines; single file is too large to read fully]"
            )
        return "\n".join([f"File: {path}", *numbered])

    def grep_code(
        self,
        pattern: str,
        path_glob: str | None = None,
        max_results: int = MAX_GREP_RESULTS,
    ) -> str:
        if not pattern:
            return "grep_code error: pattern is required."
        max_results = _bounded_int(
            max_results,
            default=MAX_GREP_RESULTS,
            minimum=1,
            maximum=MAX_GREP_RESULTS,
        )
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return f"grep_code error: invalid regex pattern: {exc}"

        try:
            paths = self.github.fetch_tree_paths(self.ref, self.git_ref)
        except Exception as exc:
            return f"grep_code error: could not list repository tree: {exc}"

        matches: list[str] = []
        searched_files = 0
        for path in _filter_search_paths(paths, path_glob):
            if searched_files >= MAX_GREP_FILES:
                break
            searched_files += 1
            try:
                text = self.github.fetch_file_text(self.ref, path, self.git_ref)
            except Exception:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append(f"{path}:{line_number}: {line}")
                    if len(matches) >= max_results:
                        return "\n".join(
                            [*matches, f"[truncated after {max_results} matches]"]
                        )

        if not matches:
            return f"grep_code found no matches for pattern: {pattern}"
        return "\n".join(matches)

    def web_search(self, query: str, max_results: int = 3) -> str:
        if self.web_searcher is None:
            return "web_search unavailable: TAVILY_API_KEY is not configured."
        max_results = _bounded_int(max_results, default=3, minimum=1, maximum=5)
        try:
            results = self.web_searcher.search(query, max_results)
        except Exception as exc:
            return f"web_search error: {exc}"
        if not results:
            return f"web_search found no results for query: {query}"
        lines = [f"Web search results for: {query}"]
        for index, result in enumerate(results[:max_results], start=1):
            title = result.get("title") or "Untitled result"
            url = result.get("url") or ""
            content = " ".join((result.get("content") or "").split())
            lines.append(f"{index}. {title}\n   URL: {url}\n   Snippet: {content}")
        return "\n".join(lines)


class TavilyWebSearchClient:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, query: str, max_results: int) -> list[dict[str, str]]:
        response = self.client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        return [result for result in results if isinstance(result, dict)]


def default_web_searcher() -> WebSearchLike | None:
    if not os.environ.get("TAVILY_API_KEY"):
        return None
    return TavilyWebSearchClient()


def _filter_search_paths(paths: list[str], path_glob: str | None) -> list[str]:
    selected: list[str] = []
    for path in paths:
        if path_glob and not fnmatch(path, path_glob):
            continue
        if not has_review_signal(path):
            continue
        selected.append(path)
    return selected


def _validate_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError("path must be a repository-relative file path")
    return normalized


def _bounded_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))
