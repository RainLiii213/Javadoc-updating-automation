import subprocess
from pathlib import Path

from javadoc_miner.cli import _classify_file_entities
from javadoc_miner.cli import mine_repository
from javadoc_miner.config import MinerConfig
from javadoc_miner.models import EntityDoc


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def test_mine_repository_extracts_method_rename_sample(tmp_path):
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
     * Returns the display name.
     */
    public String getName() {
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

public class Person {
    /**
     * Returns the full display name.
     */
    public String getFullName() {
        return "full name";
    }
}
""".strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "LANG-1234 rename getter")

    config = MinerConfig(
        repo_url=str(repo),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "dataset",
        max_commits=10,
        max_samples=10,
    )

    samples = mine_repository(config)

    assert len(samples) == 1
    assert samples[0].entity_name == "getFullName"
    assert samples[0].entity_signature == "public String getFullName()"
    assert samples[0].javadoc_change_type == "JAVADOC_MODIFICATION"
    assert samples[0].method_change_type == "METHOD_MODIFICATION"
    assert samples[0].quality == "A"


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

    assert _classify_file_entities(old_entities, new_entities, min_quality="B") == []


def test_entity_alignment_treats_new_overload_as_addition_when_original_survives():
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

    results = _classify_file_entities(old_entities, new_entities, min_quality="B")

    assert len(results) == 1
    assert results[0][1].parameters == ["final int ch"]
    assert results[0][2].change_type == "method_addition"
    assert results[0][2].javadoc_change_type == "JAVADOC_ADDITION"
    assert results[0][2].method_change_type == "METHOD_ADDITION"
    assert results[0][2].quality == "B"


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
        min_quality="C",
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
