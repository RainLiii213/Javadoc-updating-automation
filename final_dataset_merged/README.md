# Merged Patch-Aware Javadoc Updating Dataset

This directory contains the locally merged and cleaned Java dataset for the
Patch-Aware Javadoc Updating task.

Input fields for each change are `issue_summary`, `code_before`, `code_after`,
and `javadoc_before`. The target field is `javadoc_after`.

## Sources

- Old accepted baseline: `final_dataset` (2000 flat changes)
- New continuation dataset: `final_dataset_extra_3k` (1621 flat changes)

The source datasets are not overwritten. Key source files are copied under
`source_backups/` before the merged outputs are written.

## Cleaning Rules

- Deduplicate by content fingerprint over `code_before`, `code_after`,
  `javadoc_before`, and `javadoc_after`.
- Remove only pure Javadoc formatting changes: whitespace, line wrapping,
  punctuation-only, and HTML formatting-only changes.
- Do not judge whether the code patch caused the Javadoc edit.
- Keep both method-level and class-level changes.
- Weak `issue_summary` values are repaired only from real project history
  available in local git caches. They are not generated or paraphrased.

## Two-Level Schema

`combined_by_commit.json` is grouped by commit:

```json
[
  {
    "project_slug": "...",
    "repository_url": "...",
    "commit_hash": "...",
    "issue_summary": "...",
    "changes": [
      {
        "change_index": 1,
        "entity_type": "method",
        "code_before": "...",
        "code_after": "...",
        "javadoc_before": "...",
        "javadoc_after": "..."
      }
    ]
  }
]
```

`project_slug` and `repository_url` are preserved from the dataset directory
metadata so commits from different repositories cannot be accidentally merged.

## Final Counts

- Final commits: 2570
- Final changes: 3591
- Method-level changes: 2294
- Class-level changes: 1297
- Commits with multiple changes: 717
- Average changes per commit: 1.3973
- Max changes in one commit: 3

## Cleaning Statistics

- Merged raw changes: 3621
- Removed duplicate changes: 29
- Removed format-only changes: 0
- Weak issue summaries detected: 34
- Weak issue summaries resolved: 33
- Weak issue summaries unresolved: 1
- Entity-type review changes: 0
- Invalid changes: 0
- Validation passed: True

## Files

- `combined_raw_flat.json`
- `combined_cleaned_flat.json`
- `combined_by_commit.json`
- `removed_duplicates.json`
- `removed_format_only.json`
- `unresolved_issue_summary.json`
- `entity_type_review.json`
- `invalid_changes.json`
- `javadoc_format_review.json`
- `summary.json`
- `summary.csv`
- `validation_report.json`

## Re-run

```powershell
python scripts/merge_and_clean_datasets.py `
  --old-dir final_dataset `
  --new-dir final_dataset_extra_3k `
  --output-dir final_dataset_merged
```
