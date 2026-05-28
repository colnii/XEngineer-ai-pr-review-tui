from xengineer_pr_review.github import GitHubClient


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
