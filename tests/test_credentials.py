import stat

from xengineer_pr_review.credentials import (
    CredentialStatus,
    read_credential_status,
    save_runtime_credentials,
)


def test_credential_status_requires_deepseek_or_openai(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)

    status = read_credential_status()

    assert status == CredentialStatus(
        has_deepseek_api_key=False,
        has_openai_api_key=False,
        has_tavily_api_key=False,
        has_github_token=False,
        dotenv_path=None,
    )
    assert status.has_model_key is False


def test_credential_status_accepts_either_model_key(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert read_credential_status().has_model_key is True

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert read_credential_status().has_model_key is True


def test_save_runtime_credentials_creates_local_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    env_path = save_runtime_credentials(
        {
            "DEEPSEEK_API_KEY": "deepseek-key",
            "TAVILY_API_KEY": "tavily-key",
            "GITHUB_TOKEN": "github-token",
        }
    )

    assert env_path == tmp_path / ".env"
    assert env_path.read_text(encoding="utf-8").splitlines() == [
        "DEEPSEEK_API_KEY=deepseek-key",
        "TAVILY_API_KEY=tavily-key",
        "GITHUB_TOKEN=github-token",
    ]
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_save_runtime_credentials_updates_existing_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=old-key",
                "OPENAI_MODEL=gpt-4.1-mini",
                "TAVILY_API_KEY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    saved_path = save_runtime_credentials(
        {
            "DEEPSEEK_API_KEY": "new-key",
            "TAVILY_API_KEY": "tavily-key",
        }
    )

    assert saved_path == env_path
    assert env_path.read_text(encoding="utf-8").splitlines() == [
        "DEEPSEEK_API_KEY=new-key",
        "OPENAI_MODEL=gpt-4.1-mini",
        "TAVILY_API_KEY=tavily-key",
    ]


def test_save_runtime_credentials_preserves_export_and_quote_style(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                'export DEEPSEEK_API_KEY="old-key"',
                "OPENAI_API_KEY='old-openai-key'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    save_runtime_credentials(
        {
            "DEEPSEEK_API_KEY": "new-key",
            "OPENAI_API_KEY": "new-openai-key",
        }
    )

    assert env_path.read_text(encoding="utf-8").splitlines() == [
        'export DEEPSEEK_API_KEY="new-key"',
        "OPENAI_API_KEY='new-openai-key'",
    ]


def test_save_runtime_credentials_rejects_multiline_values(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    try:
        save_runtime_credentials({"OPENAI_API_KEY": "line1\nline2"})
    except ValueError as exc:
        assert "must be a single line" in str(exc)
    else:
        raise AssertionError("save_runtime_credentials should reject multiline values")

    assert not (tmp_path / ".env").exists()
