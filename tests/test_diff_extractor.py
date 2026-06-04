from javadoc_miner.diff_extractor import (
    commit_has_javadoc_and_code_changes,
    parse_changed_paths,
)


def test_parse_changed_paths_filters_main_java_files():
    name_status = "\n".join(
        [
            "M\tsrc/main/java/org/example/Foo.java",
            "M\tsrc/test/java/org/example/FooTest.java",
            "M\tpom.xml",
        ]
    )

    assert parse_changed_paths(name_status) == ["src/main/java/org/example/Foo.java"]


def test_commit_has_javadoc_and_code_changes_requires_both():
    patch = """
diff --git a/src/main/java/Foo.java b/src/main/java/Foo.java
-     * Returns name.
+     * Returns full name.
-    public String getName() {
+    public String getFullName() {
"""

    assert commit_has_javadoc_and_code_changes(patch)


def test_commit_has_javadoc_and_code_changes_rejects_docs_only():
    patch = """
-     * Returns name.
+     * Returns full name.
"""

    assert not commit_has_javadoc_and_code_changes(patch)
