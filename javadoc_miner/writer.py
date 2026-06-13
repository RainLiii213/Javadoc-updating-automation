import csv
import json
import shutil
from pathlib import Path

from .models import ExtractionStats, OutputSample


SUMMARY_FIELDS = [
    "sample_id",
    "repo",
    "commit_hash",
    "file_path",
    "entity_type",
    "entity_name",
    "entity_signature",
    "javadoc_change_type",
    "method_change_type",
    "quality",
    "issue_id",
    "issue_summary",
]


class SampleWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def write_samples(self, samples: list[OutputSample], stats: ExtractionStats | None = None) -> None:
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        summary_rows: list[dict[str, str]] = []
        for index, sample in enumerate(samples, start=1):
            sample_id = f"sample_{index:04d}"
            sample_path = self.output_dir / f"{sample_id}.json"
            sample_path.write_text(
                json.dumps(sample.to_json_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary_rows.append(
                {
                    "sample_id": sample_id,
                    "repo": sample.repo,
                    "commit_hash": sample.commit_hash,
                    "file_path": sample.file_path,
                    "entity_type": sample.entity_type,
                    "entity_name": sample.entity_name,
                    "entity_signature": sample.entity_signature,
                    "javadoc_change_type": sample.javadoc_change_type,
                    "method_change_type": sample.method_change_type,
                    "quality": sample.quality,
                    "issue_id": sample.issue_id,
                    "issue_summary": sample.issue_summary,
                }
            )

        with (self.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            writer.writerows(summary_rows)

        if stats is not None:
            (self.output_dir / "stats.json").write_text(
                json.dumps(stats.to_json_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        (self.output_dir / "inspection_examples.json").write_text(
            json.dumps(_inspection_examples(samples), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "combined_samples.json").write_text(
            json.dumps([sample.to_json_dict() for sample in samples], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _inspection_examples(samples: list[OutputSample]) -> dict[str, list[dict[str, str]]]:
    examples: dict[str, list[dict[str, str]]] = {"A": [], "B": [], "C": []}
    for quality in ("A", "B", "C"):
        for sample in [sample for sample in samples if sample.quality == quality][:2]:
            examples[quality].append(
                {
                    "issue_summary": sample.issue_summary,
                    "code_before": sample.code_before,
                    "code_after": sample.code_after,
                    "javadoc_before": sample.javadoc_before,
                    "javadoc_after": sample.javadoc_after,
                }
            )
    return examples
