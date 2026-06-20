import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from .classifier import classify_entity_change
from .config import MinerConfig
from .diff_extractor import (
    bounded_entity_code_pair,
    commit_has_javadoc_and_code_changes,
    commit_has_javadoc_changes,
    entity_code_changed,
    entity_code_text,
    extract_file_changes,
)
from .git_repo import GitCommandError, GitRepo
from .issue_finder import commit_summary_with_fallback, find_issues
from .java_parser import parse_entities
from .models import Classification, EntityDoc, ExtractionStats, FileChange, OutputSample
from .text_utils import is_low_signal_commit_message
from .validation import validate_output_sample
from .writer import SampleWriter


@dataclass(frozen=True)
class PendingOutputSample:
    commit_hash: str
    commit_message: str
    issue_ids: list[str]
    file_change: FileChange
    old_entity: EntityDoc | None
    new_entity: EntityDoc | None
    classification: Classification

    @property
    def javadoc_change_type(self) -> str:
        return self.classification.javadoc_change_type

    @property
    def method_change_type(self) -> str:
        return self.classification.method_change_type

    @property
    def entity_name(self) -> str:
        entity = self.new_entity or self.old_entity
        return entity.name if entity else ""

    @property
    def entity_type(self) -> str:
        entity = self.new_entity or self.old_entity
        return entity.entity_type if entity else ""


SelectableSample = TypeVar("SelectableSample", OutputSample, PendingOutputSample)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "mine":
        config = MinerConfig(
            repo_url=args.repo_url,
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
            max_commits=args.max_commits,
            max_samples=args.max_samples,
            full_history=args.full_history,
            force_refresh=args.force_refresh,
            skip_commits=args.skip_commits,
            fetch_existing=not args.no_fetch_existing,
            progress_interval=args.progress_interval,
        )
        samples = mine_repository(config)
        print(f"Wrote {len(samples)} samples to {config.output_dir}")
        return 0
    if args.command == "mine-multiple":
        from .multi_repo import MultiRepoConfig, mine_multiple_repositories

        config = MultiRepoConfig(
            root_dir=args.root_dir,
            final_dir=args.final_dir,
            cache_dir=args.cache_dir,
            target_total=args.target_total,
            start_from=args.start_from,
            max_commits_per_repo=args.max_commits_per_repo,
            max_repos=args.max_repos,
            repo_list=args.repo_list,
            resume=args.resume,
            dry_run=args.dry_run,
            force_refresh=args.force_refresh,
        )
        try:
            mine_multiple_repositories(config)
        except ValueError as error:
            parser.error(str(error))
        return 0
    if args.command == "mine-continuation":
        from .continuation import ContinuationConfig, mine_continuation_dataset

        config = ContinuationConfig(
            root_dir=args.root_dir,
            baseline_dir=args.baseline_dir,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
            target_new=args.target_new,
            start_from=args.start_from,
            max_commits_per_repo=args.max_commits_per_repo,
            max_repos=args.max_repos,
            dry_run=args.dry_run,
            force_refresh=args.force_refresh,
        )
        try:
            mine_continuation_dataset(config)
        except (FileNotFoundError, ValueError) as error:
            parser.error(str(error))
        return 0
    parser.print_help()
    return 1


