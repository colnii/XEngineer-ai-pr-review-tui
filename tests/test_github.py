from xengineer_pr_review.github import GitHubClient


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
