# Max Changes Per Commit Audit

## Final Conclusion

Confirmed. The project currently has an explicit per-commit cap of 3 samples in the mining stage. The cap is not introduced by the final merge/grouping script; it is applied before per-project output files are written, so both the old 2k baseline and the new 1621-sample continuation can already be capped before merging.

## Code Evidence

- `javadoc_miner/cli.py:55`: `MAX_SAMPLES_PER_COMMIT = 3`. Stage: configuration constant for candidate/sample selection.
- `javadoc_miner/cli.py:196`: `selected_candidates = _deduplicate_samples(candidate_samples)`. Stage: candidate collection -> high-quality sample build; cap applied before writing output.
- `javadoc_miner/cli.py:389`: `if key in seen or per_commit.get(sample.commit_hash, 0) >= MAX_SAMPLES_PER_COMMIT: continue`. Stage: candidate de-duplication and per-commit cap.
- `tests/test_cli_integration.py:444`: `test_selection_caps_samples_per_commit_for_review_diversity asserts len(selected) == 3 for 5 same-commit samples`. Stage: test coverage confirms intentional cap behavior.

Additional checks found no per-commit cap in `scripts/merge_and_clean_datasets.py` or `javadoc_miner/writer.py`. The merge step groups all changes that are already present; it does not slice `changes` to 3.

## Stage Assessment

- raw_candidates: Not persisted by the miner. candidate_samples is held in memory inside javadoc_miner.cli.mine_repository.
- pre_cap_candidate_collection: javadoc_miner/cli.py collects all PendingOutputSample objects in candidate_samples before selected_candidates is assigned.
- cap_stage: javadoc_miner/cli.py:_deduplicate_samples applies MAX_SAMPLES_PER_COMMIT before _build_output_samples and SampleWriter.write_samples.
- retained_samples: Per-project dataset_*/combined_samples.json already contains capped samples.
- review_samples: SampleWriter review_samples.json receives only samples that survived _deduplicate_samples; fourth and later per-commit samples never reach review.
- per_project_output: Already capped at source-specific dataset directories and final_dataset/final_dataset_extra_3k project directories.
- old_combined_dataset: Already capped because baseline was generated through the same cli.py selection path.
- new_combined_dataset: Already capped because continuation mine_repository uses the same cli.py selection path.
- cleaned_flat_dataset: No additional cap; it loads already capped flat samples.
- final_commit_grouped_dataset: No additional cap; it groups whatever changes are present after source mining and merge cleaning.

## Final Dataset Distribution

- commit_count: 2570
- total_change_count: 3591
- min_changes_per_commit: 1
- max_changes_per_commit: 3
- commits_with_1_change: 1853
- commits_with_2_changes: 413
- commits_with_3_changes: 304
- commits_with_more_than_3_changes: 0

Source flat distributions before the final merge:
- old_final_dataset_combined_samples: {'1': 1000, '2': 212, '3': 192}
- new_final_dataset_extra_3k_combined_samples: {'1': 870, '2': 203, '3': 115}

## Real Git Sampling

Sampled commits: 30 total: 10 method-majority, 10 class-majority, and 10 mixed method/class commits.
Available exactly-3 populations: 171 method-majority, 53 class-majority, 80 mixed.
Sampled commits with retained fourth-or-later changes missing from final output: 14.
Largest sampled actual retainable count without the cap: 53.

Examples with missing fourth-or-later changes:
- `apache_commons_compress` `86c20cdc037a8a3b73927b2ad51f0f9e844ba5f8`: final=3, actual_retain_without_cap=15, missing=12, final_types={'method': 3}.
- `apache_lucene` `a43843701d9dbf790f9104a2ce1f6f38e98e8370`: final=3, actual_retain_without_cap=4, missing=1, final_types={'method': 3}.
- `apache_commons_lang` `4369537d8b1387b94a1126a36a4fc400a35d35cc`: final=3, actual_retain_without_cap=4, missing=1, final_types={'method': 3}.
- `apache_commons_codec` `9f1b740a17f0d54366edfb45df0636b8e302666a`: final=3, actual_retain_without_cap=5, missing=2, final_types={'class': 3}.
- `apache_commons_io` `8b6d4969ffb55bf7301a44a8156f02b0213e6d68`: final=3, actual_retain_without_cap=19, missing=16, final_types={'class': 3}.
- `apache_commons_collections` `e585cd0433ae4cfbc56e58572b9869bd0c86b611`: final=3, actual_retain_without_cap=7, missing=4, final_types={'class': 3}.
- `apache_lucene` `c13216934c58870b487a9bd04b2fd4ea24431000`: final=3, actual_retain_without_cap=4, missing=1, final_types={'class': 3}.
- `junit_team_junit5` `2196d97edc152c2b0a8dda2d6ddffe66ab516d81`: final=3, actual_retain_without_cap=6, missing=3, final_types={'class': 3}.
- `google_guava` `2b98d3c1e96b750dc997c29f283084aeb72fb3cf`: final=3, actual_retain_without_cap=4, missing=1, final_types={'class': 3}.
- `apache_lucene` `c429f437f08cd5ea95351232b9c51104607cbda5`: final=3, actual_retain_without_cap=4, missing=1, final_types={'class': 3}.
- `apache_commons_collections` `f4693f0adf5c9994127890877d018c4ba7bbca06`: final=3, actual_retain_without_cap=4, missing=1, final_types={'method': 2, 'class': 1}.
- `apache_lucene` `d3cfba9b29511279b79071ee8fe6ed1996a2af3c`: final=3, actual_retain_without_cap=6, missing=3, final_types={'class': 1, 'method': 2}.

Maximum example: `jodaorg_joda_time` `0e07ac6b2cff63550d7df336355ca63cc05aa40b` had final=3 but actual_retain_without_cap=53.

## Impact

The cap affects method-level and class-level changes together because the counter is keyed only by `sample.commit_hash`, not by entity type. The fourth and later retained candidates are silently skipped by `_deduplicate_samples`; they do not reach review files or per-project combined JSON.

Potentially affected commits visible in the final dataset: 304 commits with exactly 3 retained changes. This is a risk/lower-bound set; only a no-cap reprocess or saved pre-cap candidate logs can determine the exact affected count.

## Recommended Minimal Fix Plan

- Remove or make configurable MAX_SAMPLES_PER_COMMIT in javadoc_miner/cli.py.
- Add tests where one commit contains 5 method changes and where one commit contains mixed method/class changes >3.
- Incrementally reprocess commits that currently have exactly 3 retained changes, plus any source stats/logs indicating candidate_samples per commit >3 if available.
- Merge newly discovered fourth-and-later changes into final_dataset_merged through the existing content fingerprint deduplication path, preserving the existing 3591 changes.

Suggested tests: one commit with 5 method changes must retain 5; one commit with 4 method changes plus 2 class changes must retain 6; commit grouping must preserve all changes and assign continuous `change_index` values.

## Audit Files

- `analysis/max_changes_per_commit_audit.json`
- `analysis/max_changes_per_commit_sample_audit.json`
- `analysis/commits_with_exactly_3_changes.json`
