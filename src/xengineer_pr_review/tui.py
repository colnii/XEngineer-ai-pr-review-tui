from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from textual.app import App, ComposeResult, ScreenStackError
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, TabPane, TabbedContent

from xengineer_pr_review.credentials import (
    CredentialStatus,
    read_credential_status,
    save_runtime_credentials,
)
from xengineer_pr_review.export import render_markdown
from xengineer_pr_review.locale import (
    display_confidence,
    display_llm_status,
    display_severity,
    display_source,
    display_suggestion_type,
    label,
    normalize_language,
    translate_builtin_text,
)
from xengineer_pr_review.models import EvidenceReference, ReviewFinding, ReviewReport, ReviewSuggestion
from xengineer_pr_review.pipeline import CommentMode, ReviewPipeline


class ReviewTUI(App):
    CSS = """
    Screen { padding: 1 2; }
    #toolbar { height: auto; margin-bottom: 1; }
    #setup { height: auto; border: solid $warning; padding: 1; margin-bottom: 1; }
    #setup-text { height: auto; margin-bottom: 1; }
    #setup-model-key { width: 1fr; margin-right: 1; }
    #setup-tavily-key { width: 1fr; margin-right: 1; }
    #setup-github-token { width: 1fr; margin-right: 1; }
    #setup-save-deepseek { margin-right: 1; }
    #setup-save-openai { margin-right: 1; }
    #pr-url { width: 1fr; margin-right: 1; }
    #analyze { margin-right: 1; }
    #comment-mode { margin-left: 1; }
    #inline-comments { margin-left: 1; }
    #main { height: 1fr; }
    #workspace { width: 1fr; }
    #status { height: auto; margin-bottom: 1; border: solid $primary; padding: 1; }
    #meta { width: 34; border: solid $accent; padding: 1; margin-left: 1; }
    RichLog { height: 1fr; border: solid $accent; padding: 1; }
    """

    def __init__(
        self,
        pipeline: ReviewPipeline | None,
        pipeline_factory: Callable[[], ReviewPipeline] | None = None,
        credential_status: CredentialStatus | None = None,
        credential_writer: Callable[[Mapping[str, str]], Path] = save_runtime_credentials,
        language: str = "zh",
        initial_pr_url: str = "",
        auto_analyze: bool = False,
    ) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.pipeline_factory = pipeline_factory
        self.credential_status = credential_status or read_credential_status()
        self.credential_writer = credential_writer
        self.credentials_required = pipeline is None and not self.credential_status.has_model_key
        self.language = normalize_language(language)
        self.initial_pr_url = initial_pr_url
        self.auto_analyze = auto_analyze
        self.last_markdown: str | None = None
        self.last_report: ReviewReport | None = None
        self.publish_confirmation_pending = False
        self.comment_mode: CommentMode = "conversation"
        self.inline_comments_enabled = False
        self.setup_status_text: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="root"):
            if self.credentials_required:
                with Vertical(id="setup"):
                    yield Static(self._setup_text(), id="setup-text")
                    with Horizontal(id="setup-model-row"):
                        yield Input(
                            placeholder=label("input.model_key", self.language),
                            password=True,
                            id="setup-model-key",
                        )
                        yield Button(
                            label("button.save_deepseek", self.language),
                            id="setup-save-deepseek",
                            variant="primary",
                        )
                        yield Button(
                            label("button.save_openai", self.language),
                            id="setup-save-openai",
                        )
                    with Horizontal(id="setup-optional-row"):
                        yield Input(
                            placeholder=label("input.tavily_key", self.language),
                            password=True,
                            id="setup-tavily-key",
                        )
                        yield Input(
                            placeholder=label("input.github_token", self.language),
                            password=True,
                            id="setup-github-token",
                        )
            with Horizontal(id="toolbar"):
                yield Input(
                    value=self.initial_pr_url,
                    placeholder=label("input.pr_url", self.language),
                    id="pr-url",
                )
                yield Button(label("button.analyze", self.language), id="analyze", variant="primary")
                yield Button(label("button.export", self.language), id="export")
                yield Button(self._comment_mode_button_text(), id="comment-mode")
                yield Button(self._inline_comments_button_text(), id="inline-comments")
                yield Button(label("button.publish", self.language), id="publish")
                yield Button(self._language_button_text(), id="language")
            with Horizontal(id="main"):
                with Vertical(id="workspace"):
                    yield Static(self._phase_text("Ready"), id="status")
                    with TabbedContent(initial="overview-tab"):
                        with TabPane(label("tab.overview", self.language), id="overview-tab"):
                            # Keep report panes plain text to avoid VS Code terminal repaint lag.
                            yield RichLog(id="overview", wrap=True)
                        with TabPane(label("tab.risks", self.language), id="risks-tab"):
                            yield RichLog(id="risks", wrap=True)
                        with TabPane(label("tab.suggestions", self.language), id="suggestions-tab"):
                            yield RichLog(id="suggestions", wrap=True)
                        with TabPane(label("tab.files", self.language), id="files-tab"):
                            yield RichLog(id="files", wrap=True)
                        with TabPane(label("tab.raw", self.language), id="raw-tab"):
                            yield RichLog(id="raw", wrap=True)
                yield Static(self._meta_text(None), id="meta")
        yield Footer()

    async def on_mount(self) -> None:
        if self.auto_analyze and self.initial_pr_url:
            await self._analyze()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "analyze":
            await self._analyze()
        elif event.button.id == "setup-save-deepseek":
            self._save_credentials("deepseek")
        elif event.button.id == "setup-save-openai":
            self._save_credentials("openai")
        elif event.button.id == "export":
            self._export()
        elif event.button.id == "publish":
            if self.publish_confirmation_pending:
                await self._confirm_publish()
            else:
                self._request_publish_confirmation()
        elif event.button.id == "comment-mode":
            self._toggle_comment_mode()
        elif event.button.id == "inline-comments":
            self._toggle_inline_comments()
        elif event.button.id == "language":
            self._set_language("en" if self.language == "zh" else "zh")

    async def _analyze(self) -> None:
        url = self.query_one("#pr-url", Input).value
        status = self.query_one("#status", Static)
        try:
            pipeline_ready = self._ensure_pipeline_ready()
        except Exception as exc:
            status.update(f"{label('status.error', self.language)}: {exc}")
            return
        if not pipeline_ready:
            status.update(label("status.model_key_required", self.language))
            return
        pipeline = self.pipeline
        if pipeline is None:
            status.update(label("status.model_key_required", self.language))
            return
        self._reset_publish_confirmation()
        self._clear_report_logs()
        status.update(self._phase_text("Running"))
        self.query_one("#meta", Static).update(self._meta_text(None))
        try:
            report = await self.run_worker(
                lambda: pipeline.run(url),
                thread=True,
                exclusive=True,
            ).wait()
        except Exception as exc:
            status.update(f"{label('status.error', self.language)}: {exc}")
            return

        self.last_report = report
        self.last_markdown = render_markdown(report, language=self.language)
        status.update(self._phase_text("Complete"))
        self.query_one("#meta", Static).update(self._meta_text(report))
        self._render_report(report)

    def _export(self) -> None:
        status = self.query_one("#status", Static)
        if not self.last_markdown:
            status.update(label("status.export_first", self.language))
            return
        output_path = Path("review-report.md")
        output_path.write_text(self.last_markdown)
        status.update(f"{label('status.exported', self.language)} {output_path}")

    def _save_credentials(self, provider: str) -> None:
        provider_key = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
        model_key = self._input_value("#setup-model-key")
        if not model_key:
            self._update_status(label("status.model_key_required", self.language))
            return

        values = {provider_key: model_key}
        tavily_key = self._input_value("#setup-tavily-key")
        github_token = self._input_value("#setup-github-token")
        if tavily_key:
            values["TAVILY_API_KEY"] = tavily_key
        if github_token:
            values["GITHUB_TOKEN"] = github_token

        try:
            env_path = self.credential_writer(values)
            os.environ.update(values)
            self.credential_status = read_credential_status()
        except Exception as exc:
            self._update_status(f"{label('status.credentials_save_failed', self.language)}: {exc}")
            return

        self.setup_status_text = (
            f"{label('status.credentials_saved', self.language)}: {env_path}\n"
            f"{provider_key} configured."
        )
        try:
            pipeline_ready = self._ensure_pipeline_ready()
        except Exception as exc:
            self.credentials_required = self.pipeline is None
            self._update_setup_text(self.setup_status_text)
            self._update_status(
                f"{label('status.credentials_pipeline_failed', self.language)}: {exc}"
            )
            return
        if not pipeline_ready:
            self.credentials_required = True
            self._update_setup_text(self.setup_status_text)
            self._update_status(label("status.credentials_pipeline_failed", self.language))
            return

        self.credentials_required = False
        self._update_setup_text(self.setup_status_text)
        self._update_status(label("status.ready", self.language))

    def _input_value(self, selector: str) -> str:
        try:
            return self.query_one(selector, Input).value.strip()
        except (NoMatches, ScreenStackError):
            return ""

    def _ensure_pipeline_ready(self) -> bool:
        if self.pipeline is not None:
            return True
        if self.pipeline_factory is None:
            return False
        self.pipeline = self.pipeline_factory()
        return True

    def _update_setup_text(self, text: str) -> None:
        try:
            self.query_one("#setup-text", Static).update(text)
        except (NoMatches, ScreenStackError):
            return

    def _update_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _set_button_label(self, widget_id: str, text: str) -> None:
        try:
            self.query_one(widget_id, Button).label = text
        except (NoMatches, ScreenStackError):
            return

    def _set_publish_button_label(self, text: str) -> None:
        self._set_button_label("#publish", text)

    def _update_publish_option_labels(self) -> None:
        self._set_button_label("#comment-mode", self._comment_mode_button_text())
        self._set_button_label("#inline-comments", self._inline_comments_button_text())

    def _reset_publish_confirmation(self) -> None:
        self.publish_confirmation_pending = False
        self._set_publish_button_label(label("button.publish", self.language))

    def _request_publish_confirmation(self) -> None:
        if not self.last_report or not self.last_markdown:
            self._update_status(label("status.publish_first", self.language))
            return
        self.publish_confirmation_pending = True
        self._set_publish_button_label(label("button.confirm_publish", self.language))
        self._update_status(self._publish_confirmation_text())

    async def _confirm_publish(self) -> None:
        if not self.publish_confirmation_pending:
            self._request_publish_confirmation()
            return
        if not self.last_report or not self.last_markdown:
            self._reset_publish_confirmation()
            self._update_status(label("status.publish_first", self.language))
            return
        self._update_status(label("status.publishing", self.language))
        try:
            posted = await self._post_current_review_comment()
        except Exception as exc:
            self._reset_publish_confirmation()
            self._update_status(f"{label('status.publish_failed', self.language)}: {exc}")
            return
        self._reset_publish_confirmation()
        self._update_status(f"{label('status.published', self.language)}: {posted.html_url}")

    async def _post_current_review_comment(self):
        assert self.last_report is not None
        assert self.last_markdown is not None

        def post():
            return self.pipeline.post_review_comment(
                self.last_report.pr_url,
                self.last_markdown,
                comment_mode=self.comment_mode,
                review_action="comment",
                include_inline_comments=self.inline_comments_enabled,
                report=self.last_report,
            )

        if self.is_running:
            return await self.run_worker(post, thread=True, exclusive=True).wait()
        return post()

    def _language_button_text(self) -> str:
        return "English" if self.language == "zh" else "中文"

    def _comment_mode_button_text(self) -> str:
        key = (
            "button.comment_mode_review"
            if self.comment_mode == "review"
            else "button.comment_mode_conversation"
        )
        return label(key, self.language)

    def _inline_comments_button_text(self) -> str:
        key = (
            "button.inline_comments_on"
            if self.inline_comments_enabled
            else "button.inline_comments_off"
        )
        return label(key, self.language)

    def _toggle_comment_mode(self) -> None:
        if self.comment_mode == "conversation":
            self.comment_mode = "review"
        else:
            self.comment_mode = "conversation"
            self.inline_comments_enabled = False
        self._reset_publish_confirmation()
        self._update_publish_option_labels()

    def _toggle_inline_comments(self) -> None:
        if self.comment_mode != "review":
            self.comment_mode = "review"
            self.inline_comments_enabled = True
        else:
            self.inline_comments_enabled = not self.inline_comments_enabled
        self._reset_publish_confirmation()
        self._update_publish_option_labels()

    def _publish_confirmation_text(self) -> str:
        if self.comment_mode == "review" and self.inline_comments_enabled:
            return label("status.publish_confirm_review_inline", self.language)
        if self.comment_mode == "review":
            return label("status.publish_confirm_review", self.language)
        return label("status.publish_confirm", self.language)

    def _set_language(self, language: str) -> None:
        self.language = normalize_language(language)
        self._reset_publish_confirmation()
        self._update_static_language()
        if self.last_report is not None:
            self.last_markdown = render_markdown(self.last_report, language=self.language)
            self._clear_report_logs()
            self._render_report(self.last_report)

    def _update_static_language(self) -> None:
        if self.credentials_required:
            self._update_setup_text(self._setup_text())
        elif self.setup_status_text:
            self._update_setup_text(self.setup_status_text)
        self.query_one("#pr-url", Input).placeholder = label("input.pr_url", self.language)
        try:
            self.query_one("#setup-model-key", Input).placeholder = label(
                "input.model_key",
                self.language,
            )
            self.query_one("#setup-tavily-key", Input).placeholder = label(
                "input.tavily_key",
                self.language,
            )
            self.query_one("#setup-github-token", Input).placeholder = label(
                "input.github_token",
                self.language,
            )
            self.query_one("#setup-save-deepseek", Button).label = label(
                "button.save_deepseek",
                self.language,
            )
            self.query_one("#setup-save-openai", Button).label = label(
                "button.save_openai",
                self.language,
            )
        except (NoMatches, ScreenStackError):
            pass
        self.query_one("#analyze", Button).label = label("button.analyze", self.language)
        self.query_one("#export", Button).label = label("button.export", self.language)
        self.query_one("#publish", Button).label = label("button.publish", self.language)
        self._update_publish_option_labels()
        self.query_one("#language", Button).label = self._language_button_text()
        self.query_one("#status", Static).update(
            self._phase_text("Complete" if self.last_report else "Ready")
        )
        self.query_one("#meta", Static).update(self._meta_text(self.last_report))

    def _clear_report_logs(self) -> None:
        for widget_id in ("#overview", "#risks", "#suggestions", "#files", "#raw"):
            self.query_one(widget_id, RichLog).clear()

    def _render_report(self, report: ReviewReport) -> None:
        self._render_overview(report)
        self._render_risks(report)
        self._render_suggestions(report)
        self._render_files(report)
        self._render_raw(report)

    def _render_overview(self, report: ReviewReport) -> None:
        overview = self.query_one("#overview", RichLog)
        overview.write(report.pr_title)
        unknown = label("common.unknown", self.language)
        overview.write(
            f"{report.repo} #{report.pr_number} "
            f"{label('overview.by', self.language)} {report.author or unknown}"
        )
        overview.write("")
        overview.write(f"{label('report.summary', self.language)}\n{report.summary}")
        overview.write("")
        overview.write(
            f"{label('meta.changed_files', self.language)}: {len(report.changed_files)} | "
            f"{label('overview.additions_deletions', self.language)}: "
            f"+{report.additions}/-{report.deletions}"
        )
        overview.write(
            f"{label('overview.risks', self.language)}: {len(report.findings)} | "
            f"{label('overview.suggestions', self.language)}: {len(report.suggestions)} | "
            f"LLM: {display_llm_status(report.llm_status, self.language)}"
        )

    def _render_risks(self, report: ReviewReport) -> None:
        risks = self.query_one("#risks", RichLog)
        if not report.findings:
            risks.write(label("tui.no_risks", self.language))
            return
        for finding in report.findings:
            risks.write(self._risk_card(finding))
            risks.write("")

    def _render_suggestions(self, report: ReviewReport) -> None:
        suggestions = self.query_one("#suggestions", RichLog)
        if not report.suggestions:
            suggestions.write(label("report.no_ai_suggestions", self.language))
            return
        for suggestion in report.suggestions:
            suggestions.write(self._suggestion_card(suggestion))
            suggestions.write("")

    def _render_files(self, report: ReviewReport) -> None:
        files = self.query_one("#files", RichLog)
        if not report.changed_files:
            files.write(label("tui.no_files", self.language))
            return
        for path in report.changed_files:
            files.write(f"- {path}")
        if report.omitted_files:
            files.write("")
            files.write(label("report.omitted_files", self.language))
            for path in report.omitted_files:
                files.write(f"- {path}")

    def _render_raw(self, report: ReviewReport) -> None:
        raw = self.query_one("#raw", RichLog)
        raw.write(
            f"{label('report.llm_status', self.language)}: "
            f"{display_llm_status(report.llm_status, self.language)}"
        )
        if report.ai_notes:
            raw.write("")
            raw.write(f"{label('report.ai_notes', self.language)}\n{report.ai_notes}")
        if report.raw_ai_output:
            raw.write("")
            raw.write(
                f"{label('report.raw_ai_output', self.language)}\n"
                f"{report.raw_ai_output}"
            )
        if report.warnings:
            raw.write("")
            raw.write(label("report.warnings", self.language))
            for warning in report.warnings:
                raw.write(f"- {warning}")
        if not report.ai_notes and not report.raw_ai_output and not report.warnings:
            raw.write(label("tui.no_raw", self.language))

    def _phase_text(self, state: str) -> str:
        phases = [
            label("phase.fetch", self.language),
            label("phase.parse", self.language),
            label("phase.rules", self.language),
            label("phase.llm", self.language),
            label("phase.render", self.language),
        ]
        if state == "Ready":
            return label("status.ready", self.language) + " | " + " -> ".join(phases)
        if state == "Running":
            return label("status.running", self.language) + " | " + " -> ".join(phases)
        done = label("phase.done", self.language)
        return label("status.complete", self.language) + " | " + " -> ".join(
            f"{phase}: {done}" for phase in phases
        )

    def _meta_text(self, report: ReviewReport | None) -> str:
        if report is None:
            return "\n".join(
                [
                    label("app.title", self.language),
                    "",
                    f"{label('meta.changed_files', self.language)}: -",
                    f"{label('meta.risk_count', self.language)}: -",
                    f"{label('meta.suggestion_count', self.language)}: -",
                    label("meta.llm_status_idle", self.language),
                ]
            )
        return "\n".join(
            [
                label("app.title", self.language),
                "",
                f"{label('meta.changed_files', self.language)}: {len(report.changed_files)}",
                f"{label('meta.risk_count', self.language)}: {len(report.findings)}",
                f"{label('meta.suggestion_count', self.language)}: {len(report.suggestions)}",
                f"{label('report.llm_status', self.language)}: "
                f"{display_llm_status(report.llm_status, self.language)}",
            ]
        )

    def _setup_text(self) -> str:
        return "\n".join(
            [
                label("setup.title", self.language),
                label("setup.required", self.language),
                label("setup.optional", self.language),
                label("setup.github_help", self.language),
            ]
        )

    def _risk_card(self, finding: ReviewFinding) -> str:
        files = ", ".join(finding.files) if finding.files else label("common.none", self.language)
        lines = [
            translate_builtin_text(finding.title, self.language),
            f"{label('report.severity', self.language)}: "
            f"{display_severity(finding.severity, self.language)} | "
            f"{label('report.source', self.language)}: "
            f"{display_source(finding.source, self.language)}",
            f"{label('report.explanation', self.language)}: "
            f"{translate_builtin_text(finding.explanation, self.language)}",
            f"{label('report.related_files', self.language)}: {files}",
        ]
        lines.extend(self._evidence_lines(finding.evidence))
        return "\n".join(lines)

    def _suggestion_card(self, suggestion: ReviewSuggestion) -> str:
        files = ", ".join(suggestion.files) if suggestion.files else label("common.none", self.language)
        lines = [
            translate_builtin_text(suggestion.title, self.language),
            f"{label('report.type', self.language)}: "
            f"{display_suggestion_type(suggestion.suggestion_type, self.language)} | "
            f"{label('report.confidence', self.language)}: "
            f"{display_confidence(suggestion.confidence, self.language)}",
            translate_builtin_text(suggestion.body, self.language),
            f"{label('report.related_file', self.language)}: {files}",
        ]
        lines.extend(self._evidence_lines(suggestion.evidence))
        return "\n".join(lines)

    def _evidence_lines(self, evidence: list[EvidenceReference]) -> list[str]:
        if not evidence:
            return []
        return [
            f"{label('report.evidence', self.language)}:",
            *[f"- {_format_evidence_text(reference)}" for reference in evidence],
        ]


def _format_evidence_text(reference: EvidenceReference) -> str:
    if reference.kind in {"web", "pr_activity"}:
        label_text = f"{reference.label}: " if reference.label else ""
        fallback_title = "PR activity" if reference.kind == "pr_activity" else "web source"
        title = reference.title or reference.url or fallback_title
        url_text = f" {reference.url}" if reference.url and reference.url != title else ""
        snippet = f" - {reference.snippet}" if reference.snippet else ""
        return f"{label_text}{title}{url_text}{snippet}"
    location = reference.path or "unknown"
    if reference.line_start is not None:
        if reference.line_end is not None and reference.line_end != reference.line_start:
            location = f"{location}:{reference.line_start}-{reference.line_end}"
        else:
            location = f"{location}:{reference.line_start}"
    snippet = f" - {reference.snippet}" if reference.snippet else ""
    return f"{location}{snippet}"
