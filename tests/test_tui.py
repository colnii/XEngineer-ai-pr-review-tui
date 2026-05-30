import asyncio

from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion
from xengineer_pr_review.pipeline import ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


def test_tui_defaults_to_chinese_language() -> None:
    app = ReviewTUI(ReviewPipeline(llm=MockLLMClient()))

    assert app.language == "zh"
    assert app._language_button_text() == "English"
    assert app._phase_text("Ready").startswith("状态：就绪")


def test_tui_accepts_initial_pr_url_and_auto_analyze_flag() -> None:
    app = ReviewTUI(
        ReviewPipeline(llm=MockLLMClient()),
        initial_pr_url="https://github.com/owner/repo/pull/1",
        auto_analyze=True,
    )

    assert app.initial_pr_url == "https://github.com/owner/repo/pull/1"
    assert app.auto_analyze is True


def test_tui_auto_analyzes_on_mount_when_initial_url_is_set(monkeypatch) -> None:
    app = ReviewTUI(
        ReviewPipeline(llm=MockLLMClient()),
        initial_pr_url="https://github.com/owner/repo/pull/1",
        auto_analyze=True,
    )
    calls: list[str] = []

    async def fake_analyze() -> None:
        calls.append(app.initial_pr_url)

    monkeypatch.setattr(app, "_analyze", fake_analyze)

    asyncio.run(app.on_mount())

    assert calls == ["https://github.com/owner/repo/pull/1"]


def test_tui_can_switch_language_and_rerender_current_report(monkeypatch) -> None:
    app = ReviewTUI(ReviewPipeline(llm=MockLLMClient()))
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        repo="owner/repo",
        pr_number=1,
        author="alice",
        additions=3,
        deletions=1,
        summary="Summary text",
        findings=[
            ReviewFinding(
                severity="high",
                title="Sensitive path changed",
                explanation="Auth path changed.",
                files=["src/auth.py"],
            )
        ],
        suggestions=[
            ReviewSuggestion(
                severity="medium",
                title="Check tests",
                body="Add coverage.",
                files=["src/auth.py"],
            )
        ],
        changed_files=["src/auth.py"],
        omitted_files=[],
        warnings=[],
    )
    rendered: list[tuple[str, ReviewReport]] = []

    monkeypatch.setattr(app, "_update_static_language", lambda: None)
    monkeypatch.setattr(app, "_clear_report_logs", lambda: None)
    monkeypatch.setattr(app, "_render_report", lambda item: rendered.append((app.language, item)))
    app.last_report = report

    app._set_language("en")

    assert app.language == "en"
    assert app.last_markdown is not None
    assert app.last_markdown.startswith("# AI PR Review Report")
    assert rendered == [("en", report)]
