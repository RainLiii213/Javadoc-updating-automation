from javadoc_miner.text_utils import (
    is_code_diff_line,
    is_javadoc_diff_line,
    is_low_signal_commit_message,
    is_target_java_path,
    is_substantive_javadoc_change,
    javadoc_similarity,
    normalize_doc_text,
    normalize_javadoc_for_semantic_compare,
)


def test_target_java_path_accepts_main_java_only():
    assert is_target_java_path("src/main/java/org/example/Foo.java")
    assert is_target_java_path("module/src/main/java/org/example/Foo.java")
    assert is_target_java_path("guava/src/com/google/common/Foo.java")
    assert is_target_java_path("lucene/core/src/java/org/example/Foo.java")
    assert not is_target_java_path("src/test/java/org/example/FooTest.java")
    assert not is_target_java_path("src/main/java/org/example/FooTest.java")
    assert not is_target_java_path("guava-tests/test/com/google/common/Foo.java")
    assert not is_target_java_path("guava-testlib/src/com/google/common/Foo.java")
    assert not is_target_java_path("android/guava/src/com/google/common/Foo.java")
    assert not is_target_java_path("module/generated/src/main/java/org/example/Foo.java")
    assert not is_target_java_path("pom.xml")


def test_diff_line_classification_separates_javadoc_and_code():
    assert is_javadoc_diff_line("+     * @param name user name")
    assert is_javadoc_diff_line("-     /**")
    assert not is_javadoc_diff_line("+     public String getName() {")
    assert is_code_diff_line("+     public String getName() {")
    assert not is_code_diff_line("+     * @return name")
    assert not is_code_diff_line("+")


def test_normalize_doc_text_removes_formatting_noise():
    left = "/**\n * Returns name.\n */"
    right = "/**\n* Returns   name.\n*/"

    assert normalize_doc_text(left) == normalize_doc_text(right)


def test_substantive_change_filters_whitespace_and_formatting_only():
    old = "/**\n * Returns the value.\n */"
    new = "/** Returns   the value. */"

    assert not is_substantive_javadoc_change(old, new)


def test_substantive_change_filters_version_number_only():
    old = "/** Returns the value for version 1.2.3. */"
    new = "/** Returns the value for version 1.2.4. */"

    assert not is_substantive_javadoc_change(old, new)


def test_substantive_change_filters_ignored_tags_only():
    old = "/** Returns the value.\n * @see OldType\n * @since 1.0\n */"
    new = "/** Returns the value.\n * @see NewType\n * @since 2.0\n */"

    assert not is_substantive_javadoc_change(old, new)


def test_substantive_change_keeps_description_sentence_change():
    old = "/** Returns the cached value. */"
    new = "/** Computes and returns a fresh value when the cache is empty. */"

    assert is_substantive_javadoc_change(old, new)


def test_substantive_change_keeps_param_description_change():
    old = "/** @param value value to format */"
    new = "/** @param value value to format using the requested locale */"

    assert is_substantive_javadoc_change(old, new)


def test_substantive_change_keeps_single_contract_unit_term():
    old = "/** @param timeout timeout value */"
    new = "/** @param timeout timeout value in milliseconds */"

    assert javadoc_similarity(old, new) >= 0.8
    assert is_substantive_javadoc_change(old, new)


def test_semantic_normalization_ignores_tag_order_urls_and_entities():
    old = "/** A &lt; value. @param x first @return second https://example.com/a */"
    new = "/** A < value. @return second www.example.com/a @param x first */"

    assert sorted(normalize_javadoc_for_semantic_compare(old).split()) == sorted(
        normalize_javadoc_for_semantic_compare(new).split()
    )
    assert not is_substantive_javadoc_change(old, new)


def test_low_signal_commit_messages_are_filtered():
    assert is_low_signal_commit_message("Javadoc")
    assert is_low_signal_commit_message("Javadoc: Better parameter names")
    assert is_low_signal_commit_message("Sort members")
    assert is_low_signal_commit_message("Fix typo in documentation")
    assert is_low_signal_commit_message("Add Strings and refactor StringUtils")
    assert is_low_signal_commit_message("Rename internal class")
    assert is_low_signal_commit_message("Replace 2x empty lines with a single one")
    assert is_low_signal_commit_message("Fix code duplication")
    assert not is_low_signal_commit_message("Make ArrayUtils.shuffle() null-safe")
