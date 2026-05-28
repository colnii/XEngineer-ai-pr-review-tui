import httpx

from xengineer_pr_review.github import GitHubClient
from xengineer_pr_review.models import PullRequestRef


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


def test_fetch_pr_follows_diff_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://api.github.com/repos/owner/repo/pulls/1":
            return httpx.Response(
                200,
                json={
                    "title": "Demo PR",
                    "user": {"login": "alice"},
                    "base": {"ref": "main"},
                    "head": {"ref": "feature"},
                },
            )
        if str(request.url) == "https://github.com/owner/repo/pull/1.diff":
            return httpx.Response(
                302,
                headers={"Location": "https://patch-diff.githubusercontent.com/raw/owner/repo/pull/1.diff"},
            )
        if str(request.url) == "https://patch-diff.githubusercontent.com/raw/owner/repo/pull/1.diff":
            return httpx.Response(
                200,
                text="""diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1,2 @@
-old = True
+new = True
""",
            )
        return httpx.Response(404)

    client = GitHubClient(transport=httpx.MockTransport(handler))

    pr = client.fetch_pr(PullRequestRef("owner", "repo", 1))

    assert pr.title == "Demo PR"
    assert [file.path for file in pr.files] == ["src/app.py"]
