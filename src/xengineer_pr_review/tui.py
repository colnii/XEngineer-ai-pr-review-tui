from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from xengineer_pr_review.export import render_markdown
from xengineer_pr_review.pipeline import ReviewPipeline


class ReviewTUI(App):
    CSS = """
    Screen { padding: 1 2; }
    #status { margin: 1 0; }
    #report { height: 1fr; border: solid $accent; padding: 1; }
    """

    def __init__(self, pipeline: ReviewPipeline) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.last_markdown: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Input(placeholder="Paste public GitHub PR URL", id="pr-url")
            yield Button("Analyze PR", id="analyze", variant="primary")
            yield Button("Export Markdown", id="export")
            yield Static("Ready", id="status")
            yield RichLog(id="report", wrap=True, highlight=True, markup=True)
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "analyze":
            await self._analyze()
        elif event.button.id == "export":
            self._export()

    async def _analyze(self) -> None:
        url = self.query_one("#pr-url", Input).value
        status = self.query_one("#status", Static)
        report_log = self.query_one("#report", RichLog)
        report_log.clear()
        status.update("Analyzing...")
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
        self.last_markdown = markdown
        status.update("Analysis complete")
        report_log.write(markdown)

    def _export(self) -> None:
        status = self.query_one("#status", Static)
        if not self.last_markdown:
            status.update("Analyze a PR before exporting")
            return
        output_path = Path("review-report.md")
        output_path.write_text(self.last_markdown)
        status.update(f"Exported {output_path}")
