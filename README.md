# High-Quality Javadoc Evolution Dataset Mining Pipeline

This project builds a high-precision dataset for **Patch-Aware Javadoc
Updating**.

```text
Input:  issue_summary, code_before, code_after, javadoc_before
Output: javadoc_after
```

Precision is more important than recall. A sample is retained only when a
reviewer can clearly explain why meaningful code evolution required the
Javadoc update.

## Final Sample Schema

Every final sample contains exactly six fields:

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

Repository identity, source URLs, mining statistics, and completion state live
in directory-level metadata rather than sample objects.

## Retention Policy

The pipeline retains only updates to existing method/class Javadocs that are
logically connected to meaningful code evolution, such as behavior, exception,
nullability, return value, parameter handling, edge-case, or API contract
changes.

It rejects:

- Javadoc creation or deletion and code deletion.
- Field-level changes.
- Formatting, whitespace, wrapping, HTML-only, spelling-only, and
  punctuation-only edits.
- Version, date, author, link-only, and weak `inheritDoc`-only edits.
- Variable-only renames, code reordering, import-only changes, and other code
  changes without meaningful behavior or contract impact.
- Unclosed comments/Javadocs/strings, unbalanced braces, placeholders,
  incomplete statements, arbitrary truncation, and unrelated whole-file
  context.

The project does not use legacy A/B/C quality grading. Samples either pass the
strict retention gate or are filtered out.

## Code Context Policy

Method-level `code_before` and `code_after` contain complete methods or
constructors. Class-level samples contain a structurally complete class context
or complete relevant member region.

The pipeline does not convert samples to minimal diff hunks and does not
truncate by a fixed number of characters or lines. Long but structurally valid
and relevant contexts may enter the final dataset. Unsafe contexts are
discarded or kept in source-specific review output, never promoted to
`final_dataset`.

## Issue Summary Policy

Issue extraction is tied to the current commit. If the extracted summary is
empty, truncated, or ends with a dangling word such as `by`, `to`, `for`,
`with`, `of`, `in`, `on`, `and`, `or`, `from`, or `into`, the commit-message
subject is used as the fallback.

## Current Dataset

The validated final dataset currently contains **2,000 samples**:

| Project | Samples | History state |
| --- | ---: | --- |
| Apache Commons Lang | 37 | complete |
| Apache Commons IO | 39 | retained reviewed baseline |
| Apache Commons Collections | 72 | complete |
| Apache Commons Text | 35 | complete |
| Apache Commons Compress | 181 | complete |
| Apache Commons Codec | 41 | complete |
| Apache Commons Math | 561 | complete |
| Google Guava | 291 | complete |
| Joda-Time | 125 | complete |
| Apache Lucene | 618 | stopped when cumulative target reached |

Lucene metadata has `complete_history: false` because mining stopped once the
cumulative dataset reached 2,000 samples. Jackson Databind, Spring Data
Commons, and JUnit 5 were not scanned in this continuation because the target
had already been reached.

## Merged Commit-Level Dataset

The accepted baseline in `final_dataset/` and the continuation dataset in
`final_dataset_extra_3k/` have been merged locally into
`final_dataset_merged/`.

The merge keeps the original source datasets intact and writes source backups
under `final_dataset_merged/source_backups/`. The merged output is grouped as
`commit -> changes`, where each commit object preserves `project_slug`,
`repository_url`, `commit_hash`, one `issue_summary`, and a non-empty `changes`
array. Each change has:

```json
{
  "change_index": 1,
  "entity_type": "method",
  "code_before": "...",
  "code_after": "...",
  "javadoc_before": "...",
  "javadoc_after": "..."
}
```

Current merged counts:

| Metric | Count |
| --- | ---: |
| Old baseline flat changes | 2,000 |
| New continuation flat changes | 1,621 |
| Raw merged flat changes | 3,621 |
| Removed duplicate changes | 29 |
| Removed format-only Javadoc changes | 0 |
| Weak issue summaries detected | 34 |
| Weak issue summaries resolved from real history | 33 |
| Weak issue summaries unresolved | 1 |
| Final commits | 2,570 |
| Final method-level changes | 2,294 |
| Final class-level changes | 1,297 |
| Final changes | 3,591 |

The merge only removes exact content duplicates and pure formatting-only
Javadoc edits. It does not classify or judge whether a patch semantically
caused the Javadoc change. Weak issue summaries are repaired only from real
issue/PR/commit text available in project history; the merge script does not
generate or paraphrase summaries.

Re-run the local merge and validation with:

```powershell
python scripts/merge_and_clean_datasets.py `
  --old-dir final_dataset `
  --new-dir final_dataset_extra_3k `
  --output-dir final_dataset_merged
