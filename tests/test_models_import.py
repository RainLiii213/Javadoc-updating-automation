from pathlib import Path

from javadoc_miner.config import MinerConfig
from javadoc_miner.models import OutputSample


def test_config_has_research_defaults():
    config = MinerConfig(repo_url="https://github.com/apache/commons-lang")

    assert config.cache_dir == Path(".cache/repos")
    assert config.output_dir == Path("dataset")
    assert config.max_commits == 1000
    assert config.max_samples == 100
    assert config.full_history is False
    assert config.min_quality == "B"


def test_output_sample_serializes_required_fields():
    sample = OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        issue="LANG-1234",
        issues=["LANG-1234"],
        entity_type="method",
        entity_name="getFullName",
        old_javadoc="/** Returns the display name. */",
        new_javadoc="/** Returns the full display name. */",
        patch="diff --git a/A.java b/A.java",
        commit_message="LANG-1234 rename method",
        change_type="method_rename",
        quality="A",
    )

    assert sample.to_json_dict()["quality"] == "A"
    assert sample.to_json_dict()["entity_name"] == "getFullName"
