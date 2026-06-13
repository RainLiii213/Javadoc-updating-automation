from javadoc_miner.diff_extractor import (
    bounded_entity_code_pair,
    commit_has_javadoc_and_code_changes,
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


def test_parse_changed_paths_keeps_deleted_main_java_files():
    name_status = "\n".join(
        [
            "D\tsrc/main/java/org/example/Removed.java",
            "D\tsrc/test/java/org/example/RemovedTest.java",
        ]
    )

    assert parse_changed_paths(name_status) == ["src/main/java/org/example/Removed.java"]


def test_extract_file_changes_does_not_carry_full_commit_patch():
    from javadoc_miner.diff_extractor import extract_file_changes

    class FakeRepo:
        def show_name_status(self, commit_hash):
            return "M\tsrc/main/java/org/example/Foo.java"

        def show_commit_patch(self, commit_hash):
            raise AssertionError("full commit patch should not be loaded into FileChange")

        def show_file(self, commit_ref, path):
            if commit_ref.endswith("^"):
                return "old"
            return "new"

    changes = extract_file_changes(FakeRepo(), "abc123")

    assert len(changes) == 1
    assert changes[0].old_content == "old"
    assert changes[0].new_content == "new"


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


def test_bounded_entity_code_pair_limits_large_class_context():
    old = "/** Class docs. */\npublic class Large {\n" + "\n".join(f"int value{i};" for i in range(150)) + "\n}"
    new = old.replace("int value120;", "String value120;")
    old_entity = parse_entities(old)[0]
    new_entity = parse_entities(new)[0]

    before, after = bounded_entity_code_pair(FileChange("src/main/java/Large.java", old, new), old_entity, new_entity)

    assert len(before.splitlines()) <= 100
    assert len(after.splitlines()) <= 100
    assert "value120" in before
    assert "value120" in after