def mine_repository(config: MinerConfig) -> list[OutputSample]:
    repo = GitRepo.clone_or_update(
        config.repo_url,
        config.cache_dir,
        config.force_refresh,
        fetch_existing=config.fetch_existing,
    )
    commits = repo.iter_commits(config.full_history, config.max_commits)
    if config.skip_commits > 0:
        skipped = min(config.skip_commits, len(commits))
        print(f"Skipping {skipped} previously scanned commits.", flush=True)
        commits = commits[config.skip_commits :]
    candidate_samples: list[PendingOutputSample] = []
    scanned = 0
    javadoc_commits = 0
    code_and_javadoc_commits = 0
    next_validation_count = config.max_samples
    stopped_after_target = False

    for commit_hash in commits:
        scanned += 1
        if config.progress_interval and scanned % config.progress_interval == 0:
            print(
                f"Progress: scanned {scanned}/{len(commits)} commits after skip; "
                f"javadoc_commits={javadoc_commits}; "
                f"code_and_javadoc_commits={code_and_javadoc_commits}; "
                f"candidate_samples={len(candidate_samples)}; "
                f"unique_candidates={_unique_sample_count(candidate_samples)}",
                flush=True,
            )
        try:
            patch = repo.show_commit_patch(commit_hash)
        except GitCommandError:
            continue
        if not commit_has_javadoc_changes(patch):
            continue
        javadoc_commits += 1
        if not commit_has_javadoc_and_code_changes(patch):
            continue
        code_and_javadoc_commits += 1
        try:
            file_changes = extract_file_changes(repo, commit_hash)
            commit_message = repo.commit_message(commit_hash)
        except GitCommandError:
            continue
        if is_low_signal_commit_message(commit_message):
            continue

        issues = find_issues(commit_message)
        for file_change in file_changes:
            old_entities = parse_entities(file_change.old_content or "")
            new_entities = parse_entities(file_change.new_content or "")
            for old_entity, new_entity, classification in _classify_file_entities(
                old_entities,
                new_entities,
                file_change,
            ):
                candidate_samples.append(
                    PendingOutputSample(
                        commit_hash=commit_hash,
                        commit_message=commit_message,
                        issue_ids=issues,
                        file_change=file_change,
                        old_entity=old_entity,
                        new_entity=new_entity,
                        classification=classification,
                    )
                )
        unique_count = _unique_sample_count(candidate_samples)
        if unique_count >= next_validation_count:
            if _retained_candidate_count(repo, candidate_samples, config.max_samples) >= config.max_samples:
                stopped_after_target = True
                break
            next_validation_count = unique_count + 10
    selected_candidates = _deduplicate_samples(candidate_samples)
    samples = _build_output_samples(repo, selected_candidates)
    stats = _stats_for_samples(
        scanned,
        javadoc_commits,
        code_and_javadoc_commits,
        len(candidate_samples),
        0,
    )
    stats.history_complete = config.full_history and not stopped_after_target and scanned == len(commits)
    samples = SampleWriter(config.output_dir).write_samples(
        samples,
        stats,
        max_samples=config.max_samples,
    )
    print(
        f"Scanned {scanned} commits, found {javadoc_commits} commits with JavaDoc changes "
        f"({code_and_javadoc_commits} also changed code).",
        flush=True,
    )
    print(
        "Stats: "
        f"candidate_samples_found={stats.candidate_samples_found}, "
        f"samples_retained={stats.samples_retained}, "
        f"samples_filtered={stats.samples_filtered}, "
        f"discarded_truncated_code_context={stats.discarded_truncated_code_context}, "
        f"moved_to_review={stats.moved_to_review}, "
        f"discarded_weak_inheritdoc={stats.discarded_weak_inheritdoc}, "
        f"issue_summary_fallbacks={stats.issue_summary_fallbacks}",
        flush=True,
    )
    return samples


def _build_output_samples(repo: GitRepo, candidates: list[PendingOutputSample]) -> list[OutputSample]:
    samples: list[OutputSample] = []
    for candidate in candidates:
        issue_id = candidate.issue_ids[0] if candidate.issue_ids else ""
        issue_summary, fallback_applied = commit_summary_with_fallback(candidate.commit_message)
        samples.append(
            _build_output_sample(
                repo=repo,
                commit_hash=candidate.commit_hash,
                commit_message=candidate.commit_message,
                issue_id=issue_id,
                issue_summary=issue_summary,
                file_change=candidate.file_change,
                old_entity=candidate.old_entity,
                new_entity=candidate.new_entity,
                classification=candidate.classification,
                issue_summary_fallback_applied=fallback_applied,
            )
        )
    return samples


