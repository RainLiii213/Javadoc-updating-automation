from scripts.merge_and_clean_datasets import (
    clean_change,
    content_fingerprint,
    deduplicate_changes,
    format_only_reason,
    group_by_commit,
    infer_entity_type,
    is_weak_issue_summary,
    normalize_file_text,
)
from scripts.recover_without_commit_cap import group_flat_changes


def base_change(commit_hash: str = "abc", summary: str = "Handle blank values") -> dict:
    return {
        "commit_hash": commit_hash,
        "issue_summary": summary,
        "code_before": "public String value() {\n    return \"a\";\n}",
        "code_after": "public String value() {\n    return \"b\";\n}",
        "javadoc_before": "/** Returns a. */",
        "javadoc_after": "/** Returns b. */",
        "_dataset": "old",
        "_project_slug": "example_project",
        "_repository_url": "https://github.com/example/project.git",
        "_source_sample_id": "example_project/sample_0001",
        "_source_order": 1,
        "_entity_type": "method",
        "_issue_summary_source": "existing_issue_summary",
    }


def test_content_fingerprint_normalizes_line_endings_and_trailing_spaces():
    one = base_change()
    two = base_change()
    two["code_before"] = "public String value() {\r\n    return \"a\";   \r\n}\r\n"

    assert normalize_file_text(two["code_before"]) == one["code_before"]
    assert content_fingerprint(one) == content_fingerprint(two)


def test_format_only_detects_wrapping_and_punctuation_but_not_semantic_change():
    assert format_only_reason(
        "/** Returns the value */",
        "/**\n * Returns the value.\n */",
    )
    assert not format_only_reason(
        "/** The value must not be null. */",
        "/** The value must not be null or blank. */",
    )


def test_deduplicate_changes_removes_identical_content_not_reverts():
    original = base_change("one")
    duplicate = dict(base_change("two"))
    duplicate["_dataset"] = "new"
    duplicate["_source_order"] = 2
    revert = base_change("three")
    revert["code_before"], revert["code_after"] = revert["code_after"], revert["code_before"]
    revert["javadoc_before"], revert["javadoc_after"] = revert["javadoc_after"], revert["javadoc_before"]

    kept, removed = deduplicate_changes([original, duplicate, revert])

    assert len(kept) == 2
    assert len(removed) == 1
    assert removed[0]["reason"] == "identical_content"


def test_infer_entity_type_for_method_and_class():
    method = "public int size() {\n    return 1;\n}"
    klass = "public class Box {\n    public int size() {\n        return 1;\n    }\n}"

    assert infer_entity_type(method, method.replace("1", "2")) == "method"
    assert infer_entity_type(klass, klass.replace("1", "2")) == "class"


def test_group_by_commit_assigns_stable_change_indexes():
    first = clean_change(base_change("same"))
    second = clean_change(base_change("same"))
    assert first is not None and second is not None
    first["_entity_type"] = "method"
    first["_issue_summary_source"] = "existing_issue_summary"
    second["_entity_type"] = "method"
    second["_issue_summary_source"] = "existing_issue_summary"
    second["code_after"] = "public String value() {\n    return \"c\";\n}"
    second["javadoc_after"] = "/** Returns c. */"

    grouped, conflicts = group_by_commit([first, second])

    assert conflicts == []
    assert len(grouped) == 1
    assert [change["change_index"] for change in grouped[0]["changes"]] == [1, 2]


def test_recovery_grouping_keeps_six_changes_with_continuous_indexes():
    changes = []
    for index in range(6):
        change = clean_change(base_change("same"))
        assert change is not None
        change["project_slug"] = "example_project"
        change["repository_url"] = "https://github.com/example/project.git"
        change["entity_type"] = "class" if index >= 4 else "method"
        change["code_after"] = f"public String value() {{\n    return \"{index}\";\n}}"
        change["javadoc_after"] = f"/** Returns {index}. */"
        changes.append(change)

    grouped = group_flat_changes(changes)

    assert len(grouped) == 1
    assert len(grouped[0]["changes"]) == 6
    assert [change["change_index"] for change in grouped[0]["changes"]] == [1, 2, 3, 4, 5, 6]


def test_weak_issue_summary_detection():
    assert is_weak_issue_summary("PR")
    assert is_weak_issue_summary("Fix")
    assert is_weak_issue_summary("Handle value by")
    assert not is_weak_issue_summary(
        "Improve consistency of Javadoc for Multisets.union/intersection/sum/difference, highlighting how they differ and the mathematical operation each is based on."
    )
    assert not is_weak_issue_summary("Handle null or blank values")
