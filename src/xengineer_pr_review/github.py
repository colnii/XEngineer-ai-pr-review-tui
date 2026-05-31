from __future__ import annotations

import base64
import binascii
import os
import re
import subprocess
from urllib.parse import quote

import httpx

from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.models import (
    PostedComment,
    PullRequestActivity,
    PullRequestData,
    PullRequestRef,
)


MAX_FILE_CONTENT_BYTES = 1_000_000


class GitHubClient:
    def __init__(self, timeout: float = 20.0, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"User-Agent": "xengineer-pr-review"}
        token = _resolve_github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            transport=transport,
        )

    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"

        pr_response = self.client.get(api_url)
        pr_response.raise_for_status()
        payload = pr_response.json()

        diff_response = self.client.get(api_url, headers={"Accept": "application/vnd.github.diff"})
        diff_response.raise_for_status()
        diff_text = diff_response.text

        return PullRequestData(
            ref=ref,
            title=payload.get("title", ""),
            author=payload.get("user", {}).get("login", "unknown"),
            base_branch=payload.get("base", {}).get("ref", "unknown"),
            head_branch=payload.get("head", {}).get("ref", "unknown"),
            files=parse_unified_diff(diff_text),
            diff_text=diff_text,
            head_sha=payload.get("head", {}).get("sha", ""),
            activities=tuple(self.fetch_pr_activities(ref)),
        )

    def fetch_pr_activities(self, ref: PullRequestRef) -> list[PullRequestActivity]:
        return [
            *self._fetch_commit_activities(ref),
            *self._fetch_conversation_activities(ref),
            *self._fetch_review_activities(ref),
            *self._fetch_inline_comment_activities(ref),
        ]

    def post_pr_comment(self, ref: PullRequestRef, body: str) -> PostedComment:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments"
        response = self.client.post(api_url, json={"body": body})
        response.raise_for_status()
        payload = response.json()
        return PostedComment(html_url=payload.get("html_url", ""))

    def post_pr_review(self, ref: PullRequestRef, body: str) -> PostedComment:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/reviews"
        response = self.client.post(api_url, json={"body": body, "event": "COMMENT"})
        response.raise_for_status()
        payload = response.json()
        return PostedComment(html_url=payload.get("html_url", ""))

    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str:
        encoded_path = quote(path.strip("/"), safe="/")
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/contents/{encoded_path}"
        response = self.client.get(api_url, params={"ref": git_ref})
        response.raise_for_status()
        payload = response.json()
        content_size = _payload_int(payload.get("size"))
        if content_size > MAX_FILE_CONTENT_BYTES:
            raise ValueError(
                f"GitHub content for {path} is larger than supported limit "
                f"({MAX_FILE_CONTENT_BYTES} bytes)."
            )
        payload_type = payload.get("type")
        if payload_type and payload_type != "file":
            raise ValueError(f"GitHub content for {path} is not a regular file.")
        if payload.get("encoding") != "base64":
            raise ValueError(f"GitHub content for {path} is not base64 encoded.")
        raw_content = re.sub(r"\s+", "", str(payload.get("content", "")))
        try:
            return base64.b64decode(raw_content, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError(f"GitHub content for {path} is not valid UTF-8 base64.") from exc

    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/git/trees/{git_ref}"
        response = self.client.get(api_url, params={"recursive": "1"})
        response.raise_for_status()
        payload = response.json()
        if payload.get("truncated"):
            raise ValueError(
                f"GitHub tree for {git_ref} is truncated; grep coverage would be incomplete."
            )
        return [
            item.get("path", "")
            for item in payload.get("tree", [])
            if item.get("type") == "blob" and item.get("path")
        ]

    def _fetch_conversation_activities(self, ref: PullRequestRef) -> list[PullRequestActivity]:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments"
        return [
            PullRequestActivity(
                kind="conversation",
                author=_user_login(item),
                body=_clean_body(item.get("body")),
                created_at=str(item.get("created_at") or ""),
                url=str(item.get("html_url") or ""),
            )
            for item in self._get_paginated_items(api_url)
        ]

    def _fetch_review_activities(self, ref: PullRequestRef) -> list[PullRequestActivity]:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/reviews"
        return [
            PullRequestActivity(
                kind="review",
                author=_user_login(item),
                body=_clean_body(item.get("body")),
                created_at=str(item.get("submitted_at") or item.get("created_at") or ""),
                url=str(item.get("html_url") or ""),
                state=str(item.get("state") or ""),
            )
            for item in self._get_paginated_items(api_url)
        ]

    def _fetch_inline_comment_activities(self, ref: PullRequestRef) -> list[PullRequestActivity]:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/comments"
        return [
            PullRequestActivity(
                kind="inline",
                author=_user_login(item),
                body=_clean_body(item.get("body")),
                created_at=str(item.get("created_at") or ""),
                url=str(item.get("html_url") or ""),
                path=str(item.get("path") or ""),
                line=_optional_int(item.get("line") or item.get("original_line")),
            )
            for item in self._get_paginated_items(api_url)
        ]

    def _fetch_commit_activities(self, ref: PullRequestRef) -> list[PullRequestActivity]:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/commits"
        activities: list[PullRequestActivity] = []
        for item in self._get_paginated_items(api_url):
            commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
            sha = str(item.get("sha") or "")
            activities.append(
                PullRequestActivity(
                    kind="commit",
                    author=str(author.get("name") or _user_login(item)),
                    body=_clean_body(commit.get("message")),
                    created_at=str(author.get("date") or ""),
                    url=str(item.get("html_url") or ""),
                    commit_sha=sha[:7],
                )
            )
        return activities

    def _get_paginated_items(self, api_url: str) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = api_url
        params: dict[str, str] | None = {"per_page": "100"}
        while next_url:
            response = self.client.get(next_url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return items
            items.extend(item for item in payload if isinstance(item, dict))
            next_url = response.links.get("next", {}).get("url")
            params = None
        return items


def _resolve_github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None

    if result.returncode != 0:
        return None

    token = result.stdout.strip()
    return token or None


def _payload_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _user_login(payload: dict) -> str:
    user = payload.get("user")
    if isinstance(user, dict):
        return str(user.get("login") or "")
    return ""


def _clean_body(value: object) -> str:
    return str(value or "").strip()
