import pytest

import xengineer_pr_review.__main__ as main_module
from xengineer_pr_review.__main__ import build_pipeline
from xengineer_pr_review.judge_demo import JUDGE_DEMO_URL, JudgeDemoGitHubClient
from xengineer_pr_review.langgraph_agent import LangGraphReviewClient
from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import PostedComment, ReviewReport


PR_URL = "https://github.com/owner/repo/pull/1"


def test_build_pipeline_uses_mock_llm_when_requested() -> None:
    pipeline = build_pipeline(use_mock_llm=True)
    assert isinstance(pipeline.llm, MockLLMClient)
    assert pipeline.llm.language == "zh"


def test_build_pipeline_passes_language_to_mock_llm() -> None:
    pipeline = build_pipeline(use_mock_llm=True, language="en")

    assert isinstance(pipeline.llm, MockLLMClient)
    assert pipeline.llm.language == "en"


def test_build_pipeline_uses_langgraph_deepseek_when_deepseek_key_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    pipeline = build_pipeline(language="en")

    assert isinstance(pipeline.llm, LangGraphReviewClient)
    assert pipeline.llm.language == "en"
    assert pipeline.llm.model == "deepseek-v4-pro"


def test_build_pipeline_uses_langgraph_openai_when_openai_key_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")

    pipeline = build_pipeline(language="zh")

    assert isinstance(pipeline.llm, LangGraphReviewClient)
    assert pipeline.llm.language == "zh"
    assert pipeline.llm.model == "gpt-4.1"


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


class PublishingPipeline:
    def __init__(self, llm_status: str = "ok") -> None:
        self.llm_status = llm_status
        self.runs: list[str] = []
        self.posts: list[tuple[str, str]] = []

    def run(self, pr_url: str) -> ReviewReport:
        self.runs.append(pr_url)
        return ReviewReport(
            pr_title="Improve auth",
            pr_url=pr_url,
            repo="owner/repo",
            pr_number=1,
            author="alice",
            summary="Summary text",
            changed_files=["src/auth.py"],
            llm_status=self.llm_status,
        )

    def post_review_comment(self, pr_url: str, body: str) -> PostedComment:
        self.posts.append((pr_url, body))
        return PostedComment(html_url="https://github.com/owner/repo/pull/1#issuecomment-9")


def test_main_publishes_comment_only_with_explicit_confirmation(monkeypatch, capsys) -> None:
    pipeline = PublishingPipeline()
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--publish-comment",
            "--confirm-publish",
            "--mock-llm",
        ]
    )

    assert pipeline.runs == [PR_URL]
    assert len(pipeline.posts) == 1
    assert pipeline.posts[0][0] == PR_URL
    assert pipeline.posts[0][1].startswith("# AI PR 审查报告")
    assert "Summary text" in pipeline.posts[0][1]
    assert "Published PR comment:" in capsys.readouterr().out


def test_main_refuses_publish_without_confirmation(monkeypatch) -> None:
    pipeline_built = False

    def fake_build_pipeline(**kwargs):
        nonlocal pipeline_built
        pipeline_built = True
        return PublishingPipeline()

    monkeypatch.setattr(main_module, "build_pipeline", fake_build_pipeline)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--pr-url", PR_URL, "--publish-comment"])

    assert exc.value.code == 2
    assert pipeline_built is False


def test_publish_review_comment_refuses_failed_llm_report() -> None:
    pipeline = PublishingPipeline(llm_status="failed")

    with pytest.raises(RuntimeError, match="LLM analysis failed"):
        main_module.publish_review_comment(pipeline, PR_URL, language="zh")

    assert pipeline.runs == [PR_URL]
    assert pipeline.posts == []
