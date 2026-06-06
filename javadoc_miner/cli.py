import argparse
from pathlib import Path

from .classifier import classify_entity_change, quality_meets_threshold
from .config import MinerConfig
from .diff_extractor import (
    commit_has_javadoc_and_code_changes,
    commit_has_javadoc_changes,
    entity_code_changed,
    entity_code_text,
    extract_file_changes,
)
from .git_repo import GitCommandError, GitRepo
from .issue_finder import find_issues, resolve_issue_summary
from .java_parser import parse_entities
from .models import Classification, EntityDoc, ExtractionStats, FileChange, OutputSample
from .writer import SampleWriter


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "mine":
        parser.print_help()
        return 1

    config = MinerConfig(
        repo_url=args.repo_url,
        cache_dir=args.cache_dir,
        output_dir=args.output_dir,
        max_commits=args.max_commits,
        max_samples=args.max_samples,
        full_history=args.full_history,
        min_quality=args.min_quality,
        force_refresh=args.force_refresh,
        target_a_samples=args.target_a,
        target_b_samples=args.target_b,
        target_c_samples=args.target_c,
    )
    samples = mine_repository(config)
    print(f"Wrote {len(samples)} samples to {config.output_dir}")
    return 0


def mine_repository(config: MinerConfig) -> list[OutputSample]:
    repo = GitRepo.clone_or_update(config.repo_url, config.cache_dir, config.force_refresh)
    samples: list[OutputSample] = []
    scanned = 0
    javadoc_commits = 0
    code_and_javadoc_commits = 0

    for commit_hash in repo.iter_commits(config.full_history, config.max_commits):
        scanned += 1
        try:
            patch = repo.show_commit_patch(commit_hash)
        except GitCommandError:
            continue
        if not commit_has_javadoc_changes(patch):
            continue
        javadoc_commits += 1
        if commit_has_javadoc_and_code_changes(patch):
            code_and_javadoc_commits += 1
        try:
            file_changes = extract_file_changes(repo, commit_hash)
            commit_message = repo.commit_message(commit_hash)
        except GitCommandError:
            continue

        issues = find_issues(f"{commit_message}\n{patch}")
        issue_summary = resolve_issue_summary(repo.repo_url, issues, commit_message)
        for file_change in file_changes:
            old_entities = parse_entities(file_change.old_content or "")
            new_entities = parse_entities(file_change.new_content or "")
            for old_entity, new_entity, classification in _classify_file_entities(
                old_entities,
                new_entities,
                config.min_quality,
                file_change,
            ):
                samples.append(
                    _build_output_sample(
                        repo=repo,
                        commit_hash=commit_hash,
                        commit_message=commit_message,
                        issue_id=issues[0] if issues else "",
                        issue_summary=issue_summary,
                        file_change=file_change,
                        old_entity=old_entity,
                        new_entity=new_entity,
                        classification=classification,
                    )
                )

    samples, shortfall = _select_target_distribution(samples, config)
    stats = _stats_for_samples(scanned, javadoc_commits, samples, config)
    SampleWriter(config.output_dir).write_samples(samples, stats)
    print(
        f"Scanned {scanned} commits, found {javadoc_commits} commits with JavaDoc changes "
        f"({code_and_javadoc_commits} also changed code)."
    )
    print(
        "Stats: "
        f"samples={stats.total_samples_extracted}, "
        f"A={stats.quality_a_samples}, "
        f"B={stats.quality_b_samples}, "
        f"C={stats.quality_c_samples}, "
        f"javadoc_additions={stats.javadoc_additions}, "
        f"javadoc_modifications={stats.javadoc_modifications}, "
        f"javadoc_deletions={stats.javadoc_deletions}, "
        f"method_additions={stats.method_additions}, "
        f"method_modifications={stats.method_modifications}, "
        f"method_deletions={stats.method_deletions}, "
        f"A_sample_yield={stats.a_sample_yield:.2%}, "
        f"A_sample_density={stats.a_sample_density:.2%}"
    )
    if shortfall:
        print(f"Warning: requested {config.target_a_samples} A samples but found {stats.quality_a_samples}.")
    return samples


