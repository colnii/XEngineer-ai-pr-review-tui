from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MISSING = object()


@contextmanager
def loaded_dotenv(start: Path | None = None) -> Iterator[Path | None]:
    """Load the nearest project .env while a CLI command is running.

    The parser intentionally supports the local-development subset this project
    documents: KEY=value lines, optional export prefixes, quotes, and inline
    comments. Multiline values and full shell expansion are out of scope.
    """

    env_path = find_dotenv(start or Path.cwd())
    if env_path is None:
        yield None
        return

    values = parse_dotenv(env_path.read_text(encoding="utf-8"))
    previous = {key: os.environ.get(key, _MISSING) for key in values}
    os.environ.update(values)
    try:
        yield env_path
    finally:
        for key, value in previous.items():
            if value is _MISSING:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)


def find_dotenv(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists() or (directory / "pyproject.toml").exists():
            return None
    return None


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            continue
        values[key] = _clean_dotenv_value(raw_value)
    return values


def _clean_dotenv_value(raw_value: str) -> str:
    value = _strip_inline_comment(raw_value.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character in ("'", '"'):
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
            continue
        if character == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value
