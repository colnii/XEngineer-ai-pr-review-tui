from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from xengineer_pr_review.env import find_dotenv
from xengineer_pr_review.locale import normalize_language


MODEL_CREDENTIAL_KEYS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY")
OPTIONAL_CREDENTIAL_KEYS = ("TAVILY_API_KEY", "GITHUB_TOKEN", "GH_TOKEN")
WRITABLE_CREDENTIAL_KEYS = MODEL_CREDENTIAL_KEYS + OPTIONAL_CREDENTIAL_KEYS


@dataclass(frozen=True)
class CredentialStatus:
    has_deepseek_api_key: bool
    has_openai_api_key: bool
    has_tavily_api_key: bool
    has_github_token: bool
    dotenv_path: Path | None

    @property
    def has_model_key(self) -> bool:
        return self.has_deepseek_api_key or self.has_openai_api_key


def read_credential_status(start: Path | None = None) -> CredentialStatus:
    return CredentialStatus(
        has_deepseek_api_key=_has_env_value("DEEPSEEK_API_KEY"),
        has_openai_api_key=_has_env_value("OPENAI_API_KEY"),
        has_tavily_api_key=_has_env_value("TAVILY_API_KEY"),
        has_github_token=_has_env_value("GITHUB_TOKEN") or _has_env_value("GH_TOKEN"),
        dotenv_path=find_dotenv(start or Path.cwd()),
    )


def format_missing_required_credentials_message(
    language: str | None = "zh",
    *,
    include_tui_onboarding: bool = False,
) -> str:
    lang = normalize_language(language)
    if lang == "en":
        lines = [
            "Missing required model API key: configure DEEPSEEK_API_KEY or OPENAI_API_KEY.",
            "Optional: TAVILY_API_KEY enables web_search; GITHUB_TOKEN/GH_TOKEN enables private PRs, higher GitHub rate limits, and comment publishing.",
            "Recommended GitHub setup: run `gh auth login`, then choose the target account and repository access. The app can read `gh auth token` automatically.",
            "Manual GitHub token fallback: create a fine-grained token in GitHub Settings > Developer settings > Personal access tokens. Private PR review needs Pull requests: read or Contents: read; publishing comments needs Issues: write.",
        ]
        if include_tui_onboarding:
            lines.insert(
                1,
                "Launching the TUI setup panel so you can save a local .env now.",
            )
        return "\n".join(lines)

    lines = [
        "未检测到必需的模型 API Key：请配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。",
        "可选：TAVILY_API_KEY 用于 web_search；GITHUB_TOKEN/GH_TOKEN 用于私有 PR、更高 GitHub API 额度和发布评论。",
        "GitHub token 推荐获取方式：先运行 `gh auth login`，选择目标账号和仓库权限；本工具会自动读取 `gh auth token`。",
        "手动 token 备用方式：在 GitHub Settings > Developer settings > Personal access tokens 里创建 fine-grained token。私有 PR 审查至少需要 Pull requests: read 或 Contents: read；发布评论需要 Issues: write。",
    ]
    if include_tui_onboarding:
        lines.insert(1, "正在打开 TUI 首次配置面板，可把 key 保存到本地 .env。")
    return "\n".join(lines)


def save_runtime_credentials(
    values: Mapping[str, str],
    start: Path | None = None,
) -> Path:
    clean_values = _clean_writable_values(values)
    if not clean_values:
        raise ValueError("at least one credential value is required")

    env_path = _resolve_dotenv_write_path(start or Path.cwd())
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated_lines = _updated_dotenv_lines(existing_lines, clean_values)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return env_path


def _has_env_value(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def _clean_writable_values(values: Mapping[str, str]) -> dict[str, str]:
    clean_values: dict[str, str] = {}
    for key, value in values.items():
        if key not in WRITABLE_CREDENTIAL_KEYS:
            raise ValueError(f"{key} is not a supported runtime credential")
        clean_value = value.strip()
        if not clean_value:
            continue
        if "\n" in clean_value or "\r" in clean_value:
            raise ValueError(f"{key} must be a single line")
        clean_values[key] = clean_value
    return clean_values


def _resolve_dotenv_write_path(start: Path) -> Path:
    existing = find_dotenv(start)
    if existing is not None:
        return existing

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        if (directory / ".git").exists() or (directory / "pyproject.toml").exists():
            return directory / ".env"
    return current / ".env"


def _updated_dotenv_lines(existing_lines: list[str], values: Mapping[str, str]) -> list[str]:
    remaining = dict(values)
    updated_lines: list[str] = []
    for line in existing_lines:
        key = _dotenv_line_key(line)
        if key in remaining:
            updated_lines.append(f"{key}={remaining.pop(key)}")
        else:
            updated_lines.append(line)
    for key, value in remaining.items():
        updated_lines.append(f"{key}={value}")
    return updated_lines


def _dotenv_line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()
    if "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key if key in WRITABLE_CREDENTIAL_KEYS else None
