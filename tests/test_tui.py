import asyncio

import pytest

from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion
from xengineer_pr_review.pipeline import ReviewPipeline
from xengineer_pr_review.tui import ReviewTUI


class PostingPipeline:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []

    def post_review_comment(self, pr_url: str, body: str):
        self.posts.append((pr_url, body))
        return type(
            "Posted",
            (),
            {"html_url": "https://github.com/owner/repo/pull/1#issuecomment-9"},
        )()


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


def test_tui_publish_requires_analyzed_report(monkeypatch) -> None:
    app = ReviewTUI(PostingPipeline())
    statuses: list[str] = []
    monkeypatch.setattr(app, "_update_status", lambda text: statuses.append(text))

    app._request_publish_confirmation()

    assert statuses == ["请先分析 PR 再发布评论"]


def test_tui_publish_first_click_arms_confirmation(monkeypatch) -> None:
    app = ReviewTUI(PostingPipeline())
    app.last_report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
    )
    app.last_markdown = "# Report"
    statuses: list[str] = []
    monkeypatch.setattr(app, "_update_status", lambda text: statuses.append(text))

    app._request_publish_confirmation()

    assert app.publish_confirmation_pending is True
    assert "再次点击" in statuses[-1]


def test_tui_confirm_publish_posts_markdown(monkeypatch) -> None:
    pipeline = PostingPipeline()
    app = ReviewTUI(pipeline)
    app.last_report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
    )
    app.last_markdown = "# Report"
    app.publish_confirmation_pending = True
    statuses: list[str] = []
    monkeypatch.setattr(app, "_update_status", lambda text: statuses.append(text))

    app._confirm_publish()

    assert pipeline.posts == [("https://github.com/owner/repo/pull/1", "# Report")]
    assert app.publish_confirmation_pending is False
    assert "已发布评论" in statuses[-1]


def test_tui_confirm_publish_does_not_post_without_pending_confirmation(monkeypatch) -> None:
    pipeline = PostingPipeline()
    app = ReviewTUI(pipeline)
    app.last_report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
    )
    app.last_markdown = "# Report"
    statuses: list[str] = []
    monkeypatch.setattr(app, "_update_status", lambda text: statuses.append(text))

    app._confirm_publish()

    assert pipeline.posts == []
    assert app.publish_confirmation_pending is True
    assert "再次点击" in statuses[-1]


@pytest.mark.anyio
async def test_tui_report_logs_do_not_parse_rich_markup() -> None:
    app = ReviewTUI(ReviewPipeline(llm=MockLLMClient()))

    async with app.run_test():
        for widget_id in ("#overview", "#risks", "#suggestions", "#files", "#raw"):
            log = app.query_one(widget_id)
            assert log.highlight is False
            assert log.markup is False


def test_tui_cards_are_plain_text_for_terminal_rendering() -> None:
    app = ReviewTUI(ReviewPipeline(llm=MockLLMClient()))
    finding = ReviewFinding(
        severity="low",
        title="[not-rich] repeated title",
        explanation="Keep [W1] literal in VSCode terminal.",
        files=["src/example.py"],
    )
    suggestion = ReviewSuggestion(
        severity="low",
        title="[not-rich] repeated suggestion",
        body="Keep [W2] literal in VSCode terminal.",
        files=["src/example.py"],
    )

    assert "[b]" not in app._risk_card(finding)
    assert "[/b]" not in app._risk_card(finding)
    assert "[b]" not in app._suggestion_card(suggestion)
    assert "[/b]" not in app._suggestion_card(suggestion)
