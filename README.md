# XEngineer AI PR Review TUI

A terminal UI for reviewing public GitHub Pull Requests with deterministic rules and AI assistance.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
xpr-review
```

## Current Scope

- Public GitHub PRs only.
- TUI entry point.
- Rule-based risk findings.
- LLM-assisted summary and suggestions.
- Markdown export.
