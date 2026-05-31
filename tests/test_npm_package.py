import json
from pathlib import Path


def test_npm_package_exposes_npx_entrypoint() -> None:
    root = Path(__file__).resolve().parents[1]
    package_json = json.loads((root / "package.json").read_text(encoding="utf-8"))

    assert package_json["name"] == "xengineer-pr-review"
    assert package_json["bin"] == {"xengineer-pr-review": "./bin/xengineer-pr-review.js"}
    assert "pyproject.toml" in package_json["files"]
    assert "src/xengineer_pr_review/*.py" in package_json["files"]
    assert "src/xengineer_pr_review/**/*.py" in package_json["files"]
    assert "src/" not in package_json["files"]
    assert package_json["scripts"]["test:python"] == "python3 -m pytest"
    assert package_json["scripts"]["test:all"] == "npm test && python3 -m pytest"


def test_npm_wrapper_runs_existing_python_module() -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "bin" / "xengineer-pr-review.js").read_text(encoding="utf-8")

    assert "xengineer_pr_review" in wrapper
    assert "XENGINEER_PYTHON" in wrapper
