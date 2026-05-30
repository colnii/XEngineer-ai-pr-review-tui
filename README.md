# XEngineer AI PR Review TUI

A terminal UI for reviewing public GitHub Pull Requests with deterministic rules and AI assistance.

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

- Public GitHub PRs only.
- TUI entry point.
- Rule-based risk findings.
- LLM-assisted summary and suggestions.
- Markdown export.

## Usage

```bash
xpr-review --mock-llm
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

If GitHub anonymous API requests are rate limited, provide a GitHub token:

```bash
export GITHUB_TOKEN="$(gh auth token)"
xpr-review --mock-llm
```

Paste a public PR URL such as:

```text
https://github.com/Textualize/textual/pull/1
```

## Architecture

- TUI: terminal input, progress, display, export.
- Review Core: PR URL parsing, diff parsing, rule analysis, context trimming, report aggregation.
- Adapters: GitHub HTTP client, LLM client, Markdown exporter.

## Model Choice

The app uses an OpenAI-compatible client when `OPENAI_API_KEY` is present. It also supports
`--mock-llm` for deterministic local review output. For judges, `--judge-demo` is the
zero-configuration path and does not require model or GitHub credentials.

## Context Strategy

The app sends PR metadata, deterministic rule findings, and trimmed diff snippets to the model.
Large PRs are trimmed by file count and hunk size, and omitted files are listed in the final report.

## Limitations

- Public GitHub PRs only.
- No automatic PR comments.
- No repository-wide semantic indexing.

## Future Work

- One-command judge runner via npm, for example `npx xengineer-pr-review --judge-demo`,
  backed by a small Node wrapper around the packaged Python app.
- GitHub Action integration.
- Optional token support for private repositories.
- Web UI using the same review core.
- Configurable organization-specific review rules.
