# XEngineer AI PR Review TUI

A terminal UI for reviewing GitHub Pull Requests with deterministic rules and AI assistance. Public PRs can be reviewed anonymously; private repository PRs require a locally configured GitHub token with access to the repository.

中文文档见 [README.zh-CN.md](README.zh-CN.md).

## Quick Start

### Judge Demo

For evaluation, run the built-in deterministic demo first. It does not require
`OPENAI_API_KEY`, `GITHUB_TOKEN`, or a live GitHub PR:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
xpr-review --judge-demo
```

The TUI opens with a demo PR URL prefilled and starts analysis automatically. Use this path
to verify the product flow, report structure, risk signals, suggestions, and Markdown export.

### Normal Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
xpr-review
```

If your shell uses a SOCKS proxy, rerun `pip install -e ".[dev]"` after pulling updates so
the `socksio` dependency is installed.

## Current Scope

- Public GitHub PRs, plus private GitHub PRs when a configured token has access.
- TUI entry point.
- Rule-based risk findings.
- LLM-assisted summary and suggestions.
- Structured evidence on findings/suggestions: code file line ranges and web citation URLs when available.
- Markdown export.
- Manual PR conversation comment publishing after human confirmation, with an optional
  pull request review body mode.
- GitHub Action integration that publishes one PR comment when a PR is opened, reopened,
  or marked ready for review.

## Usage

```bash
xpr-review --mock-llm
```

For a non-interactive command-line review, pass a PR URL and an output target.
Use `--output -` to print the Markdown report to stdout, or pass a file path
to write the report:

```bash
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --mock-llm --output -
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --mock-llm --output review-report.md
```

The zero-configuration judge demo also supports the same headless path:

```bash
xpr-review --judge-demo --output -
```

The TUI defaults to Chinese. To start in English:

```bash
xpr-review --language en
```

For real model output:

```bash
export OPENAI_API_KEY="..."
xpr-review
```

To use DeepSeek instead:

```bash
export DEEPSEEK_API_KEY="..."
# Optional: defaults to deepseek-v4-flash.
export DEEPSEEK_MODEL="deepseek-v4-pro"
xpr-review
```

Real model mode uses a LangGraph-backed review agent. During the LLM review step, the model
may call bounded read-only tools to inspect files at the PR head commit or grep repository code
before returning the final structured report. The normal stop condition is the model returning a
final report without more tool calls; hard limits or tool errors are surfaced in report warnings.
The final report can carry structured evidence objects so code line references and web citations
survive export instead of staying only in the model transcript.

Optional web search can be enabled with Tavily:

```bash
export TAVILY_API_KEY="..."
xpr-review
```

If GitHub anonymous API requests are rate limited, or you need to review a private
repository PR, provide a GitHub token:

```bash
export GITHUB_TOKEN="$(gh auth token)"
xpr-review --mock-llm
```

You can also use `GH_TOKEN`, or run `gh auth login` so the app can read the local
login with `gh auth token`. Fine-grained tokens need at least `Pull requests: read`
or `Contents: read` on the target repository. The TUI does not enter, display, or
store tokens.

To publish the generated report as a top-level PR conversation comment, configure
a token and use the TUI `Publish Comment` button after analysis. The first click
asks for confirmation; the second click posts the comment. Fine-grained tokens need
`Issues: write` or `Pull requests: write` on the target repository.

The same write path is available from the command line, but it requires an
explicit confirmation flag because there is no TUI preview step:

```bash
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --confirm-publish
```

To publish the same Markdown report as a pull request review body instead, select
review mode:

```bash
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --comment-mode review --confirm-publish
```

For deterministic local testing, add `--mock-llm` to publish the mock report body.
In non-interactive automation, `--auto-publish` can be used instead of
`--confirm-publish` to make the intent explicit.

### GitHub Actions Integration

To run XEngineer automatically from another GitHub repository, add this workflow
as `.github/workflows/xengineer-pr-review.yml` in that repository:

```yaml
name: XEngineer PR Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    if: ${{ !github.event.pull_request.draft }}
    steps:
      - name: Run XEngineer PR review
        uses: colnii/XEngineer-ai-pr-review-tui@v1
        with:
          pr-url: ${{ github.event.pull_request.html_url }}
          github-token: ${{ github.token }}
          comment-mode: conversation
          language: en
          deepseek-api-key: ${{ secrets.DEEPSEEK_API_KEY }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          tavily-api-key: ${{ secrets.TAVILY_API_KEY }}
```

The default workflow publishes one new PR conversation comment after the PR is
opened, reopened, or moved out of draft. Set `comment-mode: review` to publish
the report as a pull request review body instead. It does not edit older bot comments and
does not run on every pushed commit. Configure `DEEPSEEK_API_KEY` or
`OPENAI_API_KEY` as a repository secret for real model output; without a model
key, the CLI falls back to deterministic mock output.

After installing the CLI, you can generate the same workflow instead of writing
YAML by hand:

```bash
xpr-review init-action --repo-path /path/to/target/repo --language en
```