def _classify_file_entities(
    old_entities: list[EntityDoc],
    new_entities: list[EntityDoc],
    file_change: FileChange | None = None,
) -> list[tuple[EntityDoc | None, EntityDoc | None, Classification]]:
    results: list[tuple[EntityDoc | None, EntityDoc | None, Classification]] = []
    matched_old: set[int] = set()

    for new_entity in new_entities:
        old_index = _find_exact_entity(old_entities, new_entity, matched_old)
        if old_index is None:
            continue
        matched_old.add(old_index)
        old_entity = old_entities[old_index] if old_index is not None else None
        code_before, code_after = _entity_code_pair(file_change, old_entity, new_entity)
        classification = classify_entity_change(
            old_entity,
            new_entity,
            nearby_code_changed=_entity_code_changed(file_change, old_entity, new_entity),
            code_before=code_before,
            code_after=code_after,
        )
        if classification is None:
            continue
        results.append((old_entity, new_entity, classification))

    return results


def _find_exact_entity(
    old_entities: list[EntityDoc],
    new_entity: EntityDoc,
    matched_old: set[int],
) -> int | None:
    candidates: list[tuple[float, int, int]] = []
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
        doc_similarity = _entity_doc_similarity(old_entity, new_entity)
        line_distance = abs(old_entity.code_start_line - new_entity.code_start_line)
        candidates.append((doc_similarity, -line_distance, index))
    if not candidates:
        return None
    return max(candidates)[2]


def _entity_doc_similarity(old_entity: EntityDoc, new_entity: EntityDoc) -> float:
    from .text_utils import javadoc_similarity

    return javadoc_similarity(old_entity.javadoc, new_entity.javadoc)


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
    issue_summary_fallback_applied: bool = False,
) -> OutputSample:
    entity = new_entity or old_entity
    if entity is None:
        raise ValueError("Output sample requires an old or new entity.")
    if old_entity is None or new_entity is None:
        raise ValueError("Patch-aware update samples require both old and new entities.")
    code_before, code_after = bounded_entity_code_pair(file_change, old_entity, new_entity)
    return OutputSample(
        repo=repo.repo_name(),
        commit_hash=commit_hash,
        commit_message=commit_message,
        issue_summary=issue_summary,
        code_before=code_before,
        code_after=code_after,
        javadoc_before=old_entity.javadoc if old_entity else "",
        javadoc_after=new_entity.javadoc if new_entity else "",
        entity_name=entity.name,
        entity_signature=entity.signature,
        javadoc_change_type=classification.javadoc_change_type,
        method_change_type=classification.method_change_type,
        issue_id=issue_id,
        commit_url=repo.commit_url(commit_hash),
        entity_type=entity.entity_type,
        file_path=file_change.path,
        issue_summary_fallback_applied=issue_summary_fallback_applied,
    )


def _entity_code_changed(
    file_change: FileChange | None,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
) -> bool:
    if file_change is None:
        return True
    return entity_code_changed(file_change, old_entity, new_entity)


def _entity_code_pair(
    file_change: FileChange | None,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
) -> tuple[str, str]:
    if file_change is None:
        return (
            old_entity.signature if old_entity is not None else "",
            new_entity.signature if new_entity is not None else "",
        )
    return (
        entity_code_text(file_change.old_content, old_entity),
        entity_code_text(file_change.new_content, new_entity),
    )


def _select_samples(
    samples: list[SelectableSample],
    max_samples: int,
) -> list[SelectableSample]:
    return _deduplicate_samples(samples)[:max_samples]


def _deduplicate_samples(samples: list[SelectableSample]) -> list[SelectableSample]:
    unique: list[SelectableSample] = []
    seen: set[tuple[str, str, str, str]] = set()
    for sample in samples:
        key = _sample_content_key(sample)
        if key in seen:
            continue
        seen.add(key)
        unique.append(sample)
    return unique


