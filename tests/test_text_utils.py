from javadoc_miner.text_utils import (
    is_code_diff_line,
    is_javadoc_diff_line,
    is_target_java_path,
    normalize_doc_text,
)


def test_target_java_path_accepts_main_java_only():
    assert is_target_java_path("src/main/java/org/example/Foo.java")
    assert not is_target_java_path("src/test/java/org/example/FooTest.java")
    assert not is_target_java_path("src/main/java/org/example/FooTest.java")
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
