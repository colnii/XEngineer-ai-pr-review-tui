from xengineer_pr_review.models import PullRequestRef
from xengineer_pr_review.review_tools import ReviewToolbox


def test_read_file_returns_bounded_numbered_content() -> None:
    github = FakeGitHub(
        files={
            "src/app.py": "first\nsecond\nthird\n",
        },
        tree_paths=["src/app.py"],
    )
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.read_file("src/app.py", max_lines=2)

    assert "File: src/app.py" in result
    assert "1: first" in result
    assert "2: second" in result
    assert "third" not in result
    assert "[truncated after 2 lines]" in result
    assert github.requests == [("read", "src/app.py", "abc123")]


def test_read_file_returns_error_for_unsafe_path() -> None:
    toolbox = ReviewToolbox(
        github=FakeGitHub(files={}, tree_paths=[]),
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.read_file("../secret.txt")

    assert result.startswith("read_file error")


def test_grep_code_searches_review_relevant_files_with_limits() -> None:
    github = FakeGitHub(
        files={
            "src/app.py": "target = True\nother = False\n",
            "tests/test_app.py": "assert target\n",
            "package-lock.json": '"target": "ignored"\n',
        },
        tree_paths=["src/app.py", "tests/test_app.py", "package-lock.json"],
    )
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.grep_code("target", max_results=2)

    assert "src/app.py:1: target = True" in result
    assert "tests/test_app.py:1: assert target" in result
    assert "package-lock.json" not in result
    assert "[truncated after 2 matches]" in result


def test_web_search_reports_unavailable_when_not_configured() -> None:
    toolbox = ReviewToolbox(
        github=FakeGitHub(files={}, tree_paths=[]),
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.web_search("python security advisory")

    assert "web_search unavailable" in result


def test_web_search_formats_configured_results() -> None:
    web_search = FakeWebSearch()
    toolbox = ReviewToolbox(
        github=FakeGitHub(files={}, tree_paths=[]),
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
        web_searcher=web_search,
    )

    result = toolbox.web_search("python security advisory", max_results=1)

    assert "Example result" in result
    assert "https://example.test/result" in result
    assert web_search.calls == [("python security advisory", 1)]


class FakeGitHub:
    def __init__(self, files: dict[str, str], tree_paths: list[str]) -> None:
        self.files = files
        self.tree_paths = tree_paths
        self.requests: list[tuple[str, str, str]] = []

    def fetch_file_text(self, ref: PullRequestRef, path: str, git_ref: str) -> str:
        self.requests.append(("read", path, git_ref))
        return self.files[path]

    def fetch_tree_paths(self, ref: PullRequestRef, git_ref: str) -> list[str]:
        self.requests.append(("tree", "", git_ref))
        return self.tree_paths


class FakeWebSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int) -> list[dict[str, str]]:
        self.calls.append((query, max_results))
        return [
            {
                "title": "Example result",
                "url": "https://example.test/result",
                "content": "A short result snippet.",
            }
        ]
