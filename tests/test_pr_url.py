import pytest

from xengineer_pr_review.pr_url import parse_pr_url


def test_parse_standard_github_pr_url() -> None:
    ref = parse_pr_url("https://github.com/Textualize/textual/pull/123")
    assert ref.owner == "Textualize"
    assert ref.repo == "textual"
    assert ref.number == 123


def test_parse_url_with_extra_path() -> None:
    ref = parse_pr_url("https://github.com/openai/openai-python/pull/456/files")
    assert ref.owner == "openai"
    assert ref.repo == "openai-python"
    assert ref.number == 456


def test_reject_non_github_url() -> None:
    with pytest.raises(ValueError, match="GitHub PR URL"):
        parse_pr_url("https://example.com/owner/repo/pull/1")


def test_reject_url_without_pull_number() -> None:
    with pytest.raises(ValueError, match="/pull/<number>"):
        parse_pr_url("https://github.com/owner/repo/issues/1")
