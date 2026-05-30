import os
import re

import pytest

from xengineer_pr_review.__main__ import build_pipeline
from xengineer_pr_review.export import render_markdown


RUN_LIVE_TEST_ENV = "XENGINEER_RUN_LIVE_AI_REVIEW_TEST"
LIVE_PR_URL_ENV = "XENGINEER_LIVE_AI_REVIEW_PR_URL"
REPORT_PATH_ENV = "XENGINEER_LIVE_AI_REVIEW_REPORT_PATH"

_FILE_ID_RE = re.compile(r"^F\d+$")
_FILE_ID_BLOB_RE = re.compile(r"/F\d+(?:#|$)")


@pytest.mark.skipif(
    os.environ.get(RUN_LIVE_TEST_ENV) != "1",
    reason=f"set {RUN_LIVE_TEST_ENV}=1 to run the live AI review acceptance test",
)
def test_live_ai_review_preserves_hydrated_evidence_references(tmp_path) -> None:
    pr_url = os.environ.get(LIVE_PR_URL_ENV, "").strip()
    if not pr_url:
        pytest.skip(f"set {LIVE_PR_URL_ENV} to the GitHub PR URL under review")
    if not (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        pytest.skip("set DEEPSEEK_API_KEY or OPENAI_API_KEY to run with a real review model")

    report = build_pipeline(language="zh").run(pr_url)
    markdown = render_markdown(report, language="zh")
    report_path = os.environ.get(REPORT_PATH_ENV)
    output_path = tmp_path / "live-ai-review.md" if not report_path else report_path
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    assert report.llm_status == "ok"
    assert report.summary.strip()
    assert _matching_warnings(
        report.warnings,
        (
            "LLM output could not be parsed",
            "Tool round limit reached",
        ),
    ) == []
    assert not _contains_warning(report.warnings, "read_file error")
    assert not _contains_warning(report.warnings, "404")

    changed_files = set(report.changed_files)
    review_items = [*report.findings, *report.suggestions]
    bad_files = [
        path
        for item in review_items
        for path in item.files
        if _FILE_ID_RE.fullmatch(path or "") or path not in changed_files
    ]
    assert bad_files == []

    bad_evidence = []
    for item in review_items:
        for reference in item.evidence:
            path_is_alias = bool(_FILE_ID_RE.fullmatch(reference.path or ""))
            path_is_unknown = reference.kind == "code" and reference.path not in changed_files
            url_is_alias = bool(_FILE_ID_BLOB_RE.search(reference.url or ""))
            if path_is_alias or path_is_unknown or url_is_alias:
                bad_evidence.append(
                    {
                        "file_id": reference.file_id,
                        "path": reference.path,
                        "url": reference.url,
                    }
                )
            if reference.kind == "web" and reference.label:
                assert reference.url
    assert bad_evidence == []


def _contains_warning(warnings: list[str], text: str) -> bool:
    return any(text in warning for warning in warnings)


def _matching_warnings(warnings: list[str], fragments: tuple[str, ...]) -> list[str]:
    return [warning for warning in warnings if any(fragment in warning for fragment in fragments)]
