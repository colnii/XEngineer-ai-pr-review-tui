from xengineer_pr_review.llm import LLMResult, MockLLMClient
from xengineer_pr_review.models import PullRequestData, PullRequestRef, ReviewFinding, ReviewSuggestion
from xengineer_pr_review.pipeline import ReviewPipeline


class FakeGitHubClient:
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        diff = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1,2 @@
-old = True
+token = "x"
+new = True
"""
        return PullRequestData(
            ref=ref,
            title="Improve auth",
            author="alice",
            base_branch="main",
            head_branch="feature",
            files=(),
            diff_text=diff,
        )


def test_pipeline_returns_report_with_rules_and_llm_summary() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=MockLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.pr_title == "Improve auth"
    assert report.summary
    assert "src/auth.py" in report.changed_files
    assert report.findings
    assert report.suggestions


class MarkdownLLMClient:
    def analyze(self, prompt: str) -> LLMResult:
        return LLMResult(
            summary="AI summary",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="AI risk",
                    explanation="AI risk explanation.",
                    files=["src/auth.py"],
                )
            ],
            suggestions=[
                ReviewSuggestion(
                    severity="medium",
                    suggestion_type="test",
                    title="AI suggestion",
                    body="Add regression coverage.",
                    files=["src/auth.py"],
                    confidence="medium",
                )
            ],
            warnings=[],
        )


def test_pipeline_merges_ai_risks_with_rule_findings_and_sets_metadata() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=MarkdownLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.repo == "owner/repo"
    assert report.pr_number == 1
    assert report.author == "alice"
    assert report.additions == 2
    assert report.deletions == 1
    assert any(finding.source == "rule" for finding in report.findings)
    assert any(finding.source == "ai" for finding in report.findings)
    assert report.suggestions[0].title == "AI suggestion"
    assert report.llm_status == "ok"
