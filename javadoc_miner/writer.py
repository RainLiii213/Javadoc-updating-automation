import csv
import json
import shutil
from pathlib import Path

from .models import OutputSample


SUMMARY_FIELDS = ["sample_id", "repo", "commit_hash", "entity_name", "change_type", "quality"]


class SampleWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def write_samples(self, samples: list[OutputSample]) -> None:
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
                    "entity_name": sample.entity_name,
                    "change_type": sample.change_type,
                    "quality": sample.quality,
                }
            )

        with (self.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            writer.writerows(summary_rows)
