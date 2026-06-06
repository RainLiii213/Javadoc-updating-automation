from javadoc_miner.diff_extractor import (
    build_entity_patch,
    commit_has_javadoc_and_code_changes,
    entity_code_changed,
    parse_changed_paths,
)
from javadoc_miner.java_parser import parse_entities
from javadoc_miner.models import FileChange


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


def test_build_entity_patch_excludes_neighbor_method_changes():
    old = """
public class Foo {
    /**
     * Returns name.
     */
    public String getName() {
        return "name";
    }

    /** Other. */
    public int other() { return 1; }
}
""".strip()
    new = """
public class Foo {
    /**
     * Returns full name.
     */
    public String getName() {
        return "full name";
    }

    /** Other. */
    public int other() { return 2; }
}
""".strip()
    old_entity = parse_entities(old)[0]
    new_entity = parse_entities(new)[0]
    file_change = FileChange("src/main/java/Foo.java", old, new, "")

    patch = build_entity_patch(file_change, old_entity, new_entity)

    assert entity_code_changed(file_change, old_entity, new_entity)
    assert 'return "full name";' in patch
    assert "other() { return 2; }" not in patch
