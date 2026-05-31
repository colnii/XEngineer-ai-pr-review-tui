import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import xengineer_pr_review.__main__ as main_module
from xengineer_pr_review.__main__ import MissingModelConfigurationError, build_pipeline
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


def test_build_pipeline_requires_real_model_key_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingModelConfigurationError, match="Real model review requires"):
        build_pipeline()


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
    assert pipeline.llm.max_tool_rounds == 20


def test_build_pipeline_passes_max_tool_rounds_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("XENGINEER_MAX_TOOL_ROUNDS", "12")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    pipeline = build_pipeline(language="zh")

    assert isinstance(pipeline.llm, LangGraphReviewClient)
    assert pipeline.llm.max_tool_rounds == 12


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
        self.posts: list[tuple[str, str, str, str]] = []

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

    def post_review_comment(
        self,
        pr_url: str,
        body: str,
        comment_mode: str = "conversation",
        review_action: str = "comment",
    ) -> PostedComment:
        self.posts.append((pr_url, body, comment_mode, review_action))
        suffix = "pullrequestreview-9" if comment_mode == "review" else "issuecomment-9"
        return PostedComment(html_url=f"https://github.com/owner/repo/pull/1#{suffix}")


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
    assert pipeline.posts[0][2] == "conversation"
    assert pipeline.posts[0][3] == "comment"
    assert "Summary text" in pipeline.posts[0][1]
    assert (
        "Published PR comment: https://github.com/owner/repo/pull/1#issuecomment-9"
        in capsys.readouterr().out
    )


def test_main_publishes_pull_request_review_when_requested(monkeypatch, capsys) -> None:
    pipeline = PublishingPipeline()
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--publish-comment",
            "--comment-mode",
            "review",
            "--confirm-publish",
            "--mock-llm",
        ]
    )

    assert pipeline.runs == [PR_URL]
    assert len(pipeline.posts) == 1
    assert pipeline.posts[0][0] == PR_URL
    assert pipeline.posts[0][2] == "review"
    assert pipeline.posts[0][3] == "comment"
    output = capsys.readouterr().out
    assert "Published PR review: https://github.com/owner/repo/pull/1#pullrequestreview-9" in output
    assert "Published PR comment:" not in output


def test_main_can_publish_pull_request_review_requesting_changes(monkeypatch) -> None:
    pipeline = PublishingPipeline()
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--publish-comment",
            "--comment-mode",
            "review",
            "--review-action",
            "request-changes",
            "--confirm-publish",
        ]
    )

    assert pipeline.posts[0][2] == "review"
    assert pipeline.posts[0][3] == "request-changes"


def test_main_publishes_comment_with_auto_publish_for_automation(monkeypatch, capsys) -> None:
    pipeline = PublishingPipeline()
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--publish-comment",
            "--auto-publish",
            "--mock-llm",
        ]
    )

    assert pipeline.runs == [PR_URL]
    assert len(pipeline.posts) == 1
    assert "Published PR comment:" in capsys.readouterr().out


def test_main_loads_dotenv_before_building_pipeline(monkeypatch, tmp_path, capsys) -> None:
    pipeline = PublishingPipeline()
    seen_env = {}

    def fake_build_pipeline(**kwargs):
        seen_env["DEEPSEEK_API_KEY"] = main_module.os.environ.get("DEEPSEEK_API_KEY")
        seen_env["DEEPSEEK_MODEL"] = main_module.os.environ.get("DEEPSEEK_MODEL")
        seen_env["OPENAI_API_KEY"] = main_module.os.environ.get("OPENAI_API_KEY")
        return pipeline

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=dotenv-deepseek",
                'DEEPSEEK_MODEL="dotenv-model"',
                "OPENAI_API_KEY=dotenv-openai",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "shell-deepseek")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(main_module, "build_pipeline", fake_build_pipeline)

    main_module.main(["--pr-url", PR_URL, "--output", "-"])

    assert seen_env == {
        "DEEPSEEK_API_KEY": "dotenv-deepseek",
        "DEEPSEEK_MODEL": "dotenv-model",
        "OPENAI_API_KEY": "dotenv-openai",
    }
    assert main_module.os.environ["DEEPSEEK_API_KEY"] == "shell-deepseek"
    assert "DEEPSEEK_MODEL" not in main_module.os.environ
    assert "OPENAI_API_KEY" not in main_module.os.environ
    assert "# AI PR 审查报告" in capsys.readouterr().out


def test_env_example_documents_runtime_configuration() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"

    content = env_example.read_text(encoding="utf-8")

    for key in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "TAVILY_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "XENGINEER_MAX_TOOL_ROUNDS",
        "XENGINEER_RUN_LIVE_AI_REVIEW_TEST",
        "XENGINEER_LIVE_AI_REVIEW_PR_URL",
        "XENGINEER_LIVE_AI_REVIEW_REPORT_PATH",
    ):
        assert f"{key}=" in content


