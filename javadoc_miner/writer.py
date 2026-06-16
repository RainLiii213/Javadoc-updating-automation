import csv
import json
import shutil
from pathlib import Path

from .models import ExtractionStats, OutputSample
from .validation import validate_output_sample


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
    "issue_id",
    "issue_summary",
]


class SampleWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def write_samples(
        self,
        samples: list[OutputSample],
        stats: ExtractionStats | None = None,
        max_samples: int | None = None,
    ) -> list[OutputSample]:
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        retained: list[OutputSample] = []
        review_samples: list[dict] = []
        discarded_truncated = 0
        discarded_weak_inheritdoc = 0
        for sample in samples:
            validation = validate_output_sample(sample)
            if validation.disposition == "review":
                review_samples.append(
                    {
                        "review_reason": validation.reason,
                        **sample.to_json_dict(),
                    }
                )
                continue
            if validation.disposition == "discard":
                if validation.reason == "weak_inheritdoc_only":
                    discarded_weak_inheritdoc += 1
                elif validation.reason.startswith("truncated_code_context:"):
                    discarded_truncated += 1
                continue
            if max_samples is None or len(retained) < max_samples:
                retained.append(sample)

        summary_rows: list[dict[str, str]] = []
        for index, sample in enumerate(retained, start=1):
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
                    "issue_id": sample.issue_id,
                    "issue_summary": sample.issue_summary,
                }
            )

        with (self.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            writer.writerows(summary_rows)

        if stats is not None:
            stats.samples_retained = len(retained)
            stats.moved_to_review = len(review_samples)
            stats.discarded_truncated_code_context = discarded_truncated
            stats.discarded_weak_inheritdoc = discarded_weak_inheritdoc
            stats.issue_summary_fallbacks = sum(
                sample.issue_summary_fallback_applied for sample in retained
            )
            candidate_count = stats.candidate_samples_found or len(samples)
            stats.samples_filtered = max(
                0,
                candidate_count - len(retained) - len(review_samples),
            )
            (self.output_dir / "stats.json").write_text(
                json.dumps(stats.to_json_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        (self.output_dir / "review_samples.json").write_text(
            json.dumps(review_samples, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "combined_samples.json").write_text(
            json.dumps([sample.to_json_dict() for sample in retained], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return retained
