import csv
import json

from javadoc_miner.models import ExtractionStats, OutputSample
from javadoc_miner.writer import SampleWriter


def make_sample(name="getFullName"):
    return OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_message="LANG-1234 rename method",
        issue_summary="Rename getter",
        code_before="public String getName() {\n    return name;\n}",
        code_after="public String getFullName() {\n    return fullName;\n}",
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
    assert json.loads((tmp_path / "review_samples.json").read_text(encoding="utf-8")) == []


def test_writer_rejects_unfinished_method_and_moves_invalid_class_to_review(tmp_path):
    method = make_sample("method")
    method = OutputSample(
        **{**method.__dict__, "code_after": "throw new UnsupportedOperationException("}
    )
    class_sample = make_sample("class")
    class_sample = OutputSample(
        **{
            **class_sample.__dict__,
            "entity_type": "class",
            "code_before": "public class Names {",
            "code_after": "public class Names {\n// ... relevant changed context ...",
        }
    )

    stats = ExtractionStats(candidate_samples_found=2)
    retained = SampleWriter(tmp_path).write_samples([method, class_sample], stats)

    assert retained == []
    assert json.loads((tmp_path / "combined_samples.json").read_text(encoding="utf-8")) == []
    review = json.loads((tmp_path / "review_samples.json").read_text(encoding="utf-8"))
    assert len(review) == 1
    assert review[0]["review_reason"].startswith("invalid_class_context:")
    assert stats.discarded_truncated_code_context == 1
    assert stats.moved_to_review == 1
    assert stats.samples_retained == 0
