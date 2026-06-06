from javadoc_miner import issue_finder
from javadoc_miner.issue_finder import find_issues, resolve_issue_summary


def test_find_issues_extracts_github_and_apache_ids_in_order():
    text = "LANG-1234 fix docs. See #56 and IO-77. LANG-1234 repeated."

    assert find_issues(text) == ["LANG-1234", "#56", "IO-77"]


def test_find_issues_returns_empty_list_when_no_issue_id():
    assert find_issues("Improve JavaDoc for renamed method") == []


def test_resolve_issue_summary_falls_back_to_commit_message_for_local_repo(monkeypatch):
    issue_finder._SUMMARY_CACHE.clear()
    monkeypatch.setattr(issue_finder, "_jira_issue_title", lambda issue_id: "")
    summary = resolve_issue_summary(
        repo_url="E:/repo",
        issue_ids=["LANG-1234"],
        commit_message="Improve null handling documentation\n\nLANG-1234",
    )

    assert summary == "Improve null handling documentation"


def test_resolve_issue_summary_cleans_issue_ids_from_commit_fallback(monkeypatch):
    issue_finder._SUMMARY_CACHE.clear()
    monkeypatch.setattr(issue_finder, "_jira_issue_title", lambda issue_id: "")
    monkeypatch.setattr(issue_finder, "_github_issue_metadata", lambda repo_url, issue_id: None, raising=False)

    summary = resolve_issue_summary(
        repo_url="E:/repo",
        issue_ids=["LANG-1825", "#1647"],
        commit_message="[LANG-1825] EqualsBuilder.reflectionAppend tries to set visibility on (#1647)",
    )

    assert summary == "EqualsBuilder.reflectionAppend tries to set visibility on"


def test_resolve_issue_summary_preserves_method_signature_parentheses(monkeypatch):
    issue_finder._SUMMARY_CACHE.clear()
    monkeypatch.setattr(issue_finder, "_github_issue_metadata", lambda repo_url, issue_id: None, raising=False)

    summary = resolve_issue_summary(
        repo_url="https://github.com/apache/commons-lang",
        issue_ids=["#1683"],
        commit_message="Add Instants.toMillisSince(Instant) (#1683)",
    )

    assert summary == "Add Instants.toMillisSince(Instant)"


def test_resolve_issue_summary_prefers_github_issue_title_over_jira_title(monkeypatch):
    issue_finder._SUMMARY_CACHE.clear()
    monkeypatch.setattr(
        issue_finder,
        "_github_issue_metadata",
        lambda repo_url, issue_id: {
            "title": "GitHub issue title",
            "is_pull_request": False,
        },
        raising=False,
    )
    monkeypatch.setattr(issue_finder, "_github_issue_title", lambda repo_url, issue_id: "GitHub issue title")
    monkeypatch.setattr(issue_finder, "_jira_issue_title", lambda issue_id: "JIRA issue title")

    summary = resolve_issue_summary(
        repo_url="https://github.com/apache/commons-lang",
        issue_ids=["LANG-1234", "#56"],
        commit_message="LANG-1234 fallback (#56)",
    )

    assert summary == "GitHub issue title"


def test_resolve_issue_summary_prefers_jira_title_over_pull_request_title(monkeypatch):
    issue_finder._SUMMARY_CACHE.clear()
    monkeypatch.setattr(
        issue_finder,
        "_github_issue_metadata",
        lambda repo_url, issue_id: {
            "title": "Pull request implementation title",
            "is_pull_request": True,
        },
        raising=False,
    )
    monkeypatch.setattr(issue_finder, "_github_issue_title", lambda repo_url, issue_id: "Pull request implementation title")
    monkeypatch.setattr(issue_finder, "_jira_issue_title", lambda issue_id: "JIRA issue title")

    summary = resolve_issue_summary(
        repo_url="https://github.com/apache/commons-lang",
        issue_ids=["#56", "LANG-1234"],
        commit_message="LANG-1234 fallback (#56)",
    )

    assert summary == "JIRA issue title"
