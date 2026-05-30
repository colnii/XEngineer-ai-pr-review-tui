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
- Markdown export.
- Manual PR conversation comment publishing after human confirmation.

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

For deterministic local testing, add `--mock-llm` to publish the mock report body.

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

When a real model is configured, the LangGraph agent can request extra context with:

- `read_file`: read a repository-relative file from the PR head commit.
- `grep_code`: search review-relevant repository files at the PR head commit.
- `web_search`: search public web context only when `TAVILY_API_KEY` is configured.

## Limitations

- Private repository PRs require a local token with read access; GitHub may return
  404 when the token cannot access the repository.
- PR comments are manual only: the TUI requires explicit confirmation before
  publishing a top-level conversation comment.
- Inline review comments and approve/request-changes review states are not implemented.
- No repository-wide semantic indexing.
- Tool calls are bounded; if the model hits a tool limit or a tool fails, the report includes a warning.

## Future Work

- One-command judge runner via npm, for example `npx xengineer-pr-review --judge-demo`,
  backed by a small Node wrapper around the packaged Python app.
- GitHub Action integration.
- Web UI using the same review core.
- Pull request review mode with optional inline comments after diff-line mapping is implemented.
- Configurable organization-specific review rules.
