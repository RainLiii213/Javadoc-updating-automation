from pathlib import Path

from javadoc_miner.config import MinerConfig
from javadoc_miner.models import ExtractionStats, OutputSample


def test_config_has_research_defaults():
    config = MinerConfig(repo_url="https://github.com/apache/commons-lang")

    assert config.cache_dir == Path(".cache/repos")
    assert config.output_dir == Path("dataset")
    assert config.max_commits == 1000
    assert config.max_samples == 50
    assert config.full_history is False


def test_output_sample_serializes_required_fields():
    sample = OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_message="LANG-1234 rename method",
        issue_summary="Rename method",
        code_before="public String getName() { return name; }",
        code_after="public String getFullName() { return fullName; }",
        javadoc_before="/** Returns the display name. */",
        javadoc_after="/** Returns the full display name. */",
        entity_name="getFullName",
        entity_signature="public String getFullName()",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        issue_id="LANG-1234",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        entity_type="method",
    )

    assert set(sample.to_json_dict()) == {
        "commit_hash",
        "issue_summary",
        "code_before",
        "code_after",
        "javadoc_before",
        "javadoc_after",
    }


def test_extraction_stats_reports_required_dataset_metrics():
    stats = ExtractionStats(
        total_commits_scanned=10,
        total_commits_containing_javadoc_changes=4,
        total_commits_containing_code_and_javadoc_changes=3,
        candidate_samples_found=7,
        samples_retained=5,
        samples_filtered=2,
    )

    data = stats.to_json_dict()

    assert data["total_commits_scanned"] == 10
    assert data["total_commits_containing_javadoc_changes"] == 4
    assert data["total_commits_containing_code_and_javadoc_changes"] == 3
    assert data["candidate_samples_found"] == 7
    assert data["samples_retained"] == 5
    assert data["samples_filtered"] == 2
