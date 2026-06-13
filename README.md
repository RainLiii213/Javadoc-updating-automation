# High-Quality Javadoc Evolution Dataset Mining Pipeline

This pipeline builds a high-precision dataset for **Patch-Aware Javadoc Updating**.
Precision is more important than recall: borderline samples are discarded.

The target task is:

```text
Input:  issue_summary, code_before, code_after, javadoc_before
Output: javadoc_after
```

Every retained sample must let a reviewer clearly explain why the code change
required the Javadoc update.

## Strict Retention Rules

A sample is retained only when all of these conditions hold:

1. The same existing method or class is present before and after the commit.
2. Existing Javadoc is modified; Javadoc creation and deletion are excluded.
3. Code changes are substantial, such as behavior, parameter handling,
   nullability, exceptions, return behavior, API contracts, or edge cases.
4. Javadoc changes are semantically meaningful.
5. Changed code terms and changed Javadoc terms have a clear direct or
   contract-level relationship.

The miner aggressively rejects:

- method/class additions and deletions;
- empty `code_after`, `javadoc_before`, or `javadoc_after`;
- field-level samples;
- formatting, whitespace, imports, reordering, and identifier-only renames;
- punctuation, HTML formatting, typo, capitalization, and tag-order edits;
- versions, issue IDs, dates, URLs, and only `@see/@since/@version/@author`;
- substantial code and documentation changes whose relationship is unclear.

Very high Javadoc similarity is treated as suspicious. Such a sample is kept
only when the changed terms expose a strong contract link, for example
`milliseconds`, `null`, an exception, or a changed parameter contract.

## Code Context

Method samples contain only the modified method. Class samples contain bounded
class declaration/change context. Large entities are cropped to at most about
100 lines around the relevant change rather than storing an entire source file.

## Installation

Requires Python 3.10+ and Git:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Generate Commons Lang Samples

```powershell
.\.venv\Scripts\python.exe -m javadoc_miner mine `
  --repo-url https://github.com/apache/commons-lang `
  --full-history `
  --max-samples 50 `
  --output-dir dataset_commons_lang_50 `
  --force-refresh
```

For development, use `--max-commits 3000` or `--max-commits 5000`.

The output directory is automatically deleted and recreated on every run, so
old dataset files cannot leak into a new result.

To avoid review clutter, repeated overloads are deduplicated: for one commit,
only one sample is retained for the same entity type and entity name, and each
commit contributes at most three samples. Mining stops after enough unique
high-confidence samples are found.

## Dataset Organization

Temporary mining outputs must identify their source and retained sample count:

```text
dataset_<source>_<count>/
```

For example, the current Apache Commons Lang result is stored as
`dataset_apache_commons_lang_37`.

Only manually reviewed, accepted samples belong in `final_dataset/`. Each
source has its own subdirectory, while `final_dataset/combined_samples.json`
aggregates all accepted samples for final delivery. This keeps future results
from other Java projects separate during review while supporting the long-term
goal of a 1,000+ sample final dataset.

## Output

```text
dataset_commons_lang_50/
  sample_0001.json
  sample_0002.json
  ...
  combined_samples.json
  summary.csv
  stats.json
```

Each `sample_*.json` and each item in `combined_samples.json` uses the final
review schema:

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

`combined_samples.json` puts all retained samples in one file for GPT or human
review. `summary.csv` and `stats.json` retain additional mining metadata for
local auditing. Statistics report commits scanned, candidate samples found,
samples retained, and samples filtered; the pipeline does not assign A/B/C
quality grades.

`issue_summary` always comes from the current commit message. Issue references
are not extracted from arbitrary patch text, preventing unrelated issue
summaries from being attached.

All output samples have passed the same strict high-confidence filters. The
miner may produce fewer than the requested `--max-samples`; this is intentional
when not enough suitable samples exist.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Tests cover creation/deletion rejection, rename/reordering rejection,
substantive code changes, meaningful Javadoc changes, logical connection,
bounded context, output replacement, and combined review output.

## Current Limitations

- Only Java/Javadoc is supported.
- Java parsing and semantic linkage are conservative heuristics, not a full AST
  or language-model analysis.
- Some valid samples are intentionally discarded when the relationship is not
  immediately clear.
- Python, C++, and larger 1k+ datasets are future work.
