from xengineer_pr_review.llm import MockLLMClient
from xengineer_pr_review.models import PullRequestData, PullRequestRef
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
