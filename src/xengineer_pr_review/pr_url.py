from __future__ import annotations

from urllib.parse import urlparse

from xengineer_pr_review.models import PullRequestRef


def parse_pr_url(url: str) -> PullRequestRef:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() != "github.com":
        raise ValueError("期望 GitHub PR 地址，例如 https://github.com/owner/repo/pull/123")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2] != "pull":
        raise ValueError("期望 GitHub PR 路径 /owner/repo/pull/<number>")

    try:
        number = int(parts[3])
    except ValueError as exc:
        raise ValueError("期望数字形式的 GitHub PR 路径 /owner/repo/pull/<number>") from exc

    return PullRequestRef(owner=parts[0], repo=parts[1], number=number)
