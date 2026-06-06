from javadoc_miner.issue_finder import find_issues, resolve_issue_summary


def test_find_issues_extracts_github_and_apache_ids_in_order():
    text = "LANG-1234 fix docs. See #56 and IO-77. LANG-1234 repeated."

    assert find_issues(text) == ["LANG-1234", "#56", "IO-77"]


def test_find_issues_returns_empty_list_when_no_issue_id():
    assert find_issues("Improve JavaDoc for renamed method") == []


def test_resolve_issue_summary_falls_back_to_commit_message_for_local_repo():
    summary = resolve_issue_summary(
        repo_url="E:/repo",
        issue_ids=["LANG-1234"],
        commit_message="Improve null handling documentation\n\nLANG-1234",
    )

    assert summary == "Improve null handling documentation"
