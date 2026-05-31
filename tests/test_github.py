import base64
import json

import httpx
import pytest

import xengineer_pr_review.github as github_module
from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.models import InlineReviewComment, PullRequestRef


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
        (
            "https://api.github.com/repos/owner/repo/pulls/1/commits?per_page=100",
            "*/*",
            "Bearer private-token",
        ),
        (
            "https://api.github.com/repos/owner/repo/issues/1/comments?per_page=100",
            "*/*",
            "Bearer private-token",
        ),
        (
            "https://api.github.com/repos/owner/repo/pulls/1/reviews?per_page=100",
            "*/*",
            "Bearer private-token",
        ),
        (
            "https://api.github.com/repos/owner/repo/pulls/1/comments?per_page=100",
            "*/*",
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
    assert authorizations == [None, None, None, None, None, None]


def test_fetch_pr_includes_pull_request_activity(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://api.github.com/repos/owner/repo/issues/1/comments?per_page=100":
            return httpx.Response(
                200,
                json=[
                    {
                        "user": {"login": "reviewer"},
                        "body": "Please rerun after the latest commit.",
                        "created_at": "2026-05-30T10:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/1#issuecomment-1",
                    }
                ],
            )
        if url == "https://api.github.com/repos/owner/repo/pulls/1/reviews?per_page=100":
            return httpx.Response(
                200,
                json=[
                    {
                        "user": {"login": "maintainer"},
                        "body": "Looks close, but tests are missing.",
                        "state": "COMMENTED",
                        "submitted_at": "2026-05-30T11:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-1",
                    }
                ],
            )
        if url == "https://api.github.com/repos/owner/repo/pulls/1/comments?per_page=100":
            return httpx.Response(
                200,
                json=[
                    {
                        "user": {"login": "maintainer"},
                        "body": "This branch misses the manual trigger path.",
                        "path": "action.yml",
                        "line": 57,
                        "created_at": "2026-05-30T12:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/1#discussion_r1",
                    }
                ],
            )
        if url == "https://api.github.com/repos/owner/repo/pulls/1/commits?per_page=100":
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "abcdef1234567890",
                        "commit": {
                            "message": "feat: add action trigger",
                            "author": {"name": "Alice", "date": "2026-05-30T09:00:00Z"},
                        },
                        "html_url": "https://github.com/owner/repo/commit/abcdef1",
                    }
                ],
            )
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert [(activity.kind, activity.author) for activity in pr.activities] == [
        ("commit", "Alice"),
        ("conversation", "reviewer"),
        ("review", "maintainer"),
        ("inline", "maintainer"),
    ]
    assert pr.activities[0].commit_sha == "abcdef1"
    assert pr.activities[1].body == "Please rerun after the latest commit."
    assert pr.activities[2].state == "COMMENTED"
    assert pr.activities[3].path == "action.yml"
    assert pr.activities[3].line == 57


def test_fetch_pr_continues_when_one_activity_endpoint_fails(monkeypatch, caplog) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")
    caplog.set_level("WARNING")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://api.github.com/repos/owner/repo/issues/1/comments?per_page=100":
            return httpx.Response(403, json={"message": "rate limited"})
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert pr.title == "Demo PR"
    assert pr.activities == ()
    assert "Failed to fetch PR conversation comments" in caplog.text


def test_fetch_pr_continues_when_activity_payload_is_invalid(monkeypatch, caplog) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")
    caplog.set_level("WARNING")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://api.github.com/repos/owner/repo/pulls/1/reviews?per_page=100":
            return httpx.Response(200, content=b"not-json")
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert pr.title == "Demo PR"
    assert pr.activities == ()
    assert "Failed to fetch PR reviews" in caplog.text


def test_fetch_pr_activity_pagination_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url == "https://api.github.com/repos/owner/repo/pulls/1/commits?per_page=100":
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": f"{index:07d}",
                        "commit": {"message": f"commit {index}", "author": {"name": "Alice"}},
                    }
                    for index in range(100)
                ],
                headers={
                    "Link": (
                        '<https://api.github.com/repos/owner/repo/pulls/1/commits'
                        '?page=2&per_page=100>; rel="next"'
                    )
                },
            )
        return _pull_api_response(request)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert len([activity for activity in pr.activities if activity.kind == "commit"]) == 100
    assert not any("page=2" in request for request in requests)


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


