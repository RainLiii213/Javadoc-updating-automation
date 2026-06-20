# Extra 3k Continuation Dataset

This directory stores only new Patch-Aware Javadoc Updating samples that are
not present in the frozen baseline at `final_dataset`.

Current new continuation sample count: **1621**.

Every training sample JSON object contains exactly six fields:

```json
{
  "commit_hash": "...",
  "issue_summary": "...",
  "code_before": "...",
  "code_after": "...",
  "javadoc_before": "...",
  "javadoc_after": "..."
}
```

The old baseline is not copied into this directory. Repository metadata and
duplicate counts are recorded separately in `summary.csv`, per-project
`metadata.json` files, and `validation_report.json`.

## Sources

- `apache_commons_io`: 136 samples
- `apache_lucene`: 911 samples
- `fasterxml_jackson_databind`: 215 samples
- `junit_team_junit5`: 174 samples
- `spring_projects_spring_data_commons`: 185 samples
