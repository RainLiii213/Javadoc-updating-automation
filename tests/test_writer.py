import csv
import json

from javadoc_miner.models import OutputSample
from javadoc_miner.writer import SampleWriter


def make_sample(name="getFullName"):
    return OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        issue="LANG-1234",
        issues=["LANG-1234"],
        entity_type="method",
        entity_name=name,
        old_javadoc="/** Returns name. */",
        new_javadoc="/** Returns full name. */",
        patch="diff --git a/A.java b/A.java",
        commit_message="LANG-1234 rename method",
        change_type="method_rename",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        quality="A",
    )


def test_writer_creates_json_and_summary_csv(tmp_path):
    writer = SampleWriter(tmp_path)
    writer.write_samples([make_sample()])

    sample_path = tmp_path / "sample_0001.json"
    summary_path = tmp_path / "summary.csv"

    assert json.loads(sample_path.read_text(encoding="utf-8"))["entity_name"] == "getFullName"

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["sample_id"] == "sample_0001"
    assert rows[0]["javadoc_change_type"] == "JAVADOC_MODIFICATION"
    assert rows[0]["method_change_type"] == "METHOD_MODIFICATION"
    assert rows[0]["quality"] == "A"