def _sample_content_key(sample: OutputSample | PendingOutputSample) -> tuple[str, str, str, str]:
    if isinstance(sample, OutputSample):
        code_before = sample.code_before
        code_after = sample.code_after
        javadoc_before = sample.javadoc_before
        javadoc_after = sample.javadoc_after
    else:
        code_before, code_after = _entity_code_pair(sample.file_change, sample.old_entity, sample.new_entity)
        javadoc_before = sample.old_entity.javadoc if sample.old_entity is not None else ""
        javadoc_after = sample.new_entity.javadoc if sample.new_entity is not None else ""
    return (
        _normalize_sample_text(code_before),
        _normalize_sample_text(code_after),
        _normalize_sample_text(javadoc_before),
        _normalize_sample_text(javadoc_after),
    )


def _normalize_sample_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _unique_sample_count(samples: list[PendingOutputSample]) -> int:
    return len(_deduplicate_samples(samples))


def _retained_candidate_count(
    repo: GitRepo,
    candidates: list[PendingOutputSample],
    limit: int,
) -> int:
    retained = 0
    for sample in _build_output_samples(repo, _deduplicate_samples(candidates)):
        if validate_output_sample(sample).disposition == "retain":
            retained += 1
            if retained >= limit:
                return retained
    return retained


def _stats_for_samples(
    total_commits_scanned: int,
    total_commits_containing_javadoc_changes: int,
    total_commits_containing_code_and_javadoc_changes: int,
    candidate_samples_found: int,
    samples_retained: int,
) -> ExtractionStats:
    return ExtractionStats(
        total_commits_scanned=total_commits_scanned,
        total_commits_containing_javadoc_changes=total_commits_containing_javadoc_changes,
        total_commits_containing_code_and_javadoc_changes=total_commits_containing_code_and_javadoc_changes,
        candidate_samples_found=candidate_samples_found,
        samples_retained=samples_retained,
        samples_filtered=max(0, candidate_samples_found - samples_retained),
    )


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
    mine.add_argument("--force-refresh", action="store_true")
    mine.add_argument("--skip-commits", type=int, default=0)
    mine.add_argument("--no-fetch-existing", action="store_true")
    mine.add_argument("--progress-interval", type=int, default=0)

    multiple = subparsers.add_parser(
        "mine-multiple",
        help="Mine the configured Java repositories sequentially.",
    )
    multiple.add_argument("--root-dir", type=Path, default=Path("."))
    multiple.add_argument("--final-dir", type=Path, default=Path("final_dataset"))
    multiple.add_argument("--cache-dir", type=Path, default=Path(".cache/repos"))
    multiple.add_argument("--target-total", type=int, default=1000)
    multiple.add_argument("--start-from", default="")
    multiple.add_argument("--max-commits-per-repo", type=int)
    multiple.add_argument("--max-repos", type=int)
    multiple.add_argument("--repo-list", choices=["default_java"], default="default_java")
    multiple.add_argument("--resume", action="store_true")
    multiple.add_argument("--dry-run", action="store_true")
    multiple.add_argument("--force-refresh", action="store_true")

    continuation = subparsers.add_parser(
        "mine-continuation",
        help="Mine new continuation samples while preserving and deduplicating against a baseline.",
    )
    continuation.add_argument("--root-dir", type=Path, default=Path("."))
    continuation.add_argument("--baseline-dir", type=Path, default=Path("final_dataset"))
    continuation.add_argument("--output-dir", type=Path, default=Path("final_dataset_extra_3k"))
    continuation.add_argument("--cache-dir", type=Path, default=Path(".cache/repos"))
    continuation.add_argument("--target-new", type=int, default=3000)
    continuation.add_argument("--start-from", default="")
    continuation.add_argument("--max-commits-per-repo", type=int)
    continuation.add_argument("--max-repos", type=int)
    continuation.add_argument("--dry-run", action="store_true")
    continuation.add_argument("--force-refresh", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
