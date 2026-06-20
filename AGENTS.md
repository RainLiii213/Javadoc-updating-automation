# AGENTS.md

## Project Overview

This repository is used for a long-term research project: **Patch-Aware Javadoc Updating Dataset**.

The project was originally derived from a Javadoc evolution mining tool and has been refactored into a research-oriented dataset construction pipeline.

The task is **not**:

* Javadoc generation from scratch;
* Javadoc classification;
* Javadoc relevance classification;
* patch-Javadoc relation classification as the final task.

The actual research task is:

**Patch-Aware Javadoc Updating**

For each dataset sample, the model input is:

* `issue_summary`
* `code_before`
* `code_after`
* `javadoc_before`

The model target output is:

* `javadoc_after`

The goal is to train or evaluate models that update outdated Javadocs according to code evolution and issue/commit intent.

## Final Dataset Schema

Every final sample must use exactly the following six fields:

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

Do not add legacy or auxiliary fields to the final training dataset.

Do not include fields such as:

* `quality`
* `entity_type`
* `entity_name`
* `entity_signature`
* `method_change_type`
* `javadoc_change_type`
* `repository`
* `project`
* `file_path`
* `relation_category`

If extra analysis metadata is needed, store it in a separate analysis file, not in the final dataset samples.

## Previous Work

A previous dataset of approximately 2000 high-quality samples has already been mined and reviewed by the advisor.

The advisor considered the 2k dataset quality acceptable.

Treat the previous 2k dataset as a frozen baseline.

Do not modify, overwrite, regenerate, or weaken the accepted 2k dataset.

It may only be used for:

1. deduplication;
2. checking which repositories have already been scanned;
3. understanding previous output structure;
4. generating high-level summaries if needed.

New continuation datasets should be saved separately.

Recommended structure:

```text
final_dataset/                     # old accepted 2k baseline, keep frozen
final_dataset_extra_3k/             # new continuation samples only
final_dataset_all_2k_plus_extra/     # optional merged view, if useful
```

Do not replace the old baseline with a merged file unless the old baseline is also preserved.

## Dataset Quality Policy

High precision is more important than recall.

Only retain samples where:

1. there is a meaningful code change;
2. there is a meaningful Javadoc semantic change;
3. the code change and Javadoc change are clearly connected;
4. the Javadoc existed before and was updated, not newly created from nothing;
5. `code_before` and `code_after` provide enough context to explain the Javadoc update.

Discard samples with:

* Javadoc creation only;
* Javadoc deletion;
* code deletion;
* empty `code_before` or `code_after`;
* empty `javadoc_before` or `javadoc_after`;
* formatting-only Javadoc changes;
* line wrapping only;
* spelling-only changes;
* punctuation-only changes;
* HTML tag-only changes;
* version number-only changes;
* weak `inheritDoc`-only changes;
* weak or unrelated issue summaries;
* arbitrary truncated code;
* broken code snippets;
* unclosed Javadoc comments;
* unclosed block comments;
* code ending in the middle of a method, class, comment, string, or statement;
* noisy whole-file context unrelated to the Javadoc update.

Do not loosen filters just to reach a numeric target.

## Context Extraction Policy

Use the accepted context-aware extraction policy from the previous high-quality dataset.

Do not use the earlier failed minimal-code conversion approach.

### Method-level samples

For method-level or constructor-level samples:

* `code_before` and `code_after` should contain the complete method or constructor before and after.
* Do not keep only the method signature.
* Do not keep broken minimal diff hunks.
* Do not truncate methods by character count or line count.

### Class-level samples

For class-level samples:

* `code_before` and `code_after` should contain structurally complete class-level context or a complete relevant member region.
* If the full class is reasonably sized, keep the complete class.
* If the full class is too large, extract a structurally complete relevant member region.
* If the class-level context is too long or too noisy and cannot be safely reduced, discard the sample.

### Long code handling

Length alone should not automatically reject a sample.

Long but structurally complete and semantically relevant snippets may be retained.

However, never hard-truncate code.

Prefer discarding a sample over saving broken or misleading context.

## Sample Granularity

The dataset is **not commit-level**.

The dataset is **Javadoc-entity-level**.

