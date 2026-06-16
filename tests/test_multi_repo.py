import csv
import json

from javadoc_miner.models import ExtractionStats, OutputSample
from javadoc_miner.multi_repo import (
    MultiRepoConfig,
    mine_multiple_repositories,
    refresh_final_dataset,
)
from javadoc_miner.repositories import DEFAULT_JAVA_REPOSITORIES, RepositorySpec
from javadoc_miner.writer import SampleWriter


def make_sample(repo: str, commit_hash: str) -> OutputSample:
    return OutputSample(
        repo=repo,
        commit_hash=commit_hash,
        commit_message="Handle null values",
        issue_summary="Handle null values",
        code_before="public String normalize(String value) {\n    return Objects.requireNonNull(value);\n}",
        code_after="public String normalize(String value) {\n    return value == null ? EMPTY : value;\n}",
        javadoc_before="/** Null values are not allowed. */",
        javadoc_after="/** Null values produce an empty value. */",
        entity_name="normalize",
        entity_signature="String normalize(String value)",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        issue_id="",
        commit_url="",
        entity_type="method",
        file_path="src/main/java/example/Names.java",
    )


def test_default_java_repository_priority_order():
    assert [spec.name for spec in DEFAULT_JAVA_REPOSITORIES] == [
        "apache/commons-collections",
        "apache/commons-text",
        "apache/commons-compress",
        "apache/commons-codec",
        "apache/commons-math",
        "google/guava",
        "JodaOrg/joda-time",
        "apache/lucene",
        "FasterXML/jackson-databind",
        "spring-projects/spring-data-commons",
        "junit-team/junit5",
    ]
    assert DEFAULT_JAVA_REPOSITORIES[0].slug == "apache_commons_collections"