def _classify_file_entities(
    old_entities: list[EntityDoc],
    new_entities: list[EntityDoc],
    min_quality: str,
    file_change: FileChange | None = None,
) -> list[tuple[EntityDoc | None, EntityDoc | None, Classification]]:
    results: list[tuple[EntityDoc | None, EntityDoc | None, Classification]] = []
    matched_old: set[int] = set()
    matched_new: set[int] = set()

    for new_index, new_entity in enumerate(new_entities):
        old_index = _find_exact_entity(old_entities, new_entity, matched_old)
        if old_index is None:
            continue
        matched_old.add(old_index)
        matched_new.add(new_index)
        old_entity = old_entities[old_index] if old_index is not None else None
        classification = classify_entity_change(
            old_entity,
            new_entity,
            nearby_code_changed=_entity_code_changed(file_change, old_entity, new_entity),
        )
        if classification is None:
            continue
        if not quality_meets_threshold(classification.quality, min_quality):
            continue
        results.append((old_entity, new_entity, classification))

    for new_index, new_entity in enumerate(new_entities):
        if new_index in matched_new:
            continue
        old_index = _find_parameter_change_candidate(old_entities, new_entity, matched_old)
        if old_index is None:
            old_index = _find_rename_candidate(old_entities, new_entity, matched_old)
        old_entity = old_entities[old_index] if old_index is not None else None
        classification = classify_entity_change(
            old_entity,
            new_entity,
            nearby_code_changed=_entity_code_changed(file_change, old_entity, new_entity),
        )
        if classification is None:
            continue
        if not quality_meets_threshold(classification.quality, min_quality):
            continue
        if old_index is not None:
            matched_old.add(old_index)
            matched_new.add(new_index)
        results.append((old_entity, new_entity, classification))

    for old_index, old_entity in enumerate(old_entities):
        if old_index in matched_old:
            continue
        classification = classify_entity_change(
            old_entity,
            None,
            nearby_code_changed=_entity_code_changed(file_change, old_entity, None),
        )
        if classification is None:
            continue
        if not quality_meets_threshold(classification.quality, min_quality):
            continue
        results.append((old_entity, None, classification))
    return results


def _find_exact_entity(
    old_entities: list[EntityDoc],
    new_entity: EntityDoc,
    matched_old: set[int],
) -> int | None:
    for index, old_entity in enumerate(old_entities):
        if index in matched_old:
            continue
        if old_entity.entity_type != new_entity.entity_type:
            continue
        if old_entity.name != new_entity.name:
            continue
        if old_entity.entity_type == "method":
            if old_entity.parameters != new_entity.parameters:
                continue
        return index
    return None


def _find_parameter_change_candidate(
    old_entities: list[EntityDoc],
    new_entity: EntityDoc,
    matched_old: set[int],
) -> int | None:
    for index, old_entity in enumerate(old_entities):
        if index in matched_old:
            continue
        if old_entity.entity_type != new_entity.entity_type:
            continue
        if old_entity.name != new_entity.name:
            continue
        return index
    return None


def _find_rename_candidate(
    old_entities: list[EntityDoc],
    new_entity: EntityDoc,
    matched_old: set[int],
) -> int | None:
    for index, old_entity in enumerate(old_entities):
        if index in matched_old:
            continue
        if old_entity.entity_type != new_entity.entity_type:
            continue
        if old_entity.entity_type == "method":
            if old_entity.return_type == new_entity.return_type and old_entity.parameters == new_entity.parameters:
                return index
        elif old_entity.entity_type == "class":
            return index
    return None


