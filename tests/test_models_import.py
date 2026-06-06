from pathlib import Path

from javadoc_miner.config import MinerConfig
from javadoc_miner.models import OutputSample


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
