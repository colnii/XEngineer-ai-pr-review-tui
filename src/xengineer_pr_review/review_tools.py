from __future__ import annotations

from collections import OrderedDict
from difflib import get_close_matches
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Protocol

import httpx

from xengineer_pr_review.context import format_pr_activity_lines, has_review_signal
from xengineer_pr_review.models import EvidenceReference, PullRequestActivity, PullRequestRef


MAX_READ_LINES = 1000
MAX_GREP_FILES = 40
MAX_GREP_RESULTS = 20
MAX_CACHED_FILES = 40
DEFAULT_PR_ACTIVITY_TOOL_ITEMS = 200
MAX_PR_ACTIVITY_TOOL_ITEMS = 300
MAX_PR_ACTIVITY_SNIPPET_CHARS = 500


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
    file_ids: dict[str, str] = field(default_factory=dict)
    activities: tuple[PullRequestActivity, ...] = ()
    _tree_paths_cache: list[str] | None = field(default=None, init=False, repr=False)
    _file_text_cache: OrderedDict[str, str] = field(
        default_factory=OrderedDict,
        init=False,
        repr=False,
    )
    web_sources: list[EvidenceReference] = field(default_factory=list, init=False)
    activity_sources: list[EvidenceReference] = field(default_factory=list, init=False)

    def read_file(
        self,
        path: str = "",
        max_lines: int = MAX_READ_LINES,
        file_id: str = "",
    ) -> str:
        try:
            path = self._resolve_read_path(path=path, file_id=file_id)
            if path.startswith("read_file note:"):
                return path
            max_lines = _bounded_int(
                max_lines,
                default=MAX_READ_LINES,
                minimum=1,
                maximum=MAX_READ_LINES,
            )
            missing_note = self._missing_path_note(path)
            if missing_note:
                return missing_note
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

    def _resolve_read_path(self, path: str, file_id: str) -> str:
        normalized_file_id = str(file_id or "").strip()
        if normalized_file_id:
            mapped = self.file_ids.get(normalized_file_id)
            if mapped:
                return mapped
            return (
                f"read_file note: unknown file_id {normalized_file_id}. "
                f"Available file_ids: {_format_file_ids(self.file_ids)}"
            )
        return _validate_relative_path(path)

    def _missing_path_note(self, path: str) -> str:
        if not self.file_ids:
            return ""
        try:
            paths = self._fetch_tree_paths()
        except Exception:
            return ""
        if path in paths:
            return ""
        matches = _close_path_matches(path, paths)
        match_text = ", ".join(matches) if matches else "none"
        return (
            f"read_file note: path not found: {path}. "
            f"Close matches: {match_text}. "
            "Prefer file_id from the changed file index when reading PR files."
        )

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

    def read_pr_activity(
        self,
        kind: str = "all",
        max_items: int = DEFAULT_PR_ACTIVITY_TOOL_ITEMS,
    ) -> str:
        normalized_kind = str(kind or "all").strip().lower()
        allowed_kinds = {"all", "commit", "conversation", "review", "inline", "event"}
        if normalized_kind not in allowed_kinds:
            return (
                "read_pr_activity error: kind must be one of "
                "all, commit, conversation, review, inline, event."
            )
        max_items = _bounded_int(
            max_items,
            default=DEFAULT_PR_ACTIVITY_TOOL_ITEMS,
            minimum=1,
            maximum=MAX_PR_ACTIVITY_TOOL_ITEMS,
        )
        selected = tuple(
            (index, activity)
            for index, activity in enumerate(self.activities, start=1)
            if normalized_kind == "all" or activity.kind == normalized_kind
        )
        if not selected:
            return f"read_pr_activity found no {normalized_kind} PR activity items."
        shown = selected[:max_items]
        lines: list[str] = []
        for index, activity in shown:
            citation_id = f"A{index}"
            display_line = _activity_display_line(activity)
            self._record_activity_source(citation_id, display_line, activity)
            lines.append(
                f"[{citation_id}] {display_line}\n"
                f"   Use citation id [{citation_id}] with this PR activity item."
            )
        if len(selected) > max_items:
            lines.append(f"- [truncated {len(selected) - max_items} additional PR activity items]")
        return "\n".join(
            [
                (
                    f"PR activity history ({normalized_kind}, showing "
                    f"{min(len(selected), max_items)} of {len(selected)} items)"
                ),
                *lines,
            ]
        )

    def _record_activity_source(
        self,
        citation_id: str,
        display_line: str,
        activity: PullRequestActivity,
    ) -> None:
        if any(source.label == citation_id for source in self.activity_sources):
            return
        title = display_line.split(": ", 1)[0]
        self.activity_sources.append(
            EvidenceReference(
                kind="pr_activity",
                label=citation_id,
                title=title,
                url=activity.url,
                snippet=_activity_snippet(activity),
            )
        )

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


def _activity_display_line(activity: PullRequestActivity) -> str:
    line = format_pr_activity_lines((activity,), max_items=1)[0]
    return line.removeprefix("- ")


def _activity_snippet(activity: PullRequestActivity) -> str:
    cleaned = " ".join(activity.body.split())
    if len(cleaned) <= MAX_PR_ACTIVITY_SNIPPET_CHARS:
        return cleaned
    return cleaned[:MAX_PR_ACTIVITY_SNIPPET_CHARS].rstrip() + " [truncated]"


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


def _format_file_ids(file_ids: dict[str, str]) -> str:
    if not file_ids:
        return "none"
    return ", ".join(f"{file_id}={path}" for file_id, path in file_ids.items())


def _close_path_matches(path: str, paths: list[str], limit: int = 5) -> list[str]:
    basename = path.rsplit("/", 1)[-1].lower()
    matches: list[str] = [
        candidate
        for candidate in paths
        if candidate.rsplit("/", 1)[-1].lower() == basename
    ]
    for candidate in get_close_matches(path, paths, n=limit, cutoff=0.35):
        if candidate not in matches:
            matches.append(candidate)
    return matches[:limit]


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
