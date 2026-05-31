import pytest

from xengineer_pr_review.llm import LLMResult, MockLLMClient
from xengineer_pr_review.models import (
    EvidenceReference,
    InlineReviewComment,
    PostedComment,
    PullRequestActivity,
    PullRequestData,
    PullRequestRef,
    ReviewFinding,
    ReviewReport,
    ReviewSuggestion,
)
from xengineer_pr_review.pipeline import ReviewPipeline, build_inline_review_comments


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


class FetchOnlyGitHubClient:
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        return FakeGitHubClient().fetch_pr(ref)

    def post_pr_comment(self, ref: PullRequestRef, body: str) -> PostedComment:
        return PostedComment(html_url="https://github.com/owner/repo/pull/1#issuecomment-9")


def test_pipeline_returns_report_with_rules_and_llm_summary() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=MockLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.pr_title == "Improve auth"
    assert report.summary
    assert "src/auth.py" in report.changed_files
    assert report.findings
    assert report.suggestions


class MarkdownLLMClient:
    supports_review_tools = False

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is None
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


class ActivityGitHubClient(FakeGitHubClient):
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        pr = super().fetch_pr(ref)
        return PullRequestData(
            ref=pr.ref,
            title=pr.title,
            author=pr.author,
            base_branch=pr.base_branch,
            head_branch=pr.head_branch,
            files=pr.files,
            diff_text=pr.diff_text,
            head_sha=pr.head_sha,
            activities=(
                PullRequestActivity(
                    kind="conversation",
                    author="reviewer",
                    body="Please inspect the prior PR discussion before reviewing.",
                    created_at="2026-05-30T10:00:00Z",
                ),
            ),
        )


class PromptCapturingLLMClient:
    supports_review_tools = False

    def __init__(self) -> None:
        self.prompt = ""

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is None
        self.prompt = prompt
        return LLMResult(summary="AI summary")


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


def test_pipeline_preserves_pr_activity_for_llm_context() -> None:
    llm = PromptCapturingLLMClient()
    pipeline = ReviewPipeline(github=ActivityGitHubClient(), llm=llm)

    pipeline.run("https://github.com/owner/repo/pull/1")

    assert "PR activity history:" in llm.prompt
    assert "Please inspect the prior PR discussion before reviewing." in llm.prompt


def test_pipeline_enriches_ai_items_with_code_evidence_permalink() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=MarkdownLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    ai_risk = next(finding for finding in report.findings if finding.source == "ai")
    assert ai_risk.evidence[0].kind == "code"
    assert ai_risk.evidence[0].path == "src/auth.py"
    assert ai_risk.evidence[0].line_start == 1
    assert ai_risk.evidence[0].line_end == 2
    assert ai_risk.evidence[0].url == (
        "https://github.com/owner/repo/blob/sha123/src/auth.py#L1-L2"
    )
    assert report.suggestions[0].evidence[0].url == (
        "https://github.com/owner/repo/blob/sha123/src/auth.py#L1-L2"
    )


class ToolAwareLLMClient:
    supports_review_tools = True

    def __init__(self) -> None:
        self.tool_output = ""

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is not None
        self.tool_output = toolbox.read_file("src/auth.py", max_lines=1)
        return LLMResult(summary="AI summary with tools")


class ActivityToolAwareLLMClient:
    supports_review_tools = True

    def __init__(self) -> None:
        self.activity_output = ""

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is not None
        self.activity_output = toolbox.read_pr_activity(kind="conversation", max_items=5)
        return LLMResult(summary="AI summary with PR activity tool")


class FileIdToolAwareLLMClient:
    supports_review_tools = True

    def __init__(self) -> None:
        self.prompt = ""
        self.tool_output = ""

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is not None
        self.prompt = prompt
        self.tool_output = toolbox.read_file(file_id="F1", max_lines=1)
        return LLMResult(
            summary="AI summary with indexed tools",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="Indexed evidence",
                    explanation="Evidence used a short file id.",
                    files=[],
                    evidence=[
                        EvidenceReference(
                            kind="code",
                            file_id="F1",
                            line_start=1,
                            line_end=1,
                        )
                    ],
                )
            ],
        )