def test_main_writes_report_to_output_path(monkeypatch, tmp_path, capsys) -> None:
    pipeline = PublishingPipeline()
    output_path = tmp_path / "review-report.md"
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--mock-llm",
            "--output",
            str(output_path),
        ]
    )

    markdown = output_path.read_text()
    assert pipeline.runs == [PR_URL]
    assert pipeline.posts == []
    assert markdown.startswith("# AI PR 审查报告")
    assert "Summary text" in markdown
    assert f"Wrote review report: {output_path}" in capsys.readouterr().out


def test_main_prints_report_when_output_is_dash(monkeypatch, capsys) -> None:
    pipeline = PublishingPipeline()
    monkeypatch.setattr(main_module, "build_pipeline", lambda **kwargs: pipeline)

    main_module.main(
        [
            "--pr-url",
            PR_URL,
            "--mock-llm",
            "--output",
            "-",
        ]
    )

    assert pipeline.runs == [PR_URL]
    assert pipeline.posts == []
    output = capsys.readouterr().out
    assert output.startswith("# AI PR 审查报告")
    assert "Summary text" in output
    assert "Wrote review report:" not in output


def test_main_can_output_judge_demo_report_without_pr_url(monkeypatch, capsys) -> None:
    pipeline = PublishingPipeline()
    build_kwargs = {}

    def fake_build_pipeline(**kwargs):
        build_kwargs.update(kwargs)
        return pipeline

    monkeypatch.setattr(main_module, "build_pipeline", fake_build_pipeline)

    main_module.main(["--judge-demo", "--output", "-"])

    assert build_kwargs["judge_demo"] is True
    assert pipeline.runs == [main_module.JUDGE_DEMO_URL]
    assert "# AI PR 审查报告" in capsys.readouterr().out


def test_main_refuses_empty_output_path(monkeypatch) -> None:
    pipeline_built = False

    def fake_build_pipeline(**kwargs):
        nonlocal pipeline_built
        pipeline_built = True
        return PublishingPipeline()

    monkeypatch.setattr(main_module, "build_pipeline", fake_build_pipeline)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--pr-url", PR_URL, "--output", ""])

    assert exc.value.code == 2
    assert pipeline_built is False


def test_main_refuses_real_review_without_model_key(monkeypatch) -> None:
    @contextmanager
    def fake_loaded_dotenv() -> Iterator[None]:
        yield None

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(main_module, "loaded_dotenv", fake_loaded_dotenv)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--pr-url", PR_URL, "--output", "-"])

    assert exc.value.code == 2


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


def test_main_refuses_auto_publish_without_publish_comment(monkeypatch) -> None:
    pipeline_built = False

    def fake_build_pipeline(**kwargs):
        nonlocal pipeline_built
        pipeline_built = True
        return PublishingPipeline()

    monkeypatch.setattr(main_module, "build_pipeline", fake_build_pipeline)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--pr-url", PR_URL, "--auto-publish"])

    assert exc.value.code == 2
    assert pipeline_built is False


def test_publish_review_comment_refuses_failed_llm_report() -> None:
    pipeline = PublishingPipeline(llm_status="failed")

    with pytest.raises(RuntimeError, match="LLM analysis failed"):
        main_module.publish_review_comment(pipeline, PR_URL, language="zh")

    assert pipeline.runs == [PR_URL]
    assert pipeline.posts == []


def test_main_init_action_writes_workflow(tmp_path, capsys) -> None:
    main_module.main(
        [
            "init-action",
            "--repo-path",
            str(tmp_path),
            "--action-uses",
            "owner/xengineer@v1",
            "--comment-mode",
            "review",
            "--language",
            "en",
        ]
    )

    workflow_path = tmp_path / ".github" / "workflows" / "xengineer-pr-review.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "uses: owner/xengineer@v1" in workflow
    assert "comment-mode: review" in workflow
    assert f"Wrote GitHub Actions workflow: {workflow_path}" in capsys.readouterr().out


def test_main_init_action_does_not_load_dotenv(monkeypatch, tmp_path) -> None:
    dotenv_loaded = False

    @contextmanager
    def fake_loaded_dotenv() -> Iterator[None]:
        nonlocal dotenv_loaded
        dotenv_loaded = True
        yield None

    monkeypatch.setattr(main_module, "loaded_dotenv", fake_loaded_dotenv)

    main_module.main(["init-action", "--repo-path", str(tmp_path)])

    assert dotenv_loaded is False


def test_main_help_lists_init_action(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main_module.main(["--help"])

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "init-action" in output
    assert "--mock-llm" not in output


def test_main_init_action_works_from_console_argv(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "xpr-review",
            "init-action",
            "--repo-path",
            str(tmp_path),
        ],
    )

    main_module.main()

    assert (tmp_path / ".github" / "workflows" / "xengineer-pr-review.yml").exists()


def test_main_init_action_refuses_existing_workflow(tmp_path) -> None:
    workflow_path = tmp_path / ".github" / "workflows" / "xengineer-pr-review.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("existing workflow\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main_module.main(["init-action", "--repo-path", str(tmp_path)])

    assert exc.value.code == 2
    assert workflow_path.read_text(encoding="utf-8") == "existing workflow\n"
