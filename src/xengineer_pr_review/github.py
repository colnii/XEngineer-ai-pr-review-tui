from __future__ import annotations

import os

import httpx

from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.models import PullRequestData, PullRequestRef


class GitHubClient:
    def __init__(self, timeout: float = 20.0) -> None:
        headers = {"User-Agent": "xengineer-pr-review"}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
        diff_url = f"https://github.com/{ref.owner}/{ref.repo}/pull/{ref.number}.diff"

        pr_response = self.client.get(api_url)
        pr_response.raise_for_status()
        payload = pr_response.json()

        diff_response = self.client.get(diff_url)
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
        )
