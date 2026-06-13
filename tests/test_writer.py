import csv
import json

from javadoc_miner.models import OutputSample
from javadoc_miner.writer import SampleWriter


def make_sample(name="getFullName"):
    return OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_message="LANG-1234 rename method",
        issue_summary="Rename getter",
        code_before="public String getName() { return name; }",
        code_after="public String getFullName() { return fullName; }",
        javadoc_before="/** Returns name. */",
        javadoc_after="/** Returns full name. */",
        entity_name=name,
        entity_signature="public String getFullName()",
        javadoc_change_type="JAVADOC_MODIFICATION",
        method_change_type="METHOD_MODIFICATION",
        issue_id="LANG-1234",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        entity_type="method",
        file_path="src/main/java/org/example/Person.java",
    )


def test_writer_creates_json_and_summary_csv(tmp_path):
    writer = SampleWriter(tmp_path)
    stale_path = tmp_path / "stale.json"
    stale_path.write_text("stale", encoding="utf-8")
    writer.write_samples([make_sample()])

    sample_path = tmp_path / "sample_0001.json"
    summary_path = tmp_path / "summary.csv"

    sample_data = json.loads(sample_path.read_text(encoding="utf-8"))
    assert set(sample_data) == {
        "commit_hash",
        "issue_summary",
        "code_before",
        "code_after",
        "javadoc_before",
        "javadoc_after",
    }
    assert not stale_path.exists()

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["sample_id"] == "sample_0001"
    assert rows[0]["file_path"] == "src/main/java/org/example/Person.java"
    assert rows[0]["entity_type"] == "method"
    assert rows[0]["javadoc_change_type"] == "JAVADOC_MODIFICATION"
    assert rows[0]["method_change_type"] == "METHOD_MODIFICATION"
    assert "quality" not in rows[0]
    combined = json.loads((tmp_path / "combined_samples.json").read_text(encoding="utf-8"))
    assert combined == [sample_data]
