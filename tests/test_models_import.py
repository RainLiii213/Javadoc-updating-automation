from pathlib import Path

from javadoc_miner.config import MinerConfig
from javadoc_miner.models import Classification, ExtractionStats, OutputSample


def test_config_has_research_defaults():
    config = MinerConfig(repo_url="https://github.com/apache/commons-lang")

    assert config.cache_dir == Path(".cache/repos")
    assert config.output_dir == Path("dataset")
    assert config.max_commits == 1000
    assert config.max_samples == 50
    assert config.full_history is False
    assert config.min_quality == "C"


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
        quality="A",
        issue_id="LANG-1234",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        entity_type="method",
    )

    assert sample.to_json_dict()["quality"] == "A"
    assert sample.to_json_dict()["entity_name"] == "getFullName"
    assert sample.to_json_dict()["javadoc_change_type"] == "JAVADOC_MODIFICATION"
    assert "issues" not in sample.to_json_dict()
    assert "old_javadoc" not in sample.to_json_dict()
    assert "new_javadoc" not in sample.to_json_dict()
    assert "patch" not in sample.to_json_dict()


def test_extraction_stats_reports_required_dataset_metrics():
    stats = ExtractionStats(
        total_commits_scanned=10,
        total_commits_containing_javadoc_changes=4,
        target_a_samples=40,
        target_b_samples=5,
        target_c_samples=5,
    )
    stats.record(
        Classification(
            change_type="parameter_change",
            quality="A",
            javadoc_change_type="JAVADOC_MODIFICATION",
            method_change_type="METHOD_MODIFICATION",
        )
    )
    stats.record(
        Classification(
            change_type="method_addition",
            quality="B",
            javadoc_change_type="JAVADOC_ADDITION",
            method_change_type="METHOD_ADDITION",
        )
    )
    stats.finalize()

    data = stats.to_json_dict()

    assert data["total_commits_scanned"] == 10
    assert data["total_commits_containing_javadoc_changes"] == 4
    assert data["total_samples_generated"] == 2
    assert data["quality_distribution"] == {"A": 1, "B": 1, "C": 0}
    assert data["method_change_distribution"] == {
        "METHOD_ADDITION": 1,
        "METHOD_MODIFICATION": 1,
        "METHOD_DELETION": 0,
    }
    assert data["javadoc_change_distribution"] == {
        "JAVADOC_ADDITION": 1,
        "JAVADOC_MODIFICATION": 1,
        "JAVADOC_DELETION": 0,
    }
    assert data["a_sample_yield"] == 0.1
    assert data["a_sample_density"] == 0.5
    assert data["a_sample_shortfall"] == 39
    assert "a_sample_shortfall_reason" in data