class PathAliasLLMClient:
    supports_review_tools = False

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is None
        assert "F1: src/auth.py" in prompt
        return LLMResult(
            summary="AI summary with path alias",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="Path alias evidence",
                    explanation="Evidence used F1 as the path field.",
                    files=["F1"],
                    evidence=[
                        EvidenceReference(
                            kind="code",
                            path="F1",
                            line_start=1,
                            line_end=2,
                            snippet="HUNK_HEADER_PATTERN = re.compile(...)",
                        )
                    ],
                )
            ],
        )


class UnknownPathLLMClient:
    supports_review_tools = False

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is None
        return LLMResult(
            summary="AI summary with unknown path",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="Unknown path evidence",
                    explanation="Evidence used a path that is not in the changed file index.",
                    files=["src/autn.py"],
                    evidence=[
                        EvidenceReference(
                            kind="code",
                            path="src/autn.py",
                            line_start=1,
                            line_end=2,
                        )
                    ],
                )
            ],
        )


class OutOfRangeEvidenceLLMClient:
    supports_review_tools = False

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is None
        return LLMResult(
            summary="AI summary with out-of-range evidence",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="Out-of-range evidence",
                    explanation="Evidence line is not in the changed diff hunk.",
                    files=["src/auth.py"],
                    evidence=[
                        EvidenceReference(
                            kind="code",
                            path="src/auth.py",
                            line_start=99,
                            line_end=100,
                        )
                    ],
                )
            ],
        )


class OptionalToolAwareLLMClient:
    supports_review_tools = True

    def __init__(self) -> None:
        self.toolbox = object()

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        self.toolbox = toolbox
        return LLMResult(summary="AI summary without tools")


class WebCitationLLMClient:
    supports_review_tools = True

    def analyze(self, prompt: str, toolbox=None) -> LLMResult:
        assert toolbox is not None
        toolbox.web_search("python security advisory", max_results=1)
        return LLMResult(
            summary="AI summary with web citation",
            risks=[
                ReviewFinding(
                    severity="low",
                    source="ai",
                    title="External advisory",
                    explanation="External docs mention a related advisory.",
                    files=["src/auth.py"],
                    evidence=[{"kind": "web", "label": "W1"}],
                )
            ],
        )


def test_pipeline_passes_review_toolbox_to_tool_aware_llm() -> None:
    llm = ToolAwareLLMClient()
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=llm)

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.summary == "AI summary with tools"
    assert "File: src/auth.py" in llm.tool_output
    assert "1: token = 'x'" in llm.tool_output


def test_pipeline_passes_pr_activity_to_review_toolbox() -> None:
    llm = ActivityToolAwareLLMClient()
    pipeline = ReviewPipeline(github=ActivityGitHubClient(), llm=llm)

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.summary == "AI summary with PR activity tool"
    assert "PR activity history (conversation" in llm.activity_output
    assert "Please inspect the prior PR discussion before reviewing." in llm.activity_output


def test_pipeline_exposes_file_ids_and_hydrates_file_id_evidence() -> None:
    llm = FileIdToolAwareLLMClient()
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=llm)

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert "F1: src/auth.py" in llm.prompt
    assert "File: src/auth.py" in llm.tool_output
    evidence = next(finding for finding in report.findings if finding.title == "Indexed evidence").evidence[0]
    assert evidence.file_id == "F1"
    assert evidence.path == "src/auth.py"
    assert evidence.url == "https://github.com/owner/repo/blob/sha123/src/auth.py#L1"


def test_pipeline_normalizes_file_id_aliases_in_paths_and_files() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=PathAliasLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    finding = next(finding for finding in report.findings if finding.title == "Path alias evidence")
    assert finding.files == ["src/auth.py"]
    assert len(finding.evidence) == 1
    evidence = finding.evidence[0]
    assert evidence.file_id == "F1"
    assert evidence.path == "src/auth.py"
    assert evidence.url == "https://github.com/owner/repo/blob/sha123/src/auth.py#L1-L2"
    assert evidence.snippet == ""


