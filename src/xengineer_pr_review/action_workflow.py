from __future__ import annotations

from pathlib import Path


DEFAULT_ACTION_USES = "colnii/XEngineer-ai-pr-review-tui@v1"
WORKFLOW_RELATIVE_PATH = Path(".github/workflows/xengineer-pr-review.yml")


def render_action_workflow(
    action_uses: str = DEFAULT_ACTION_USES,
    language: str = "zh",
) -> str:
    # GitHub expressions need doubled braces inside this f-string template.
    return f"""name: XEngineer PR Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    if: ${{{{ !github.event.pull_request.draft }}}}
    steps:
      - name: Run XEngineer PR review
        uses: {action_uses}
        with:
          pr-url: ${{{{ github.event.pull_request.html_url }}}}
          github-token: ${{{{ github.token }}}}
          language: {language}
          deepseek-api-key: ${{{{ secrets.DEEPSEEK_API_KEY }}}}
          openai-api-key: ${{{{ secrets.OPENAI_API_KEY }}}}
          tavily-api-key: ${{{{ secrets.TAVILY_API_KEY }}}}
"""


def init_action_workflow(
    repo_path: str | Path = ".",
    action_uses: str = DEFAULT_ACTION_USES,
    language: str = "zh",
    overwrite: bool = False,
) -> Path:
    repo_root = Path(repo_path).expanduser().resolve()
    if not repo_root.is_dir():
        raise NotADirectoryError(f"Repository path does not exist: {repo_root}")

    workflow_path = repo_root / WORKFLOW_RELATIVE_PATH
    if workflow_path.exists() and not overwrite:
        raise FileExistsError(f"GitHub Actions workflow already exists: {workflow_path}")

    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        render_action_workflow(action_uses=action_uses, language=language),
        encoding="utf-8",
    )
    return workflow_path
