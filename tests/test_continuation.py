import csv
import json

from javadoc_miner.continuation import (
    ContinuationConfig,
    build_continuation_plan,
    mine_continuation_dataset,
)
from javadoc_miner.models import ExtractionStats, OutputSample
from javadoc_miner.repositories import RepositorySpec
from javadoc_miner.writer import SampleWriter


def make_sample(commit_hash: str, after_word: str = "empty") -> OutputSample:
    return OutputSample(
        repo="apache/lucene",
        commit_hash=commit_hash,
        commit_message="LUCENE-1234 handle null values",
        issue_summary="handle null values",
        code_before="public String normalize(String value) {\n    return Objects.requireNonNull(value);\n}",
        code_after=f"public String normalize(String value) {{\n    return value == null ? \"{after_word}\" : value;\n}}",
        javadoc_before="/** Null values are rejected. */",
        javadoc_after=f"/** Null values produce {after_word} output. */",
        entity_name="normalize",
        entity_signature="public String normalize(String value)",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        issue_id="LUCENE-1234",
        commit_url="",
        entity_type="method",
        file_path="src/main/java/org/example/Names.java",
    )


def write_baseline(tmp_path, spec: RepositorySpec, complete_history: bool = False) -> None:
    baseline_dir = tmp_path / "final_dataset"
    project_dir = baseline_dir / spec.slug
    SampleWriter(project_dir).write_samples([make_sample("base1")])
    (project_dir / "metadata.json").write_text(
        json.dumps(
            {
                "project_slug": spec.slug,
                "repository_name": spec.name,
                "repository_url": spec.url,
                "retained_samples": 1,
                "commits_scanned": 5,
                "complete_history": complete_history,
                "stop_reason": "full_history_scanned" if complete_history else "history_incomplete",
            }
        ),
        encoding="utf-8",
    )
    (baseline_dir / "combined_samples.json").write_text(
        json.dumps([make_sample("base1").to_json_dict()]),
        encoding="utf-8",
    )


def test_continuation_filters_duplicates_against_frozen_baseline(tmp_path, monkeypatch):
    spec = RepositorySpec("apache/lucene", "https://github.com/apache/lucene.git")
    write_baseline(tmp_path, spec, complete_history=False)

    def fake_mine(config):
        assert config.skip_commits == 5
        samples = [make_sample("base1"), make_sample("new1", "fallback")]
        SampleWriter(config.output_dir).write_samples(
            samples,
            ExtractionStats(
                total_commits_scanned=12,
                candidate_samples_found=2,
                samples_retained=2,
                history_complete=True,
            ),
        )
        return samples

    monkeypatch.setattr("javadoc_miner.continuation.mine_repository", fake_mine)

    completed = mine_continuation_dataset(
        ContinuationConfig(
            root_dir=tmp_path,
            target_new=1,
        ),
        [spec],
    )

    assert completed[0]["duplicate_against_baseline"] == 1
    output_dir = tmp_path / "final_dataset_extra_3k"
    combined = json.loads((output_dir / "combined_samples.json").read_text(encoding="utf-8"))
    assert len(combined) == 1
    assert combined[0]["commit_hash"] == "new1"
    assert set(combined[0]) == {
        "commit_hash",
        "issue_summary",
        "code_before",
        "code_after",
        "javadoc_before",
        "javadoc_after",
    }
    validation = json.loads((output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert validation["duplicate_against_baseline_count"] == 0
    assert validation["passed"] is True
    with (output_dir / "summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["duplicate_against_baseline"] == "1"
    baseline = json.loads((tmp_path / "final_dataset" / "combined_samples.json").read_text())
    assert len(baseline) == 1


def test_continuation_plan_starts_from_first_incomplete_repository(tmp_path):
    completed = RepositorySpec("apache/commons-collections", "https://github.com/apache/commons-collections.git")
    incomplete = RepositorySpec("apache/lucene", "https://github.com/apache/lucene.git")
    write_baseline(tmp_path, completed, complete_history=True)

    incomplete_dir = tmp_path / "final_dataset" / incomplete.slug
    incomplete_dir.mkdir(parents=True)
    (incomplete_dir / "combined_samples.json").write_text("[]", encoding="utf-8")
    (incomplete_dir / "metadata.json").write_text(
        json.dumps({"complete_history": False}),
        encoding="utf-8",
    )

    plan = build_continuation_plan(
        ContinuationConfig(root_dir=tmp_path, target_new=3000),
        [completed, incomplete],
    )

    assert plan.baseline_count == 1
    assert plan.completed_repositories == [completed.name]
    assert plan.repositories_to_scan == [incomplete.name]
