from xengineer_pr_review.env import parse_dotenv


def test_parse_dotenv_supports_documented_local_config_subset() -> None:
    values = parse_dotenv(
        "\n".join(
            [
                "# comments and blank lines are ignored",
                "",
                "export DEEPSEEK_API_KEY=deepseek-key",
                'OPENAI_MODEL="gpt-4.1-mini"',
                "PASSWORD=value#fragment",
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
        "WINDOWS_PATH": "C:\\tools\\bin",
    }
