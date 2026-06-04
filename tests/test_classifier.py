from javadoc_miner.classifier import classify_entity_change
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


def test_classify_method_rename_as_quality_a():
    old = entity("getName", "/** Returns name. */")
    new = entity("getFullName", "/** Returns full name. */")

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result.change_type == "method_rename"
    assert result.quality == "A"


def test_classify_parameter_change_as_quality_a():
    old = entity("format", "/** Formats value. */", parameters=["String value"])
    new = entity(
        "format",
        "/** Formats value with locale. */",
        parameters=["String value", "Locale locale"],
    )

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result.change_type == "parameter_change"
    assert result.quality == "A"


def test_classify_new_method_with_javadoc_as_quality_b():
    new = entity("isBlank", "/** Returns true when blank. */", return_type="boolean")

    result = classify_entity_change(None, new, nearby_code_changed=True)

    assert result.change_type == "method_addition"
    assert result.quality == "B"


def test_filter_only_see_change():
    old = entity("getName", "/** Returns name. */")
    new = entity("getName", "/** Returns name.\n * @see Person\n */")

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result is None