def test_post_pr_review_posts_markdown_to_pull_reviews(monkeypatch) -> None:
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
            json={"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-9"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    result = client.post_pr_review(PullRequestRef("owner", "repo", 1), "# Report")

    assert result.html_url == "https://github.com/owner/repo/pull/1#pullrequestreview-9"
    assert requests == [
        (
            "https://api.github.com/repos/owner/repo/pulls/1/reviews",
            "Bearer write-token",
            {"body": "# Report", "event": "COMMENT"},
        )
    ]


def test_post_pr_review_can_request_changes(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "write-token")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-10"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    result = client.post_pr_review(
        PullRequestRef("owner", "repo", 1),
        "# Report",
        review_action="request-changes",
    )

    assert result.html_url.endswith("#pullrequestreview-10")
    assert requests == [{"body": "# Report", "event": "REQUEST_CHANGES"}]


def test_post_pr_review_can_approve(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "write-token")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-11"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    result = client.post_pr_review(
        PullRequestRef("owner", "repo", 1),
        "# Report",
        review_action="approve",
    )

    assert result.html_url.endswith("#pullrequestreview-11")
    assert requests == [{"body": "# Report", "event": "APPROVE"}]


def test_post_pr_review_can_include_inline_comments(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "write-token")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-13"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    result = client.post_pr_review(
        PullRequestRef("owner", "repo", 1),
        "# Report",
        comments=[
            InlineReviewComment(
                path="src/auth.py",
                body="XEngineer: check token handling.",
                line=12,
                start_line=10,
            )
        ],
        commit_id="abc123",
    )

    assert result.html_url.endswith("#pullrequestreview-13")
    assert requests == [
        {
            "body": "# Report",
            "event": "COMMENT",
            "commit_id": "abc123",
            "comments": [
                {
                    "path": "src/auth.py",
                    "body": "XEngineer: check token handling.",
                    "line": 12,
                    "side": "RIGHT",
                    "start_line": 10,
                    "start_side": "RIGHT",
                }
            ],
        }
    ]


def test_post_pr_review_truncates_oversized_body(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "write-token")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-12"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    client.post_pr_review(PullRequestRef("owner", "repo", 1), "a" * 70_000)

    body = requests[0]["body"]
    assert len(body) <= 65_536
    assert "truncated by XEngineer" in body


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


def test_fetch_file_text_rejects_invalid_base64(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": "@@@not-base64@@@",
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="not valid UTF-8 base64"):
        client.fetch_file_text(PullRequestRef("owner", "repo", 1), "src/app.py", "abc123")


def test_fetch_file_text_accepts_base64_whitespace(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")
    encoded = base64.b64encode(b"print('hello')\n").decode()
    wrapped = f" {encoded[:5]}\r\n\t{encoded[5:]} "

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": wrapped,
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    text = client.fetch_file_text(PullRequestRef("owner", "repo", 1), "src/app.py", "abc123")

    assert text == "print('hello')\n"


def test_fetch_file_text_rejects_oversized_content(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "encoding": "none",
                "content": "",
                "size": 1_000_001,
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="larger than supported limit"):
        client.fetch_file_text(PullRequestRef("owner", "repo", 1), "src/large.py", "abc123")


def test_fetch_file_text_rejects_non_file_content(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "type": "submodule",
                "size": 0,
                "encoding": "none",
                "content": "",
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="is not a regular file"):
        client.fetch_file_text(PullRequestRef("owner", "repo", 1), "vendor/lib", "abc123")


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


def test_fetch_tree_paths_rejects_truncated_recursive_tree(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "read-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "truncated": True,
                "tree": [
                    {"type": "blob", "path": "src/app.py"},
                ],
            },
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="tree for abc123 is truncated"):
        client.fetch_tree_paths(PullRequestRef("owner", "repo", 1), "abc123")


def _pull_api_response(request: httpx.Request) -> httpx.Response:
    activity_urls = {
        "https://api.github.com/repos/owner/repo/pulls/1/commits?per_page=100",
        "https://api.github.com/repos/owner/repo/issues/1/comments?per_page=100",
        "https://api.github.com/repos/owner/repo/pulls/1/reviews?per_page=100",
        "https://api.github.com/repos/owner/repo/pulls/1/comments?per_page=100",
    }
    if str(request.url) in activity_urls:
        return httpx.Response(200, json=[])
    if str(request.url) != PULL_API_URL:
        return httpx.Response(404)
    if request.headers.get("accept") == "application/vnd.github.diff":
        return httpx.Response(200, text=DIFF_TEXT)
    return httpx.Response(200, json=PULL_PAYLOAD)
