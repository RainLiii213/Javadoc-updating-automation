import subprocess
from pathlib import Path

from javadoc_miner.cli import _classify_file_entities
from javadoc_miner.cli import mine_repository
from javadoc_miner.cli import _select_samples
from javadoc_miner.config import MinerConfig
from javadoc_miner.java_parser import parse_entities
from javadoc_miner.models import EntityDoc, FileChange, OutputSample


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def test_mine_repository_extracts_connected_behavior_and_contract_update(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")

    java_path = repo / "src/main/java/org/example/Person.java"
    java_path.parent.mkdir(parents=True)
    java_path.write_text(
        """
package org.example;

public class Person {
    /**
     * Null values are not allowed.
     */
    public String normalize(String value) {
        return Objects.requireNonNull(value);
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")

    java_path.write_text(
        """
package org.example;

public class Person {
    /**
     * Null values are treated as an empty string.
     */
    public String normalize(String value) {
        return value == null ? StringUtils.EMPTY : value;
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "LANG-1234 handle null values")

    config = MinerConfig(
        repo_url=str(repo),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "dataset",
        max_commits=10,
        max_samples=10,
    )

    samples = mine_repository(config)

    assert len(samples) == 1
    assert samples[0].entity_name == "normalize"
    assert samples[0].entity_signature == "public String normalize(String value)"
    assert samples[0].javadoc_change_type == "JAVADOC_MODIFICATION"
    assert samples[0].method_change_type == "METHOD_MODIFICATION"
    assert samples[0].file_path == "src/main/java/org/example/Person.java"
    assert samples[0].issue_summary == "handle null values"


def test_entity_alignment_does_not_cross_match_overloads():
    old_entities = [
        EntityDoc(
            entity_type="method",
            name="getFraction",
            signature="public static Fraction getFraction(double value)",
            javadoc="/** Creates a Fraction from a double. */",
            start_line=1,
            end_line=3,
            return_type="Fraction",
            parameters=["double value"],
        ),
        EntityDoc(
            entity_type="method",
            name="getFraction",
            signature="public static Fraction getFraction(int numerator, int denominator)",
            javadoc="/** Creates a Fraction from numerator and denominator. */",
            start_line=4,
            end_line=6,
            return_type="Fraction",
            parameters=["int numerator", "int denominator"],
        ),
    ]
    new_entities = [
        EntityDoc(
            entity_type="method",
            name="getFraction",
            signature="public static Fraction getFraction(double value)",
            javadoc="/** Creates a Fraction from a double. */",
            start_line=1,
            end_line=3,
            return_type="Fraction",
            parameters=["double value"],
        ),
        EntityDoc(
            entity_type="method",
            name="getFraction",
            signature="public static Fraction getFraction(int numerator, int denominator)",
            javadoc="/** Creates a Fraction from numerator and denominator. */",
            start_line=4,
            end_line=6,
            return_type="Fraction",
            parameters=["int numerator", "int denominator"],
        ),
    ]

    assert _classify_file_entities(old_entities, new_entities) == []


def test_entity_alignment_filters_new_overload_as_creation():
    old_entities = [
        EntityDoc(
            entity_type="method",
            name="isAsciiNumeric",
            signature="public static boolean isAsciiNumeric(final char ch)",
            javadoc="/** Tests whether the character is ASCII numeric. */",
            start_line=1,
            end_line=3,
            return_type="boolean",
            parameters=["final char ch"],
        )
    ]
    new_entities = [
        EntityDoc(
            entity_type="method",
            name="isAsciiNumeric",
            signature="public static boolean isAsciiNumeric(final int ch)",
            javadoc="/** Tests whether the code point is ASCII numeric. */",
            start_line=4,
            end_line=6,
            return_type="boolean",
            parameters=["final int ch"],
        ),
        EntityDoc(
            entity_type="method",
            name="isAsciiNumeric",
            signature="public static boolean isAsciiNumeric(final char ch)",
            javadoc="/** Tests whether the character is ASCII numeric. */",
            start_line=1,
            end_line=3,
            return_type="boolean",
            parameters=["final char ch"],
        ),
    ]

    results = _classify_file_entities(old_entities, new_entities)

    assert results == []


def test_entity_alignment_does_not_cross_match_reordered_same_signature_methods():
    old_entities = [
        EntityDoc("method", "getDuration", "Duration getDuration()", "/** Stopwatch duration. */", 1, 2, parameters=[]),
        EntityDoc("method", "getDuration", "Duration getDuration()", "/** Split duration. */", 20, 21, parameters=[]),
    ]
    new_entities = [
        EntityDoc("method", "getDuration", "Duration getDuration()", "/** Split duration. */", 1, 2, parameters=[]),
        EntityDoc("method", "getDuration", "Duration getDuration()", "/** Stopwatch duration. */", 20, 21, parameters=[]),
    ]

    assert _classify_file_entities(old_entities, new_entities) == []


def test_mine_repository_extracts_one_sample_per_changed_entity(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")

    java_path = repo / "src/main/java/org/example/Names.java"
    java_path.parent.mkdir(parents=True)
    java_path.write_text(
        """
package org.example;

public class Names {
    /**
     * Returns first name.
     */
    public String first() {
        return "first";
    }

    /**
     * Returns last name.
     */
    public String last() {
        return "last";
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")

    java_path.write_text(
        """
package org.example;

public class Names {
    /**
     * Returns given name.
     */
    public String first() {
        return "given";
    }

    /**
     * Returns family name.
     */
    public String last() {
        return "family";
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "LANG-1234 update names")

    config = MinerConfig(
        repo_url=str(repo),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "dataset",
        max_commits=10,
        max_samples=10,
    )

    samples = mine_repository(config)

    assert len(samples) == 2
    assert {sample.entity_name for sample in samples} == {"first", "last"}
    first_sample = next(sample for sample in samples if sample.entity_name == "first")
    last_sample = next(sample for sample in samples if sample.entity_name == "last")
    assert "family" not in first_sample.code_after
    assert "given" not in last_sample.code_after
    assert first_sample.javadoc_change_type == "JAVADOC_MODIFICATION"
    assert first_sample.method_change_type == "METHOD_MODIFICATION"


def test_mine_repository_filters_doc_only_change(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")

    java_path = repo / "src/main/java/org/example/Name.java"
    java_path.parent.mkdir(parents=True)
    java_path.write_text(
        """
package org.example;

public class Name {
    /**
     * Returns name.
     */
    public String get() {
        return "name";
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")

    java_path.write_text(
        """
package org.example;

public class Name {
    /**
     * Returns display name.
     */
    public String get() {
        return "name";
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "LANG-1234 doc-only change")

    config = MinerConfig(
        repo_url=str(repo),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "dataset",
        max_commits=10,
        max_samples=10,
    )

    assert mine_repository(config) == []


def test_class_level_code_and_substantive_javadoc_change_is_output():
    old_source = """
/**
 * Stores an immutable person name.
 */
public class Person {
    public Person(String name) {
        this.name = name;
    }
}
""".strip()
    new_source = """
/**
 * Stores a person name and rejects null names.
 */
public class Person {
    public Person(String name) {
        this.name = Objects.requireNonNull(name);
    }
}
""".strip()
    file_change = FileChange("src/main/java/org/example/Person.java", old_source, new_source)

    results = _classify_file_entities(
        parse_entities(old_source),
        parse_entities(new_source),
        file_change=file_change,
    )

    assert len(results) == 1
    assert results[0][1].entity_type == "class"
    assert results[0][2].javadoc_change_type == "JAVADOC_MODIFICATION"
    assert results[0][2].method_change_type == "METHOD_MODIFICATION"


def test_field_level_code_and_javadoc_change_is_not_output():
    old_source = """
public class Person {
    /** Stores the original display name. */
    private String name;
}
""".strip()
    new_source = """
public class Person {
    /** Stores the normalized display name for output. */
    private final String name;
}
""".strip()
    file_change = FileChange("src/main/java/org/example/Person.java", old_source, new_source)

    results = _classify_file_entities(
        parse_entities(old_source),
        parse_entities(new_source),
        file_change=file_change,
    )

    assert results == []


def test_selection_keeps_only_available_high_confidence_samples():
    def sample(index):
        return OutputSample(
            repo="apache/commons-lang",
            commit_hash=str(index),
            commit_message="change",
            issue_summary="",
            code_before="old",
            code_after="new",
            javadoc_before="old docs",
            javadoc_after="new docs",
            entity_name=f"method{index}",
            entity_signature=f"method{index}()",
            javadoc_change_type="JAVADOC_MODIFICATION",
            method_change_type="METHOD_MODIFICATION",
            issue_id="",
            commit_url="",
            entity_type="method",
        )

    samples = [sample(index) for index in range(2)]
    selected = _select_samples(samples, max_samples=10)

    assert len(selected) == 2


def test_selection_deduplicates_same_commit_and_entity_name():
    def sample(commit_hash, entity_name):
        return OutputSample(
            repo="apache/commons-lang",
            commit_hash=commit_hash,
            commit_message="Make behavior null-safe",
            issue_summary="Make behavior null-safe",
            code_before="return value;",
            code_after="return value == null ? EMPTY : value;",
            javadoc_before="/** Returns value. */",
            javadoc_after="/** Returns empty for null values. */",
            entity_name=entity_name,
            entity_signature=f"{entity_name}()",
            javadoc_change_type="JAVADOC_MODIFICATION",
            method_change_type="METHOD_MODIFICATION",
            issue_id="",
            commit_url="",
            entity_type="method",
        )

    samples = [
        sample("abc", "shuffle"),
        sample("abc", "shuffle"),
        sample("abc", "fill"),
    ]
    selected = _select_samples(samples, max_samples=10)

    assert [(item.commit_hash, item.entity_name) for item in selected] == [
        ("abc", "shuffle"),
        ("abc", "fill"),
    ]


def test_selection_caps_samples_per_commit_for_review_diversity():
    samples = []
    for index in range(5):
        samples.append(
            OutputSample(
                repo="apache/commons-lang",
                commit_hash="abc",
                commit_message="Make behavior null-safe",
                issue_summary="Make behavior null-safe",
                code_before="return value;",
                code_after="return value == null ? EMPTY : value;",
                javadoc_before="/** Returns value. */",
                javadoc_after="/** Returns empty for null values. */",
                entity_name=f"method{index}",
                entity_signature=f"method{index}()",
                javadoc_change_type="JAVADOC_MODIFICATION",
                method_change_type="METHOD_MODIFICATION",
                issue_id="",
                commit_url="",
                entity_type="method",
            )
        )
    selected = _select_samples(samples, max_samples=10)

    assert len(selected) == 3