def test_pipeline_does_not_hydrate_unknown_ai_paths() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=UnknownPathLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    finding = next(finding for finding in report.findings if finding.title == "Unknown path evidence")
    assert finding.files == []
    assert finding.evidence == []


def test_pipeline_replaces_out_of_range_ai_evidence_with_changed_hunk_range() -> None:
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=OutOfRangeEvidenceLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    finding = next(finding for finding in report.findings if finding.title == "Out-of-range evidence")
    assert finding.evidence == [
        EvidenceReference(
            kind="code",
            path="src/auth.py",
            line_start=1,
            line_end=2,
            url="https://github.com/owner/repo/blob/sha123/src/auth.py#L1-L2",
        )
    ]


def test_pipeline_hydrates_web_citation_labels_from_tool_results(monkeypatch) -> None:
    monkeypatch.setattr(
        "xengineer_pr_review.pipeline.default_web_searcher",
        lambda: FakeWebSearch(),
    )
    pipeline = ReviewPipeline(github=FakeGitHubClient(), llm=WebCitationLLMClient())

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    web_evidence = next(
        reference
        for reference in report.findings[-1].evidence
        if reference.kind == "web"
    )
    assert web_evidence.label == "W1"
    assert web_evidence.title == "Example result"
    assert web_evidence.url == "https://example.test/result"
    assert web_evidence.snippet == "A short result snippet."


def test_pipeline_logs_when_tool_aware_llm_cannot_receive_tools(caplog) -> None:
    caplog.set_level("INFO")
    llm = OptionalToolAwareLLMClient()
    pipeline = ReviewPipeline(github=FetchOnlyGitHubClient(), llm=llm)

    report = pipeline.run("https://github.com/owner/repo/pull/1")

    assert report.summary == "AI summary without tools"
    assert llm.toolbox is None
    assert "Review tools disabled" in caplog.text


class PostingGitHubClient(FakeGitHubClient):
    def __init__(self) -> None:
        self.posts: list[tuple[PullRequestRef, str]] = []
        self.reviews: list[
            tuple[PullRequestRef, str, str, list[InlineReviewComment], str]
        ] = []

    def post_pr_comment(self, ref: PullRequestRef, body: str) -> PostedComment:
        self.posts.append((ref, body))
        return PostedComment(html_url="https://github.com/owner/repo/pull/1#issuecomment-9")

    def post_pr_review(
        self,
        ref: PullRequestRef,
        body: str,
        review_action: str = "comment",
        comments: list[InlineReviewComment] | None = None,
        commit_id: str = "",
    ) -> PostedComment:
        self.reviews.append((ref, body, review_action, comments or [], commit_id))
        return PostedComment(html_url="https://github.com/owner/repo/pull/1#pullrequestreview-9")


def test_pipeline_posts_review_comment_from_pr_url() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())

    result = pipeline.post_review_comment("https://github.com/owner/repo/pull/1", "# Report")

    assert result.html_url.endswith("#issuecomment-9")
    assert github.posts == [(PullRequestRef("owner", "repo", 1), "# Report")]


def test_pipeline_posts_pull_request_review_from_pr_url() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())

    result = pipeline.post_review_comment(
        "https://github.com/owner/repo/pull/1",
        "# Report",
        comment_mode="review",
    )

    assert result.html_url.endswith("#pullrequestreview-9")
    assert github.posts == []
    assert github.reviews == [(PullRequestRef("owner", "repo", 1), "# Report", "comment", [], "")]


def test_pipeline_passes_review_action_to_pull_request_review() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())

    pipeline.post_review_comment(
        "https://github.com/owner/repo/pull/1",
        "# Report",
        comment_mode="review",
        review_action="approve",
    )

    assert github.reviews == [(PullRequestRef("owner", "repo", 1), "# Report", "approve", [], "")]


