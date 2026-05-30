import json
import base64

import httpx

import xengineer_pr_review.github as github_module
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.models import PullRequestRef


PULL_API_URL = "https://api.github.com/repos/owner/repo/pulls/1"
PULL_PAYLOAD = {
    "title": "Demo PR",
    "user": {"login": "alice"},
    "base": {"ref": "main"},
    "head": {"ref": "feature", "sha": "abc123"},
}
DIFF_TEXT = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1,2 @@
-old = True
+new = True
"""


def test_github_client_uses_github_token_header(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "example-token")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    client = GitHubClient()

    assert client.client.headers["authorization"] == "Bearer example-token"


def test_github_client_uses_gh_token_when_github_token_is_absent(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh-token")

    client = GitHubClient()

    assert client.client.headers["authorization"] == "Bearer gh-token"


def test_github_client_falls_back_to_gh_auth_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def fake_run(*args, **kwargs):
        assert args[0] == ["gh", "auth", "token"]
        return type("Completed", (), {"returncode": 0, "stdout": "cli-token\n"})()

    monkeypatch.setattr(github_module.subprocess, "run", fake_run)

    client = GitHubClient()

    assert client.client.headers["authorization"] == "Bearer cli-token"


def test_github_client_ignores_failed_gh_auth_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def fake_run(*args, **kwargs):
        return type("Completed", (), {"returncode": 1, "stdout": ""})()

    monkeypatch.setattr(github_module.subprocess, "run", fake_run)

    client = GitHubClient()

    assert "authorization" not in client.client.headers


def test_github_client_supports_socks_proxy_environment(monkeypatch) -> None:
    proxy_url = "socks5://127.0.0.1:1080"
    monkeypatch.setenv("ALL_PROXY", proxy_url)
    monkeypatch.setenv("HTTP_PROXY", proxy_url)
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)
    monkeypatch.setenv("all_proxy", proxy_url)
    monkeypatch.setenv("http_proxy", proxy_url)
    monkeypatch.setenv("https_proxy", proxy_url)

    client = GitHubClient()

    assert client.client is not None


def test_fetch_pr_uses_authenticated_pull_api_for_diff(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers.get("accept", ""),
                request.headers.get("authorization"),
            )
        )
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert pr.title == "Demo PR"
    assert pr.head_sha == "abc123"
    assert [file.path for file in pr.files] == ["src/app.py"]
    assert requests == [
        (
            PULL_API_URL,
            "*/*",
            "Bearer private-token",
        ),
        (
            PULL_API_URL,
            "application/vnd.github.diff",
            "Bearer private-token",
        ),
    ]


def test_fetch_pr_allows_public_pr_without_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def fake_run(*args, **kwargs):
        return type("Completed", (), {"returncode": 1, "stdout": ""})()

    monkeypatch.setattr(github_module.subprocess, "run", fake_run)
    authorizations: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers.get("authorization"))
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert pr.title == "Demo PR"
    assert authorizations == [None, None]


def test_post_pr_comment_posts_markdown_to_issue_comments(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "write-token")
    requests: list[tuple[str, str | None, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers.get("authorization"),
                json.loads(request.content.decode()),
            )
        )
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/pull/1#issuecomment-9"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    result = client.post_pr_comment(PullRequestRef("owner", "repo", 1), "# Report")

    assert result.html_url == "https://github.com/owner/repo/pull/1#issuecomment-9"
    assert requests == [
        (
            "https://api.github.com/repos/owner/repo/issues/1/comments",
            "Bearer write-token",
            {"body": "# Report"},
        )
    ]


def test_fetch_file_text_reads_content_at_requested_ref(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")
    seen_requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"print('hello')\n").decode(),
                "size": 15,
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    text = client.fetch_file_text(PullRequestRef("owner", "repo", 1), "src/app.py", "abc123")

    assert text == "print('hello')\n"
    assert seen_requests == [
        (
            "https://api.github.com/repos/owner/repo/contents/src/app.py?ref=abc123",
            "Bearer read-token",
        )
    ]


def test_fetch_tree_paths_returns_blob_paths_at_requested_ref(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://api.github.com/repos/owner/repo/git/trees/abc123?recursive=1"
        )
        assert request.headers.get("authorization") == "Bearer read-token"
        return httpx.Response(
            200,
            json={
                "tree": [
                    {"type": "blob", "path": "src/app.py"},
                    {"type": "tree", "path": "src"},
                    {"type": "blob", "path": "README.md"},
                ]
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    paths = client.fetch_tree_paths(PullRequestRef("owner", "repo", 1), "abc123")

    assert paths == ["src/app.py", "README.md"]


def _pull_api_response(request: httpx.Request) -> httpx.Response:
    if str(request.url) != PULL_API_URL:
        return httpx.Response(404)
    if request.headers.get("accept") == "application/vnd.github.diff":
        return httpx.Response(200, text=DIFF_TEXT)
    return httpx.Response(200, json=PULL_PAYLOAD)