```

The merged delivery files are:

- `final_dataset_merged/combined_raw_flat.json`
- `final_dataset_merged/combined_cleaned_flat.json`
- `final_dataset_merged/combined_by_commit.json`
- `final_dataset_merged/removed_duplicates.json`
- `final_dataset_merged/removed_format_only.json`
- `final_dataset_merged/unresolved_issue_summary.json`
- `final_dataset_merged/summary.json`
- `final_dataset_merged/summary.csv`
- `final_dataset_merged/validation_report.json`

## No-Cap Recovery Dataset

An audit found that older mining code kept at most three changes per commit.
The cap has been removed from `javadoc_miner/cli.py`; sample selection now
deduplicates by exact content over `code_before`, `code_after`,
`javadoc_before`, and `javadoc_after`, without limiting how many distinct
method/class changes a commit can contribute.

Before changing the pipeline, the previous merged output was copied to:

```text
backups/before_remove_commit_cap/final_dataset_merged/
```

The no-cap recovery did not rescan full histories. It only reprocessed the 304
target commits listed in `analysis/commits_to_reprocess_without_cap.json`,
starting from `analysis/commits_with_exactly_3_changes.json`.

Independent recovery output:

- `recovery_without_commit_cap/target_commits.json`
- `recovery_without_commit_cap/recovered_raw_flat.json`
- `recovery_without_commit_cap/recovered_cleaned_flat.json`
- `recovery_without_commit_cap/recovered_by_commit.json`
- `recovery_without_commit_cap/recovered_duplicates.json`
- `recovery_without_commit_cap/recovered_format_only.json`
- `recovery_without_commit_cap/reprocess_failures.json`
- `recovery_without_commit_cap/summary.json`

Final no-cap merged output:

- `final_dataset_merged_no_commit_cap/combined_cleaned_flat.json`
- `final_dataset_merged_no_commit_cap/combined_by_commit.json`
- `final_dataset_merged_no_commit_cap/newly_recovered_changes.json`
- `final_dataset_merged_no_commit_cap/removed_duplicates.json`
- `final_dataset_merged_no_commit_cap/removed_format_only.json`
- `final_dataset_merged_no_commit_cap/unresolved_reprocess_commits.json`
- `final_dataset_merged_no_commit_cap/summary.json`
- `final_dataset_merged_no_commit_cap/summary.csv`
- `final_dataset_merged_no_commit_cap/validation_report.json`

No-cap recovery counts:

| Metric | Count |
| --- | ---: |
| Target commits reprocessed | 304 |
| Original merged changes | 3,591 |
| Raw reprocessed changes | 3,890 |
| Newly recovered non-duplicate changes | 2,995 |
| Final no-cap commits | 2,570 |
| Final no-cap changes | 6,586 |
| Method-level changes | 4,545 |
| Class-level changes | 2,041 |
| Commits with more than 3 changes | 274 |
| Max changes in one commit | 111 |
| Unresolved reprocess commits | 0 |

Validation passed for `final_dataset_merged_no_commit_cap/combined_by_commit.json`.
The audit examples now contain 46, 24, and 93 changes respectively for
`apache_commons_compress/86c20cdc037a8a3b73927b2ad51f0f9e844ba5f8`,
`apache_commons_io/8b6d4969ffb55bf7301a44a8156f02b0213e6d68`, and
`jodaorg_joda_time/0e07ac6b2cff63550d7df336355ca63cc05aa40b`.

## Run Single-Repository Mining

```powershell
python -m javadoc_miner mine `
  --repo-url https://github.com/apache/commons-lang.git `
  --full-history `
  --max-samples 50 `
  --output-dir dataset_apache_commons_lang_50
```

The output directory is replaced on every run.

## Run Multi-Repository Mining

Always validate the workflow with a bounded run first:

```powershell
python -m javadoc_miner mine-multiple `
  --max-commits-per-repo 50 `
  --max-repos 1
```

Preview the plan without mining:

```powershell
python -m javadoc_miner mine-multiple --dry-run --max-commits-per-repo 50
```

Continue from existing outputs toward a cumulative target:

```powershell
python -m javadoc_miner mine-multiple --resume --target-total 2000
```

Useful options:

- `--start-from apache/lucene`: start at a named repository.
- `--max-commits-per-repo N`: bounded development run; never promoted to the
  final dataset.
- `--max-repos N`: limit how many repositories are attempted.
- `--resume`: skip repositories whose full history is already complete.
- `--dry-run`: show the plan without writing or cloning.
- `--force-refresh`: refresh repository caches.

## Repository Priority

1. `apache/commons-collections`
2. `apache/commons-text`
3. `apache/commons-compress`
4. `apache/commons-codec`
5. `apache/commons-math`
6. `google/guava`
7. `JodaOrg/joda-time`
8. `apache/lucene`
9. `FasterXML/jackson-databind`
10. `spring-projects/spring-data-commons`
11. `junit-team/junit5`

## Output Structure

```text
dataset_<project_slug>_<count>/       # source-specific temporary output, Git-ignored
  sample_*.json
  combined_samples.json
  summary.csv
  stats.json
  metadata.json
  review_samples.json

final_dataset/                        # validated delivery dataset
  <project_slug>/
    sample_*.json
    combined_samples.json
    summary.csv
    stats.json
    metadata.json
  combined_samples.json               # all retained samples
  summary.csv                         # project-level mining statistics
  validation_report.json
  README.md
```

`review_samples.json` remains only in source-specific temporary folders. It is
never copied into `final_dataset`.

## Verification

```powershell
python -m compileall javadoc_miner
python -m pytest -v
```

Final validation checks the exact six-field schema, repository-aware duplicate
keys, dangling issue summaries, unclosed Javadocs/comments/strings, balanced
braces, and the absence of review files in `final_dataset`.

## Current Limitations

- Only Java/Javadoc is supported.
- Parsing and semantic linkage use conservative heuristics rather than a
  complete Java compiler or language model.
- High precision intentionally discards some valid but ambiguous samples.
- Repository histories are expensive to scan; target-limited repositories can
  be resumed later when a larger cumulative target is selected.
