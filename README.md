# XEngineer AI PR Review TUI

A terminal UI for reviewing public GitHub Pull Requests with deterministic rules and AI assistance.

## Quick Start

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

For real model output:

```bash
export OPENAI_API_KEY="..."
xpr-review
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
`--mock-llm` so the demo can run without network or quota risk.

## Context Strategy

The app sends PR metadata, deterministic rule findings, and trimmed diff snippets to the model.
Large PRs are trimmed by file count and hunk size, and omitted files are listed in the final report.

## Limitations

- Public GitHub PRs only.
- No automatic PR comments.
- No repository-wide semantic indexing.

## Future Work

- GitHub Action integration.
- Optional token support for private repositories.
- Web UI using the same review core.
- Configurable organization-specific review rules.
