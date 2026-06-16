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