def test_pipeline_posts_inline_review_comments_from_report_evidence() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        repo="owner/repo",
        pr_number=1,
        author="alice",
        summary="Summary text",
        head_sha="sha123",
        findings=[
            ReviewFinding(
                severity="high",
                source="ai",
                title="Token is logged",
                explanation="Avoid logging sensitive token values.",
                files=["src/auth.py"],
                evidence=[
                    EvidenceReference(
                        kind="code",
                        path="src/auth.py",
                        line_start=1,
                        line_end=2,
                    )
                ],
            )
        ],
        suggestions=[],
        changed_files=["src/auth.py"],
    )

    pipeline.post_review_comment(
        "https://github.com/owner/repo/pull/1",
        "# Report",
        comment_mode="review",
        include_inline_comments=True,
        report=report,
    )

    assert github.reviews == [
        (
            PullRequestRef("owner", "repo", 1),
            "# Report",
            "comment",
            [
                InlineReviewComment(
                    path="src/auth.py",
                    body="XEngineer AI risk: Token is logged\n\nAvoid logging sensitive token values.",
                    line=2,
                    start_line=1,
                )
            ],
            "sha123",
        )
    ]


def test_pipeline_requires_report_head_sha_for_inline_review_comments() -> None:
    github = PostingGitHubClient()
    pipeline = ReviewPipeline(github=github, llm=MockLLMClient())
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
    )

    with pytest.raises(ValueError, match="head SHA"):
        pipeline.post_review_comment(
            "https://github.com/owner/repo/pull/1",
            "# Report",
            comment_mode="review",
            include_inline_comments=True,
            report=report,
        )

    assert github.reviews == []


def test_build_inline_review_comments_orders_reversed_line_ranges() -> None:
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
        head_sha="sha123",
        findings=[
            ReviewFinding(
                severity="low",
                source="ai",
                title="Reversed range",
                explanation="The evidence range was reversed.",
                files=["src/auth.py"],
                evidence=[
                    EvidenceReference(
                        kind="code",
                        path="src/auth.py",
                        line_start=8,
                        line_end=3,
                    )
                ],
            )
        ],
    )

    comments = build_inline_review_comments(report)

    assert comments == [
        InlineReviewComment(
            path="src/auth.py",
            body="XEngineer AI risk: Reversed range\n\nThe evidence range was reversed.",
            line=8,
            start_line=3,
        )
    ]


def test_build_inline_review_comments_deduplicates_same_location() -> None:
    evidence = [
        EvidenceReference(
            kind="code",
            path="src/auth.py",
            line_start=3,
            line_end=8,
        )
    ]
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
        head_sha="sha123",
        findings=[
            ReviewFinding(
                severity="low",
                source="ai",
                title="Duplicate location",
                explanation="Finding should win.",
                files=["src/auth.py"],
                evidence=evidence,
            )
        ],
        suggestions=[
            ReviewSuggestion(
                severity="low",
                title="Duplicate location",
                body="Suggestion should be deduplicated.",
                files=["src/auth.py"],
                evidence=evidence,
            )
        ],
    )

    comments = build_inline_review_comments(report)

    assert comments == [
        InlineReviewComment(
            path="src/auth.py",
            body="XEngineer AI risk: Duplicate location\n\nFinding should win.",
            line=8,
            start_line=3,
        )
    ]


def test_pipeline_reports_when_client_cannot_publish_pull_request_reviews() -> None:
    pipeline = ReviewPipeline(github=FetchOnlyGitHubClient(), llm=MockLLMClient())

    with pytest.raises(ValueError, match="does not support pull request review comments"):
        pipeline.post_review_comment(
            "https://github.com/owner/repo/pull/1",
            "# Report",
            comment_mode="review",
        )


class FakeWebSearch:
    def search(self, query: str, max_results: int) -> list[dict[str, str]]:
        return [
            {
                "title": "Example result",
                "url": "https://example.test/result",
                "content": "A short result snippet.",
            }
        ]