def test_multi_repository_mining_preserves_existing_and_writes_clean_aggregate(
    tmp_path,
    monkeypatch,
):
    final_dir = tmp_path / "final_dataset"
    commons_lang_dir = final_dir / "apache_commons_lang"
    SampleWriter(commons_lang_dir).write_samples([make_sample("apache/commons-lang", "lang1")])

    def fake_mine(config):
        samples = [make_sample("apache/commons-io", "io1")]
        stats = ExtractionStats(
            total_commits_scanned=10,
            candidate_samples_found=2,
            samples_retained=1,
            samples_filtered=1,
            history_complete=True,
        )
        SampleWriter(config.output_dir).write_samples(samples, stats)
        return samples

    monkeypatch.setattr("javadoc_miner.multi_repo.mine_repository", fake_mine)
    spec = RepositorySpec("apache/commons-io", "https://github.com/apache/commons-io.git")
    completed = mine_multiple_repositories(
        MultiRepoConfig(
            root_dir=tmp_path,
            final_dir=final_dir,
            cache_dir=tmp_path / "cache",
        ),
        [spec],
    )

    assert len(completed) == 1
    assert (tmp_path / "dataset_apache_commons_io_1" / "metadata.json").exists()
    assert (final_dir / "apache_commons_io" / "metadata.json").exists()
    metadata = json.loads(
        (final_dir / "apache_commons_io" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["complete_history"] is True
    assert metadata["stop_reason"] == "full_history_scanned"
    assert metadata["commits_scanned"] == 10

    combined = json.loads((final_dir / "combined_samples.json").read_text(encoding="utf-8"))
    assert len(combined) == 2
    assert all(
        set(sample)
        == {
            "commit_hash",
            "issue_summary",
            "code_before",
            "code_after",
            "javadoc_before",
            "javadoc_after",
        }
        for sample in combined
    )
    with (final_dir / "summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["project_slug"] for row in rows} == {
        "apache_commons_lang",
        "apache_commons_io",
    }


def test_bounded_run_stays_in_source_specific_folder(tmp_path, monkeypatch):
    def fake_mine(config):
        samples = [make_sample("apache/commons-io", "io1")]
        SampleWriter(config.output_dir).write_samples(samples, ExtractionStats(samples_retained=1))
        return samples

    monkeypatch.setattr("javadoc_miner.multi_repo.mine_repository", fake_mine)
    spec = RepositorySpec("apache/commons-io", "https://github.com/apache/commons-io.git")

    completed = mine_multiple_repositories(
        MultiRepoConfig(root_dir=tmp_path, max_commits_per_repo=10),
        [spec],
    )

    assert completed[0]["complete_history"] is False
    assert completed[0]["stop_reason"] == "max_commits_per_repo=10 reached"
    assert completed[0]["final_folder"] == ""
    assert (tmp_path / "dataset_apache_commons_io_1").exists()
    assert not (tmp_path / "final_dataset" / "apache_commons_io").exists()


def test_target_limited_run_records_stop_reason(tmp_path, monkeypatch):
    def fake_mine(config):
        samples = [make_sample("apache/lucene", "lucene1")]
        SampleWriter(config.output_dir).write_samples(
            samples,
            ExtractionStats(samples_retained=1, history_complete=False),
        )
        return samples

    monkeypatch.setattr("javadoc_miner.multi_repo.mine_repository", fake_mine)
    spec = RepositorySpec("apache/lucene", "https://github.com/apache/lucene.git")

    completed = mine_multiple_repositories(
        MultiRepoConfig(root_dir=tmp_path, target_total=1),
        [spec],
    )

    assert completed[0]["complete_history"] is False
    assert completed[0]["stop_reason"] == "target_total=1 reached"


def test_resume_remines_existing_incomplete_project(tmp_path, monkeypatch):
    final_project = tmp_path / "final_dataset" / "apache_commons_io"
    SampleWriter(final_project).write_samples([make_sample("apache/commons-io", "io1")])
    (final_project / "metadata.json").write_text(
        json.dumps({"complete_history": False}),
        encoding="utf-8",
    )

    def fake_mine(config):
        samples = [make_sample("apache/commons-io", "io2")]
        SampleWriter(config.output_dir).write_samples(
            samples,
            ExtractionStats(samples_retained=1, history_complete=True),
        )
        return samples

    monkeypatch.setattr("javadoc_miner.multi_repo.mine_repository", fake_mine)
    spec = RepositorySpec("apache/commons-io", "https://github.com/apache/commons-io.git")

    completed = mine_multiple_repositories(
        MultiRepoConfig(root_dir=tmp_path, resume=True),
        [spec],
    )

    assert len(completed) == 1
    assert len(json.loads((tmp_path / "final_dataset" / "combined_samples.json").read_text())) == 1
    metadata = json.loads((final_project / "metadata.json").read_text())
    assert metadata["complete_history"] is True
    assert json.loads((final_project / "combined_samples.json").read_text())[0]["commit_hash"] == "io2"


def test_refresh_final_dataset_deduplicates_within_project(tmp_path):
    project_dir = tmp_path / "final_dataset" / "apache_commons_io"
    project_dir.mkdir(parents=True)
    sample = make_sample("apache/commons-io", "io1").to_json_dict()
    (project_dir / "combined_samples.json").write_text(
        json.dumps([sample, sample]),
        encoding="utf-8",
    )

    refresh_final_dataset(tmp_path / "final_dataset")

    combined = json.loads((tmp_path / "final_dataset" / "combined_samples.json").read_text())
    assert combined == [sample]


def test_refresh_final_dataset_keeps_incomplete_history_stop_reason_consistent(tmp_path):
    project_dir = tmp_path / "final_dataset" / "apache_commons_io"
    SampleWriter(project_dir).write_samples([make_sample("apache/commons-io", "io1")])
    (project_dir / "metadata.json").write_text(
        json.dumps({"complete_history": False, "stop_reason": "full_history_scanned"}),
        encoding="utf-8",
    )

    refresh_final_dataset(tmp_path / "final_dataset")

    metadata = json.loads((project_dir / "metadata.json").read_text())
    assert metadata["complete_history"] is False
    assert metadata["stop_reason"] == "history_incomplete"


def test_dry_run_does_not_create_outputs(tmp_path):
    spec = RepositorySpec("apache/commons-io", "https://github.com/apache/commons-io.git")

    result = mine_multiple_repositories(
        MultiRepoConfig(root_dir=tmp_path, dry_run=True, max_commits_per_repo=5),
        [spec],
    )

    assert result == []
    assert not (tmp_path / "final_dataset").exists()
