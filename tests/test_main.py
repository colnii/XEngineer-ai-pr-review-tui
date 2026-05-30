from xengineer_pr_review.__main__ import build_pipeline
from xengineer_pr_review.judge_demo import JUDGE_DEMO_URL, JudgeDemoGitHubClient
from xengineer_pr_review.llm import MockLLMClient


def test_build_pipeline_uses_mock_llm_when_requested() -> None:
    pipeline = build_pipeline(use_mock_llm=True)
    assert isinstance(pipeline.llm, MockLLMClient)
    assert pipeline.llm.language == "zh"


def test_build_pipeline_passes_language_to_mock_llm() -> None:
    pipeline = build_pipeline(use_mock_llm=True, language="en")

    assert isinstance(pipeline.llm, MockLLMClient)
    assert pipeline.llm.language == "en"


def test_build_pipeline_uses_judge_demo_fixture_when_requested() -> None:
    pipeline = build_pipeline(judge_demo=True)

    assert isinstance(pipeline.github, JudgeDemoGitHubClient)
    assert isinstance(pipeline.llm, MockLLMClient)
    assert pipeline.llm.language == "zh"

    report = pipeline.run(JUDGE_DEMO_URL)

    assert report.repo == "colnii/xengineer-demo"
    assert report.pr_number == 7
    assert report.changed_files
    assert report.findings
    assert report.suggestions
    assert report.llm_status == "ok"
