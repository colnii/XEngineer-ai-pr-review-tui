from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, TabPane, TabbedContent

from xengineer_pr_review.export import render_markdown
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

    def __init__(self, pipeline: ReviewPipeline) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.last_markdown: str | None = None
        self.last_report: ReviewReport | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="root"):
            with Horizontal(id="toolbar"):
                yield Input(placeholder="Paste public GitHub PR URL", id="pr-url")
                yield Button("Analyze", id="analyze", variant="primary")
                yield Button("Export", id="export")
            with Horizontal(id="main"):
                with Vertical(id="workspace"):
                    yield Static(self._phase_text("Ready"), id="status")
                    with TabbedContent(initial="overview-tab"):
                        with TabPane("Overview", id="overview-tab"):
                            yield RichLog(id="overview", wrap=True, highlight=True, markup=True)
                        with TabPane("Risks", id="risks-tab"):
                            yield RichLog(id="risks", wrap=True, highlight=True, markup=True)
                        with TabPane("Suggestions", id="suggestions-tab"):
                            yield RichLog(id="suggestions", wrap=True, highlight=True, markup=True)
                        with TabPane("Files", id="files-tab"):
                            yield RichLog(id="files", wrap=True, highlight=True, markup=True)
                        with TabPane("Raw / Debug", id="raw-tab"):
                            yield RichLog(id="raw", wrap=True, highlight=True, markup=True)
                yield Static(self._meta_text(None), id="meta")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "analyze":
            await self._analyze()
        elif event.button.id == "export":
            self._export()

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
            status.update(f"Error: {exc}")
            return

        markdown = render_markdown(report)
        self.last_report = report
        self.last_markdown = markdown
        status.update(self._phase_text("Complete"))
        self.query_one("#meta", Static).update(self._meta_text(report))
        self._render_report(report)

    def _export(self) -> None:
        status = self.query_one("#status", Static)
        if not self.last_markdown:
            status.update("Analyze a PR before exporting")
            return
        output_path = Path("review-report.md")
        output_path.write_text(self.last_markdown)
        status.update(f"Exported {output_path}")

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
        overview.write(f"{report.repo} #{report.pr_number} by {report.author or 'unknown'}")
        overview.write("")
        overview.write(f"[b]Summary[/b]\n{report.summary}")
        overview.write("")
        overview.write(
            f"Changed files: {len(report.changed_files)} | "
            f"Additions/deletions: +{report.additions}/-{report.deletions}"
        )
        overview.write(
            f"Risks: {len(report.findings)} | Suggestions: {len(report.suggestions)} | "
            f"LLM: {report.llm_status}"
        )

    def _render_risks(self, report: ReviewReport) -> None:
        risks = self.query_one("#risks", RichLog)
        if not report.findings:
            risks.write("No risks were identified.")
            return
        for finding in report.findings:
            risks.write(self._risk_card(finding))
            risks.write("")

    def _render_suggestions(self, report: ReviewReport) -> None:
        suggestions = self.query_one("#suggestions", RichLog)
        if not report.suggestions:
            suggestions.write("No AI suggestions were generated.")
            return
        for suggestion in report.suggestions:
            suggestions.write(self._suggestion_card(suggestion))
            suggestions.write("")

    def _render_files(self, report: ReviewReport) -> None:
        files = self.query_one("#files", RichLog)
        if not report.changed_files:
            files.write("No changed files detected.")
            return
        for path in report.changed_files:
            files.write(f"- {path}")
        if report.omitted_files:
            files.write("")
            files.write("[b]Omitted from LLM context[/b]")
            for path in report.omitted_files:
                files.write(f"- {path}")

    def _render_raw(self, report: ReviewReport) -> None:
        raw = self.query_one("#raw", RichLog)
        raw.write(f"LLM status: {report.llm_status}")
        if report.ai_notes:
            raw.write("")
            raw.write(f"[b]AI Notes[/b]\n{report.ai_notes}")
        if report.raw_ai_output:
            raw.write("")
            raw.write(f"[b]Raw AI Output[/b]\n{report.raw_ai_output}")
        if report.warnings:
            raw.write("")
            raw.write("[b]Warnings[/b]")
            for warning in report.warnings:
                raw.write(f"- {warning}")
        if not report.ai_notes and not report.raw_ai_output and not report.warnings:
            raw.write("No warnings or raw fallback output.")

    def _phase_text(self, state: str) -> str:
        phases = ["Fetch PR", "Parse Diff", "Rule Scan", "LLM Review", "Render Report"]
        if state == "Ready":
            return "Status: Ready | " + " -> ".join(phases)
        if state == "Running":
            return "Status: Running | " + " -> ".join(phases)
        return "Status: Complete | " + " -> ".join(f"{phase}: done" for phase in phases)

    def _meta_text(self, report: ReviewReport | None) -> str:
        if report is None:
            return "\n".join(
                [
                    "PR Review Assistant",
                    "",
                    "Changed files: -",
                    "Risk count: -",
                    "Suggestion count: -",
                    "LLM status: idle",
                ]
            )
        return "\n".join(
            [
                "PR Review Assistant",
                "",
                f"Changed files: {len(report.changed_files)}",
                f"Risk count: {len(report.findings)}",
                f"Suggestion count: {len(report.suggestions)}",
                f"LLM status: {report.llm_status}",
            ]
        )

    def _risk_card(self, finding: ReviewFinding) -> str:
        files = ", ".join(finding.files) if finding.files else "n/a"
        return "\n".join(
            [
                f"[b]{finding.title}[/b]",
                f"Severity: {finding.severity} | Source: {finding.source}",
                f"Explanation: {finding.explanation}",
                f"Related files: {files}",
            ]
        )

    def _suggestion_card(self, suggestion: ReviewSuggestion) -> str:
        files = ", ".join(suggestion.files) if suggestion.files else "n/a"
        return "\n".join(
            [
                f"[b]{suggestion.title}[/b]",
                f"Type: {suggestion.suggestion_type} | Confidence: {suggestion.confidence}",
                suggestion.body,
                f"Related file: {files}",
            ]
        )
