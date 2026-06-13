from javadoc_miner.classifier import (
    classify_entity_change,
    is_logically_connected_change,
    is_substantial_code_change,
)
from javadoc_miner.models import EntityDoc


def entity(name, javadoc, return_type="String", parameters=None, throws=None):
    return EntityDoc(
        entity_type="method",
        name=name,
        signature=f"public {return_type} {name}()",
        javadoc=javadoc,
        start_line=1,
        end_line=5,
        return_type=return_type,
        parameters=parameters or [],
        throws=throws or [],
    )


def field(name, javadoc):
    return EntityDoc(
        entity_type="field",
        name=name,
        signature=f"private String {name}",
        javadoc=javadoc,
        start_line=1,
        end_line=3,
    )


def test_filter_method_rename_only():
    old = entity("getName", "/** Returns name. */")
    new = entity("getFullName", "/** Returns full name. */")

    result = classify_entity_change(
        old,
        new,
        nearby_code_changed=True,
        code_before='public String getName() { return "name"; }',
        code_after='public String getFullName() { return "name"; }',
    )

    assert result is None


def test_keep_parameter_unit_contract_change():
    old = entity("waitFor", "/** @param timeout timeout value */", parameters=["long timeout"])
    new = entity(
        "waitFor",
        "/** @param timeout timeout in milliseconds */",
        parameters=["long timeout"],
    )

    result = classify_entity_change(
        old,
        new,
        nearby_code_changed=True,
        code_before="return wait(timeout);",
        code_after="return wait(TimeUnit.MILLISECONDS.toNanos(timeout));",
    )

    assert result.change_type == "code_and_javadoc_change"


def test_filter_new_method_with_javadoc():
    new = entity("isBlank", "/** Returns true when blank. */", return_type="boolean")

    result = classify_entity_change(None, new, nearby_code_changed=True)

    assert result is None


def test_filter_only_see_change():
    old = entity("getName", "/** Returns name. */")
    new = entity("getName", "/** Returns name.\n * @see Person\n */")

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result is None


def test_filter_deleted_method_javadoc():
    old = entity("getName", "/** Returns the normalized display name for the person. */")

    result = classify_entity_change(old, None, nearby_code_changed=True)

    assert result is None


def test_filter_field_change_even_when_code_and_javadoc_change():
    old = field("name", "/** The original display name for the person. */")
    new = field("name", "/** The normalized display name for the person. */")

    assert classify_entity_change(old, new, nearby_code_changed=True) is None


def test_filter_javadoc_change_without_entity_code_patch():
    old = entity("getName", "/** Returns the original display name. */")
    new = entity("getName", "/** Returns the normalized display name. */")

    assert classify_entity_change(old, new, nearby_code_changed=False) is None


def test_filter_substantial_but_unrelated_code_and_javadoc_changes():
    old = entity("convert", "/** Returns the original display name. */")
    new = entity("convert", "/** Returns the normalized display name. */")

    result = classify_entity_change(
        old,
        new,
        nearby_code_changed=True,
        code_before="if (input == null) { throw new IllegalArgumentException(); } return input;",
        code_after="if (input.isEmpty()) { throw new IllegalArgumentException(); } return input;",
    )

    assert result is None


def test_filter_formatting_reordering_and_identifier_rename_code_changes():
    assert not is_substantial_code_change("return value + 1;", "return renamed + 1;")
    assert not is_substantial_code_change("first(); second();", "second(); first();")
    assert not is_substantial_code_change("return value;", "return   value;")


def test_logical_connection_detects_null_contract_update():
    old = entity("normalize", "/** Null values are not allowed. */")
    new = entity("normalize", "/** Null values are treated as Instant.EPOCH. */")

    assert is_logically_connected_change(
        "return Objects.requireNonNull(value);",
        "return value == null ? Instant.EPOCH : value;",
        old,
        new,
    )


def test_filter_high_similarity_class_doc_with_weak_single_term_link():
    old = EntityDoc("class", "Consumer", "class Consumer", "/** Consumer operation. */", 1, 2)
    new = EntityDoc("class", "Consumer", "class Consumer", "/** Consumer action. */", 1, 2)

    assert not is_logically_connected_change(
        "public class Consumer {}",
        "public class Consumer { void accept() {} }",
        old,
        new,
    )


def test_filter_high_similarity_method_doc_with_non_contract_overlap():
    old = entity("render", "/** Builds the formatted output value. */")
    new = entity("render", "/** Creates the formatted output value. */")

    assert not is_logically_connected_change(
        "return builder.build();",
        "return builder.create();",
        old,
        new,
    )