def _build_output_sample(
    repo: GitRepo,
    commit_hash: str,
    commit_message: str,
    issue_id: str,
    issue_summary: str,
    file_change: FileChange,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
    classification: Classification,
) -> OutputSample:
    entity = new_entity or old_entity
    if entity is None:
        raise ValueError("Output sample requires an old or new entity.")
    return OutputSample(
        repo=repo.repo_name(),
        commit_hash=commit_hash,
        commit_message=commit_message,
        issue_summary=issue_summary,
        code_before=entity_code_text(file_change.old_content, old_entity),
        code_after=entity_code_text(file_change.new_content, new_entity),
        javadoc_before=old_entity.javadoc if old_entity else "",
        javadoc_after=new_entity.javadoc if new_entity else "",
        entity_name=entity.name,
        entity_signature=entity.signature,
        javadoc_change_type=classification.javadoc_change_type,
        method_change_type=classification.method_change_type,
        quality=classification.quality,
        issue_id=issue_id,
        commit_url=repo.commit_url(commit_hash),
        entity_type=entity.entity_type,
    )


def _entity_code_changed(
    file_change: FileChange | None,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
) -> bool:
    if file_change is None:
        return True
    return entity_code_changed(file_change, old_entity, new_entity)


def _prioritize_samples(samples: list[OutputSample]) -> list[OutputSample]:
    return sorted(samples, key=_sample_priority)


def _sample_priority(sample: OutputSample) -> tuple[int, int]:
    if (
        sample.method_change_type == "METHOD_MODIFICATION"
        and sample.javadoc_change_type == "JAVADOC_MODIFICATION"
    ):
        primary = 0
    elif sample.javadoc_change_type == "JAVADOC_MODIFICATION":
        primary = 1
    elif sample.javadoc_change_type == "JAVADOC_ADDITION":
        primary = 2
    else:
        primary = 3
    quality_rank = {"A": 0, "B": 1, "C": 2}.get(sample.quality, 3)
    return primary, quality_rank


def _select_target_distribution(
    samples: list[OutputSample],
    config: MinerConfig,
) -> tuple[list[OutputSample], bool]:
    prioritized = _prioritize_samples(samples)
    targets = {
        "A": config.target_a_samples,
        "B": config.target_b_samples,
        "C": config.target_c_samples,
    }
    selected: list[OutputSample] = []
    for quality in ("A", "B", "C"):
        bucket = [sample for sample in prioritized if sample.quality == quality]
        selected.extend(bucket[: targets[quality]])
    selected = selected[: config.max_samples]
    return selected, len([sample for sample in samples if sample.quality == "A"]) < config.target_a_samples


def _stats_for_samples(
    total_commits_processed: int,
    total_commits_containing_javadoc_changes: int,
    samples: list[OutputSample],
    config: MinerConfig,
) -> ExtractionStats:
    stats = ExtractionStats(
        total_commits_processed=total_commits_processed,
        total_commits_containing_javadoc_changes=total_commits_containing_javadoc_changes,
        target_a_samples=config.target_a_samples,
        target_b_samples=config.target_b_samples,
        target_c_samples=config.target_c_samples,
    )
    for sample in samples:
        stats.record(
            Classification(
                change_type="",
                quality=sample.quality,
                javadoc_change_type=sample.javadoc_change_type,
                method_change_type=sample.method_change_type,
            )
        )
    stats.finalize()
    return stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="javadoc_miner")
    subparsers = parser.add_subparsers(dest="command")
    mine = subparsers.add_parser("mine", help="Mine JavaDoc update samples from a repository.")
    mine.add_argument("--repo-url", required=True)
    mine.add_argument("--cache-dir", type=Path, default=Path(".cache/repos"))
    mine.add_argument("--output-dir", type=Path, default=Path("dataset"))
    mine.add_argument("--max-commits", type=int, default=1000)
    mine.add_argument("--max-samples", type=int, default=50)
    mine.add_argument("--full-history", action="store_true")
    mine.add_argument("--min-quality", choices=["A", "B", "C"], default="C")
    mine.add_argument("--force-refresh", action="store_true")
    mine.add_argument("--target-a", type=int, default=40)
    mine.add_argument("--target-b", type=int, default=5)
    mine.add_argument("--target-c", type=int, default=5)
    return parser
