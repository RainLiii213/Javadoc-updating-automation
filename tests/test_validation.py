from javadoc_miner.models import OutputSample
from javadoc_miner.validation import validate_code_snippet, validate_output_sample


def sample(code_before: str, code_after: str, entity_type: str = "method") -> OutputSample:
    return OutputSample(
        repo="apache/commons-io",
        commit_hash="abc",
        commit_message="Handle null values",
        issue_summary="Handle null values",
        code_before=code_before,
        code_after=code_after,
        javadoc_before="/** Null values are rejected. */",
        javadoc_after="/** Null values produce an empty result. */",
        entity_name="normalize",
        entity_signature="String normalize(String value)",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        issue_id="",
        commit_url="",
        entity_type=entity_type,
    )


def test_complete_method_passes_structure_validation():
    code = "public String normalize(String value) {\n    return value;\n}"

    assert validate_code_snippet(code, "method") == ""


def test_rejects_unclosed_javadoc_unfinished_statement_and_placeholder():
    assert validate_code_snippet("public void run() {\n/**", "method") == "unclosed_javadoc"
    assert validate_code_snippet("public void run() {\n    call(", "method") == "unfinished_ending"
    assert (
        validate_code_snippet(
            "public void run() {\n// ... relevant changed context ...\n}",
            "method",
        )
        == "placeholder_context"
    )


def test_rejects_partial_changed_hunk():
    assert validate_code_snippet("if (value == null) {\n    return EMPTY;", "method") == "unbalanced_braces"


def test_invalid_class_placeholder_is_moved_to_review():
    result = validate_output_sample(
        sample(
            "public class Names {",
            "public class Names {\n// ... relevant changed context ...",
            entity_type="class",
        )
    )

    assert result.disposition == "review"
    assert result.reason.startswith("invalid_class_context:")


def test_long_complete_class_is_not_rejected_only_for_length():
    body = "\n".join(f"    int value{i};" for i in range(101))
    result = validate_output_sample(
        sample(
            f"public class Names {{\n{body}\n    int oldValue;\n}}",
            f"public class Names {{\n{body}\n    String newValue;\n}}",
            entity_type="class",
        )
    )

    assert result.disposition == "retain"


def test_very_large_complete_class_is_discarded():
    body = "\n".join(f"    int value{i};" for i in range(501))
    result = validate_output_sample(
        sample(
            f"public class Names {{\n{body}\n}}",
            f"public class Names {{\n{body}\n    int added;\n}}",
            entity_type="class",
        )
    )

    assert result.disposition == "discard"
    assert result.reason == "class_context_too_large"


def test_weak_inheritdoc_only_change_is_discarded():
    value = sample(
        "public String normalize(String value) { return value; }",
        "public String normalize(String value) { return value == null ? EMPTY : value; }",
    )
    value = OutputSample(
        **{
            **value.__dict__,
            "javadoc_after": "/** {@inheritDoc}\n * @see Names\n */",
        }
    )

    result = validate_output_sample(value)

    assert result.disposition == "discard"
    assert result.reason == "weak_inheritdoc_only"