One updated Javadoc entity corresponds to one sample.

If one commit updates five methods and five corresponding Javadocs, that commit may produce five samples.

Those samples may share the same `commit_hash` and `issue_summary`, but they must have different:

* `code_before`
* `code_after`
* `javadoc_before`
* `javadoc_after`

This is expected and should not be treated as duplicate data.

## Deduplication Policy

Do not deduplicate only by `commit_hash` or `issue_summary`.

Deduplicate by a stable full key such as:

* repository or project slug;
* `commit_hash`;
* `code_before`;
* `code_after`;
* `javadoc_before`;
* `javadoc_after`.

When mining additional data, also deduplicate against the old accepted 2k baseline so that the continuation dataset contains only new additional samples.

## Issue Summary Policy

`issue_summary` should describe the modification intent.

If the issue summary is empty, weak, truncated, or ends with dangling words such as:

```text
by, to, for, with, of, in, on, and, or, from, into
```

then fall back to the commit message subject.

If neither issue summary nor commit message is useful, discard the sample rather than keeping a misleading one.

## Relationship Between Issue, Code Change, and Javadoc Update

The `issue_summary` provides the modification intent.

The `code_before` and `code_after` provide the actual code evolution.

The `javadoc_before` provides the old documentation context.

The `javadoc_after` should reflect how the API documentation changes according to the code evolution and issue intent.

Useful relation categories include:

1. exception contract update;
2. parameter constraint update;
3. deprecation update;
4. behavior update;
5. return value update;
6. supported feature or mode update;
7. generic/type parameter update;
8. usage/example update;
9. resource/lifecycle update.

These categories may be recorded in a separate analysis file if useful, but they must not be added to the final six-field dataset schema.

## Java Repository Scope

The full Java repository list used for mining is:

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

Previously mined seed projects may include:

* `apache/commons-lang`
* `apache/commons-io`

When continuing mining, inspect existing summary files and metadata to determine which repositories are completed, partially completed, or not yet scanned.

## Output Organization

For new continuation mining, do not mix new samples into the frozen old baseline.

Use a separate output area such as:

```text
final_dataset_extra_3k/
```

Recommended files:

```text
final_dataset_extra_3k/<project_slug>/
final_dataset_extra_3k/combined_samples.json
final_dataset_extra_3k/summary.csv
final_dataset_extra_3k/README.md
```

Optional analysis files may be placed under:

```text
analysis/
```

or:

```text
final_dataset_extra_3k/analysis/
```

## Validation Rules

Before writing any new sample to a final dataset, validate that:

1. all required six fields exist;
2. no legacy fields exist;
3. all six fields are non-empty;
4. JSON is valid;
5. code snippets are not obviously truncated;
6. Javadoc comments are closed;
7. `code_before` and `code_after` are not identical;
8. `javadoc_before` and `javadoc_after` are not identical after whitespace normalization;
9. the sample is not a duplicate of the old baseline;
10. the sample is not a duplicate inside the new continuation dataset.

Before large mining runs, execute:

```bash
python -m compileall javadoc_miner
```

If tests exist, run the full test suite.

## Reporting Requirements

After each repository mining run, report:

* repository name;
* whether it was skipped, partially resumed, or newly scanned;
* commits scanned;
* candidate samples found;
* retained high-quality samples;
* discarded samples;
* duplicate count against old baseline;
* duplicate count inside the new dataset;
* invalid/truncated code count;
* weak `inheritDoc`-only discard count;
* issue summary fallback count;
* new continuation dataset count so far;
* optional total combined count if old and new samples are merged.

After a full continuation run stops, report:

* stop reason;
* old baseline count;
* new additional sample count;
* optional combined total count;
* per-project counts for the new continuation dataset;
* projects scanned in this stage;
* projects skipped because already completed;
* projects with unusually low yield;
* generated file paths;
* known limitations.

## Important Warnings

Do not use malformed minimal-diff data.

Do not keep signature-only code snippets.

Do not hard-truncate code snippets.

Do not weaken filters to hit a target count.

Do not change the six-field final schema.

Keep the old accepted 2k dataset frozen.

Save new continuation data separately.

Make all mining runs resume-friendly so that rerunning after interruption does not duplicate samples.
