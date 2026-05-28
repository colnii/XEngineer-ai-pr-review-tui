from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, TabPane, TabbedContent

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
from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion
from xengineer_pr_review.pipeline import ReviewPipeline


class ReviewTUI(App):
    CSS = """
    Screen { padding: 1 2; }
    #toolbar { height: auto; margin-bottom: 1; }
    #pr-url { width: 1fr; margin-right: 1; }
    #analyze { margin-right: 1; }
    #main { height: 1fr; }
    #workspace { width: 1fr; }
    #status { height: auto; margin-bottom: 1; border: solid $primary; padding: 1; }
    #meta { width: 34; border: solid $accent; padding: 1; margin-left: 1; }
    RichLog { height: 1fr; border: solid $accent; padding: 1; }
    """

    def __init__(self, pipeline: ReviewPipeline, language: str = "zh") -> None:
        super().__init__()
        self.pipeline = pipeline
        self.language = normalize_language(language)
        self.last_markdown: str | None = None
        self.last_report: ReviewReport | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="root"):
            with Horizontal(id="toolbar"):
                yield Input(placeholder=label("input.pr_url", self.language), id="pr-url")
                yield Button(label("button.analyze", self.language), id="analyze", variant="primary")
                yield Button(label("button.export", self.language), id="export")
                yield Button(self._language_button_text(), id="language")
            with Horizontal(id="main"):
                with Vertical(id="workspace"):
                    yield Static(self._phase_text("Ready"), id="status")
                    with TabbedContent(initial="overview-tab"):
                        with TabPane(label("tab.overview", self.language), id="overview-tab"):
                            yield RichLog(id="overview", wrap=True, highlight=True, markup=True)
                        with TabPane(label("tab.risks", self.language), id="risks-tab"):
                            yield RichLog(id="risks", wrap=True, highlight=True, markup=True)
                        with TabPane(label("tab.suggestions", self.language), id="suggestions-tab"):
                            yield RichLog(id="suggestions", wrap=True, highlight=True, markup=True)
                        with TabPane(label("tab.files", self.language), id="files-tab"):
                            yield RichLog(id="files", wrap=True, highlight=True, markup=True)
                        with TabPane(label("tab.raw", self.language), id="raw-tab"):
                            yield RichLog(id="raw", wrap=True, highlight=True, markup=True)
                yield Static(self._meta_text(None), id="meta")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "analyze":
            await self._analyze()
        elif event.button.id == "export":
            self._export()
        elif event.button.id == "language":
            self._set_language("en" if self.language == "zh" else "zh")

    async def _analyze(self) -> None:
        url = self.query_one("#pr-url", Input).value
        status = self.query_one("#status", Static)
        self._clear_report_logs()
        status.update(self._phase_text("Running"))
        self.query_one("#meta", Static).update(self._meta_text(None))
        try:
            report = await self.run_worker(
                lambda: self.pipeline.run(url),
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

    def _language_button_text(self) -> str:
        return "English" if self.language == "zh" else "中文"

    def _set_language(self, language: str) -> None:
        self.language = normalize_language(language)
        self._update_static_language()
        if self.last_report is not None:
            self.last_markdown = render_markdown(self.last_report, language=self.language)
            self._clear_report_logs()
            self._render_report(self.last_report)

    def _update_static_language(self) -> None:
        self.query_one("#pr-url", Input).placeholder = label("input.pr_url", self.language)
        self.query_one("#analyze", Button).label = label("button.analyze", self.language)
        self.query_one("#export", Button).label = label("button.export", self.language)
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
        overview.write(f"[b]{report.pr_title}[/b]")
        unknown = label("common.unknown", self.language)
        overview.write(
            f"{report.repo} #{report.pr_number} "
            f"{label('overview.by', self.language)} {report.author or unknown}"
        )
        overview.write("")
        overview.write(f"[b]{label('report.summary', self.language)}[/b]\n{report.summary}")
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
            files.write(f"[b]{label('report.omitted_files', self.language)}[/b]")
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
            raw.write(f"[b]{label('report.ai_notes', self.language)}[/b]\n{report.ai_notes}")
        if report.raw_ai_output:
            raw.write("")
            raw.write(
                f"[b]{label('report.raw_ai_output', self.language)}[/b]\n"
                f"{report.raw_ai_output}"
            )
        if report.warnings:
            raw.write("")
            raw.write(f"[b]{label('report.warnings', self.language)}[/b]")
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

    def _risk_card(self, finding: ReviewFinding) -> str:
        files = ", ".join(finding.files) if finding.files else label("common.none", self.language)
        return "\n".join(
            [
                f"[b]{translate_builtin_text(finding.title, self.language)}[/b]",
                f"{label('report.severity', self.language)}: "
                f"{display_severity(finding.severity, self.language)} | "
                f"{label('report.source', self.language)}: "
                f"{display_source(finding.source, self.language)}",
                f"{label('report.explanation', self.language)}: "
                f"{translate_builtin_text(finding.explanation, self.language)}",
                f"{label('report.related_files', self.language)}: {files}",
            ]
        )

    def _suggestion_card(self, suggestion: ReviewSuggestion) -> str:
        files = ", ".join(suggestion.files) if suggestion.files else label("common.none", self.language)
        return "\n".join(
            [
                f"[b]{translate_builtin_text(suggestion.title, self.language)}[/b]",
                f"{label('report.type', self.language)}: "
                f"{display_suggestion_type(suggestion.suggestion_type, self.language)} | "
                f"{label('report.confidence', self.language)}: "
                f"{display_confidence(suggestion.confidence, self.language)}",
                translate_builtin_text(suggestion.body, self.language),
                f"{label('report.related_file', self.language)}: {files}",
            ]
        )
