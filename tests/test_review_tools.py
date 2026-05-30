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
    assert "truncated after 2 lines" in result
    assert "single file is too large" in result
    assert github.requests == [("read", "src/app.py", "abc123")]


def test_read_file_defaults_to_1000_lines_and_flags_large_files() -> None:
    github = FakeGitHub(
        files={
            "src/large.py": "\n".join(f"line {index}" for index in range(1, 1002)),
        },
        tree_paths=["src/large.py"],
    )
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.read_file("src/large.py")

    assert "1000: line 1000" in result
    assert "1001: line 1001" not in result
    assert "single file is too large" in result


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


def test_grep_code_reuses_tree_listing_for_repeated_searches() -> None:
    github = FakeGitHub(
        files={
            "src/app.py": "target = True\n",
            "tests/test_app.py": "assert target\n",
        },
        tree_paths=["src/app.py", "tests/test_app.py"],
    )
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    first = toolbox.grep_code("target")
    second = toolbox.grep_code("assert")

    assert "src/app.py:1: target = True" in first
    assert "tests/test_app.py:1: assert target" in second
    assert [request for request in github.requests if request[0] == "tree"] == [
        ("tree", "", "abc123")
    ]
    assert [request for request in github.requests if request[0] == "read"] == [
        ("read", "src/app.py", "abc123"),
        ("read", "tests/test_app.py", "abc123"),
    ]


def test_grep_code_path_glob_can_search_low_signal_files() -> None:
    github = FakeGitHub(
        files={
            "src/app.py": "target = False\n",
            "package-lock.json": '"target": "included when explicit"\n',
        },
        tree_paths=["src/app.py", "package-lock.json"],
    )
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.grep_code("target", path_glob="package-lock.json")

    assert "package-lock.json:1:" in result
    assert "src/app.py" not in result


def test_grep_code_reports_when_file_search_budget_is_exhausted() -> None:
    files = {f"src/file_{index}.py": "nothing here\n" for index in range(45)}
    github = FakeGitHub(files=files, tree_paths=list(files))
    toolbox = ReviewToolbox(
        github=github,
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
    )

    result = toolbox.grep_code("target")

    assert "file search budget exhausted" in result
    assert len([request for request in github.requests if request[0] == "read"]) == 40


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


def test_web_search_redacts_provider_errors() -> None:
    toolbox = ReviewToolbox(
        github=FakeGitHub(files={}, tree_paths=[]),
        ref=PullRequestRef("owner", "repo", 1),
        git_ref="abc123",
        web_searcher=FailingWebSearch(),
    )

    result = toolbox.web_search("python security advisory")

    assert result == "web_search error: search request failed."
    assert "secret-token" not in result


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


class FailingWebSearch:
    def search(self, query: str, max_results: int) -> list[dict[str, str]]:
        raise RuntimeError("provider rejected secret-token")
