# Recovery Without Commit Cap

This directory contains the independent recovery pass for commits that had
exactly three changes in `final_dataset_merged`.

The pass reprocesses only the target commits listed in
`target_commits.json`; it does not scan full repository histories.

## Counts

- Target commits: 304
- Raw reprocessed changes: 3890
- New recovered changes after content dedupe: 2995
- Duplicates with existing merged dataset: 877
- Duplicates inside recovery: 18
- Format-only removed: 202
- Failed or partially failed commits: 0

## Files

- `target_commits.json`
- `recovered_raw_flat.json`
- `recovered_cleaned_flat.json`
- `recovered_by_commit.json`
- `recovered_duplicates.json`
- `recovered_format_only.json`
- `reprocess_failures.json`
- `target_reports.json`
- `summary.json`
- `summary.csv`
