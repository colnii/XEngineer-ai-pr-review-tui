from xengineer_pr_review.__main__ import build_pipeline
from xengineer_pr_review.llm import MockLLMClient


def test_build_pipeline_uses_mock_llm_when_requested() -> None:
    pipeline = build_pipeline(use_mock_llm=True)
    assert isinstance(pipeline.llm, MockLLMClient)
