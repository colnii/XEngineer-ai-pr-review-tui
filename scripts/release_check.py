#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Callable


class ReleaseCheckError(Exception):
    """Raised when the package is not ready to publish."""


def read_project_version(root: Path) -> str:
    try:
        package_json = json.loads((root / "package.json").read_text(encoding="utf-8"))
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        npm_version = package_json["version"]
        python_version = pyproject["project"]["version"]
    except (
        OSError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise ReleaseCheckError(f"failed to read package versions: {error}") from error

    if npm_version != python_version:
        raise ReleaseCheckError(
            f"package.json version {npm_version} != pyproject.toml version {python_version}"
        )
    return npm_version


def npm_command(platform: str = sys.platform) -> str:
    if platform == "win32":
        return "npm.cmd"
    return "npm"


def release_commands(python: str, *, platform: str = sys.platform) -> list[tuple[str, list[str]]]:
    npm = npm_command(platform)
    return [
        ("npm wrapper tests", [npm, "test"]),
        ("Python tests", [python, "-m", "pytest"]),
        ("ruff", [python, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("git whitespace check", ["git", "diff", "--check"]),
        ("npm package dry run", [npm, "pack", "--dry-run"]),
    ]


def default_python(root: Path, *, platform: str = sys.platform) -> str:
    if override := os.environ.get("XENGINEER_RELEASE_PYTHON"):
        return override

    python_path = root / ".venv"
    if platform == "win32":
        python_path = python_path / "Scripts" / "python.exe"
    else:
        python_path = python_path / "bin" / "python"
    if python_path.exists():
        return str(python_path)
    return sys.executable


def run_release_checks(
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    python: str | None = None,
) -> None:
    root = root.resolve()
    python = python or default_python(root)
    version = read_project_version(root)
    commands = release_commands(python)

    print(f"Checking xengineer-pr-review {version} before npm publish.", flush=True)
    for index, (label, command) in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] {label}: {shlex.join(command)}", flush=True)
        result = runner(command, cwd=root)
        if result.returncode != 0:
            raise ReleaseCheckError(f"{label} failed (exit {result.returncode})")

    print("Release check passed. Publish manually with: npm publish --access public", flush=True)


def main() -> int:
    try:
        run_release_checks(Path.cwd())
    except ReleaseCheckError as error:
        print(f"release-check: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
