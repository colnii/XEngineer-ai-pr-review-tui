from xengineer_pr_review.llm import LLMResult, MockLLMClient
from xengineer_pr_review.models import (
    PostedComment,
    PullRequestData,
    PullRequestRef,
    ReviewFinding,
    ReviewSuggestion,
)
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
            head_sha="sha123",
        )

    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str:
        assert git_ref == "sha123"
        return "token = 'x'\nnew = True\n"

    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]:
        assert git_ref == "sha123"
        return ["src/auth.py"]


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


class ToolAwareLLMClient:
    supports_review_tools = True

    def __init__(self) -> None:
        self.tool_output = ""

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is not None
        self.tool_output = toolbox.read_file("src/auth.py", max_lines=1)
        return LLMResult(summary="AI summary with tools")


def test_pipeline_passes_review_toolbox_to_tool_aware_llm() -> None:
    llm = ToolAwareLLMClient()
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=llm)

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.summary == "AI summary with tools"
    assert "File: src/auth.py" in llm.tool_output
    assert "1: token = 'x'" in llm.tool_output


class PostingGitHubClient(FakeGitHubClient):
    def __init__(self) -> None:
        self.posts: list[tuple[PullRequestRef, str]] = []

    def post_pr_comment(self, ref: PullRequestRef, body: str) -> PostedComment:
        self.posts.append((ref, body))
        return PostedComment(html_url="https://github.com/owner/repo/pull/1#issuecomment-9")


def test_pipeline_posts_review_comment_from_pr_url() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())

    result = pipeline.post_review_comment("https://github.com/owner/repo/pull/1", "# Report")

    assert result.html_url.endswith("#issuecomment-9")
    assert github.posts == [(PullRequestRef("owner", "repo", 1), "# Report")]
