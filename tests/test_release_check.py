import json
import subprocess
from pathlib import Path


def load_release_check():
    from scripts import release_check

    return release_check


def write_project(root: Path, npm_version: str, python_version: str) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "xengineer-pr-review", "version": npm_version}),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "xengineer-pr-review"\nversion = "{python_version}"\n',
        encoding="utf-8",
    )


def test_release_check_rejects_version_mismatch(tmp_path: Path) -> None:
    release_check = load_release_check()
    write_project(tmp_path, npm_version="0.1.0", python_version="0.1.1")

    try:
        release_check.read_project_version(tmp_path)
    except release_check.ReleaseCheckError as error:
        assert "package.json version 0.1.0 != pyproject.toml version 0.1.1" in str(error)
    else:
        raise AssertionError("expected version mismatch to fail")


def test_release_check_reports_unreadable_version_files(tmp_path: Path) -> None:
    release_check = load_release_check()

    try:
        release_check.read_project_version(tmp_path)
    except release_check.ReleaseCheckError as error:
        assert "failed to read package versions" in str(error)
    else:
        raise AssertionError("expected missing version files to fail")


def test_release_check_runs_expected_commands(tmp_path: Path) -> None:
    release_check = load_release_check()
    write_project(tmp_path, npm_version="0.1.0", python_version="0.1.0")
    calls = []

    def runner(command, *, cwd):
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, 0)

    release_check.run_release_checks(tmp_path, runner=runner, python="python3")

    assert calls == [
        (["npm", "test"], tmp_path),
        (["python3", "-m", "pytest"], tmp_path),
        (["python3", "-m", "ruff", "check", "src", "tests", "scripts"], tmp_path),
        (["git", "diff", "--check"], tmp_path),
        (["npm", "pack", "--dry-run"], tmp_path),
    ]


def test_release_check_prefers_project_virtualenv(tmp_path: Path, monkeypatch) -> None:
    release_check = load_release_check()
    monkeypatch.delenv("XENGINEER_RELEASE_PYTHON", raising=False)
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    assert release_check.default_python(tmp_path, platform="linux") == str(python_path)


def test_release_check_allows_python_override(tmp_path: Path, monkeypatch) -> None:
    release_check = load_release_check()
    monkeypatch.setenv("XENGINEER_RELEASE_PYTHON", "/custom/python")

    assert release_check.default_python(tmp_path, platform="linux") == "/custom/python"


def test_release_check_stops_on_command_failure(tmp_path: Path) -> None:
    release_check = load_release_check()
    write_project(tmp_path, npm_version="0.1.0", python_version="0.1.0")

    def runner(command, *, cwd):
        return subprocess.CompletedProcess(command, 2)

    try:
        release_check.run_release_checks(tmp_path, runner=runner, python="python3")
    except release_check.ReleaseCheckError as error:
        assert "npm wrapper tests failed (exit 2)" in str(error)
    else:
        raise AssertionError("expected command failure to fail")


def test_gitignore_excludes_npm_pack_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "*.tgz" in gitignore


def test_scripts_directory_is_importable() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "scripts" / "__init__.py").exists()
