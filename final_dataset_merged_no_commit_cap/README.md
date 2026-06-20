# Merged Dataset Without Per-Commit Cap

This directory is a no-cap successor to `final_dataset_merged`.

The old merged dataset is preserved. The recovery pass only reprocessed target
commits that already had exactly three changes and added newly discovered
non-duplicate method/class Javadoc updates.

## Counts

- Original merged commits: 2570
- Original merged changes: 3591
- Target commits reprocessed: 304
- Raw reprocessed changes: 3890
- Newly recovered changes: 2995
- Final commits: 2570
- Final changes: 6586
- Commits with more than 3 changes: 274
- Max changes in one commit: 111
- Validation passed: True

## Files

- `combined_cleaned_flat.json`
- `combined_by_commit.json`
- `newly_recovered_changes.json`
- `removed_duplicates.json`
- `removed_format_only.json`
- `unresolved_reprocess_commits.json`
- `validation_report.json`
- `summary.json`
- `summary.csv`
