import os

import pytest

from xengineer_pr_review.env import find_dotenv, loaded_dotenv, parse_dotenv


def test_parse_dotenv_supports_documented_local_config_subset() -> None:
    values = parse_dotenv(
        "\n".join(
            [
                "# comments and blank lines are ignored",
                "",
                "export DEEPSEEK_API_KEY=deepseek-key",
                'OPENAI_MODEL="gpt-4.1-mini"',
                "PASSWORD=value#fragment",
                "HASH_VALUE=#secret",
                "EMPTY_COMMENT= # comment",
                "WINDOWS_PATH=C:\\tools\\bin # comment",
                "INVALID LINE",
                "123BAD=ignored",
            ]
        )
    )

    assert values == {
        "DEEPSEEK_API_KEY": "deepseek-key",
        "OPENAI_MODEL": "gpt-4.1-mini",
        "PASSWORD": "value#fragment",
        "HASH_VALUE": "#secret",
        "EMPTY_COMMENT": "",
        "WINDOWS_PATH": "C:\\tools\\bin",
    }


def test_find_dotenv_searches_parents_until_project_boundary(tmp_path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "src" / "package"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    env_path = repo / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=repo-key\n", encoding="utf-8")

    assert find_dotenv(nested) == env_path

    blocked = tmp_path / "blocked"
    blocked_child = blocked / "child"
    blocked_child.mkdir(parents=True)
    (blocked / "pyproject.toml").write_text("[project]\nname = 'blocked'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=outer-key\n", encoding="utf-8")

    assert find_dotenv(blocked_child) is None


def test_loaded_dotenv_restores_environment_after_exception(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=dotenv\nNEW_VALUE=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "shell")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    with pytest.raises(RuntimeError, match="boom"):
        with loaded_dotenv(tmp_path):
            assert os.environ["EXISTING"] == "dotenv"
            assert os.environ["NEW_VALUE"] == "from-dotenv"
            raise RuntimeError("boom")

    assert os.environ["EXISTING"] == "shell"
    assert "NEW_VALUE" not in os.environ