If you run the command inside the target repository, omit `--repo-path`. Use
`--comment-mode review` to generate a workflow that publishes pull request review
body comments, `--action-uses owner/repo@ref` to point at a fork, branch, or
release tag, and `--overwrite` only when replacing an existing generated workflow.

### Live AI Review Acceptance Test

The repository includes a skipped-by-default live acceptance test for validating that a
real model review of a target PR keeps evidence references hydrated, without `read_file`
404 warnings or fake `F1` path links. It consumes model quota and reads a live GitHub PR,
so it must be enabled explicitly:

```bash
export DEEPSEEK_API_KEY="..."  # or OPENAI_API_KEY
export XENGINEER_RUN_LIVE_AI_REVIEW_TEST=1
export XENGINEER_LIVE_AI_REVIEW_PR_URL="https://github.com/owner/repo/pull/1"
export XENGINEER_LIVE_AI_REVIEW_REPORT_PATH="live-ai-review.md"  # optional Markdown output
.venv/bin/python -m pytest tests/test_live_ai_review.py
```

If both DeepSeek and OpenAI keys are configured, the app follows its normal provider
priority and uses DeepSeek first. To validate the OpenAI path specifically, prefix the
command with `DEEPSEEK_API_KEY=`.

Paste a PR URL such as:

```text
https://github.com/Textualize/textual/pull/1
```

## Architecture

- TUI: terminal input, progress, display, export.
- Review Core: PR URL parsing, diff parsing, rule analysis, context trimming, report aggregation.
- Adapters: GitHub HTTP client, LangGraph LLM agent, Markdown exporter.

## Third-party Dependencies and Original Work

Top-level third-party dependencies are declared in [pyproject.toml](pyproject.toml):

- `textual`: terminal UI framework.
- `httpx[socks]`: GitHub, model-provider-compatible, and Tavily HTTP requests, including optional SOCKS proxy support.
- `openai`: OpenAI-compatible client used for OpenAI and DeepSeek Chat Completions.
- `langgraph`: agent loop orchestration for model -> tool -> model review flow.
- `pydantic`: typed data validation support for structured models.
- Development-only tools: `pytest` for tests and `ruff` for linting.

External services are GitHub REST APIs, optional OpenAI/DeepSeek model APIs, and optional Tavily web search.
These services are integrated through this project code and are not embedded third-party code.

Original project work includes PR URL parsing, unified diff parsing, deterministic rule analysis, context trimming,
report aggregation/export, Chinese/English TUI presentation, manual PR comment publishing, the LangGraph review client
integration, bounded `read_file`/`grep_code`/`web_search` tool behavior, GitHub file/tree adapters, safety limits,
fallback warnings, and the fake-client test suite. Third-party libraries provide infrastructure; the PR review product
workflow and tool policies are implemented in this repository.

## Model Choice

The app uses DeepSeek when `DEEPSEEK_API_KEY` is present, otherwise it uses OpenAI when
`OPENAI_API_KEY` is present. DeepSeek uses the OpenAI-compatible Chat Completions API with
`https://api.deepseek.com` by default; override `DEEPSEEK_BASE_URL` only for a compatible
gateway. `DEEPSEEK_MODEL` defaults to `deepseek-v4-flash`.

The app also supports `--mock-llm` for deterministic local review output. For judges,
`--judge-demo` is the zero-configuration path and does not require model or GitHub credentials.

## Context Strategy

The app sends PR metadata, deterministic rule findings, and diff snippets to the model.
Review-relevant files are no longer trimmed by count. The prompt skips obvious low-signal files
such as lockfiles, generated bundles, binary assets, and archives; long hunks are still trimmed.
Skipped files are listed in the final report.

Diff hunks are indexed with changed line ranges. Changed files also get short IDs such as `F1`,
so the model can call `read_file(file_id="F1")` instead of copying long repository paths.
`read_file` and `grep_code` return line-numbered code context, and `web_search` returns stable IDs
such as `[W1]` with the result URL and snippet. The model is prompted to copy those references into
`evidence` objects on risks or suggestions; the TUI and Markdown export render that evidence under
the corresponding review item.

When a real model is configured, the LangGraph agent can request extra context with:

- `read_file`: read a repository-relative file from the PR head commit.
- `grep_code`: search review-relevant repository files at the PR head commit.
- `web_search`: search public web context only when `TAVILY_API_KEY` is configured.

## Limitations

- Private repository PRs require a local token with read access; GitHub may return
  404 when the token cannot access the repository.
- GitHub Action comments default to top-level PR conversation comments. The generated
  workflow publishes a new comment per trigger and does not edit an older XEngineer comment.
- Pull request review body comments are supported with `--comment-mode review`, but inline
  review comments and approve/request-changes review states are not implemented.
- No repository-wide semantic indexing.
- Tool calls are bounded; if the model hits a tool limit or a tool fails, the report includes a warning.

## Future Work

- One-command judge runner via npm, for example `npx xengineer-pr-review --judge-demo`,
  backed by a small Node wrapper around the packaged Python app.
- Web UI using the same review core.
- Optional inline review comments after GitHub inline-position mapping is implemented.
- Configurable organization-specific review rules.
