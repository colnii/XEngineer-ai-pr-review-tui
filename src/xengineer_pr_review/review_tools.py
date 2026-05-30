from __future__ import annotations

from collections import OrderedDict
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Protocol

import httpx

from xengineer_pr_review.context import has_review_signal
from xengineer_pr_review.models import EvidenceReference, PullRequestRef


MAX_READ_LINES = 1000
MAX_GREP_FILES = 40
MAX_GREP_RESULTS = 20
MAX_CACHED_FILES = 40


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
    _tree_paths_cache: list[str] | None = field(default=None, init=False, repr=False)
    _file_text_cache: OrderedDict[str, str] = field(
        default_factory=OrderedDict,
        init=False,
        repr=False,
    )
    web_sources: list[EvidenceReference] = field(default_factory=list, init=False)

    def read_file(self, path: str, max_lines: int = MAX_READ_LINES) -> str:
        try:
            path = _validate_relative_path(path)
            max_lines = _bounded_int(
                max_lines,
                default=MAX_READ_LINES,
                minimum=1,
                maximum=MAX_READ_LINES,
            )
            text = self._fetch_file_text(path)
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
            paths = self._fetch_tree_paths()
        except Exception as exc:
            return f"grep_code error: could not list repository tree: {exc}"

        matches: list[str] = []
        skipped_files = 0
        search_paths = _filter_search_paths(paths, path_glob)
        budget_exhausted = len(search_paths) > MAX_GREP_FILES
        for path in search_paths[:MAX_GREP_FILES]:
            try:
                text = self._fetch_file_text(path)
            except Exception:
                skipped_files += 1
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append(f"{path}:{line_number}: {line}")
                    if len(matches) >= max_results:
                        return "\n".join(
                            [*matches, f"[truncated after {max_results} matches]"]
                        )

        if not matches:
            lines = [f"grep_code found no matches for pattern: {pattern}"]
            if budget_exhausted:
                lines.append(f"[stopped after {MAX_GREP_FILES} files; file search budget exhausted]")
            if skipped_files:
                lines.append(_skipped_files_message(skipped_files))
            return "\n".join(lines)
        if budget_exhausted:
            matches.append(f"[stopped after {MAX_GREP_FILES} files; file search budget exhausted]")
        if skipped_files:
            matches.append(_skipped_files_message(skipped_files))
        return "\n".join(matches)

    def web_search(self, query: str, max_results: int = 3) -> str:
        if self.web_searcher is None:
            return "web_search unavailable: TAVILY_API_KEY is not configured."
        max_results = _bounded_int(max_results, default=3, minimum=1, maximum=5)
        try:
            results = self.web_searcher.search(query, max_results)
        except Exception:
            return "web_search error: search request failed."
        if not results:
            return f"web_search found no results for query: {query}"
        lines = [
            f"Web search results for: {query}",
            "Use citation id [W1], [W2], etc. in final JSON evidence for external facts.",
        ]
        for index, result in enumerate(results[:max_results], start=len(self.web_sources) + 1):
            citation_id = f"W{index}"
            title = result.get("title") or "Untitled result"
            url = result.get("url") or ""
            content = " ".join((result.get("content") or "").split())
            self.web_sources.append(
                EvidenceReference(
                    kind="web",
                    label=citation_id,
                    title=title,
                    url=url,
                    snippet=content,
                )
            )
            lines.append(
                f"[{citation_id}] {title}\n"
                f"   URL: {url}\n"
                f"   Snippet: {content}\n"
                f"   Use citation id [{citation_id}] with this URL."
            )
        return "\n".join(lines)

    def _fetch_tree_paths(self) -> list[str]:
        if self._tree_paths_cache is None:
            self._tree_paths_cache = self.github.fetch_tree_paths(self.ref, self.git_ref)
        return self._tree_paths_cache

    def _fetch_file_text(self, path: str) -> str:
        if path in self._file_text_cache:
            self._file_text_cache.move_to_end(path)
            return self._file_text_cache[path]
        if len(self._file_text_cache) >= MAX_CACHED_FILES:
            self._file_text_cache.popitem(last=False)
        self._file_text_cache[path] = self.github.fetch_file_text(
            self.ref,
            path,
            self.git_ref,
        )
        return self._file_text_cache[path]


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
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY is not configured.")
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
        if not path_glob and not has_review_signal(path):
            continue
        selected.append(path)
    return selected


def _validate_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if (
        not normalized
        or normalized.startswith("/")
        or ".." in normalized.split("/")
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError("path must be a repository-relative file path")
    return normalized


def _bounded_int(value: int, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _skipped_files_message(count: int) -> str:
    noun = "file" if count == 1 else "files"
    return f"[skipped {count} unreadable {noun}]"
