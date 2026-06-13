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
from .issue_finder import commit_summary, find_issues
from .java_parser import parse_entities
from .models import Classification, EntityDoc, ExtractionStats, FileChange, OutputSample
from .text_utils import is_low_signal_commit_message
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
MAX_SAMPLES_PER_COMMIT = 3


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
        force_refresh=args.force_refresh,
    )
    samples = mine_repository(config)
    print(f"Wrote {len(samples)} samples to {config.output_dir}")
    return 0


def mine_repository(config: MinerConfig) -> list[OutputSample]:
    repo = GitRepo.clone_or_update(config.repo_url, config.cache_dir, config.force_refresh)
    candidate_samples: list[PendingOutputSample] = []
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
        if _unique_sample_count(candidate_samples) >= config.max_samples:
            break

    selected_candidates = _select_samples(candidate_samples, config.max_samples)
    samples = _build_output_samples(repo, selected_candidates)
    stats = _stats_for_samples(
        scanned,
        javadoc_commits,
        code_and_javadoc_commits,
        len(candidate_samples),
        len(samples),
    )
    SampleWriter(config.output_dir).write_samples(samples, stats)
    print(
        f"Scanned {scanned} commits, found {javadoc_commits} commits with JavaDoc changes "
        f"({code_and_javadoc_commits} also changed code)."
    )
    print(
        "Stats: "
        f"candidate_samples_found={stats.candidate_samples_found}, "
        f"samples_retained={stats.samples_retained}, "
        f"samples_filtered={stats.samples_filtered}"
    )
    return samples


def _build_output_samples(repo: GitRepo, candidates: list[PendingOutputSample]) -> list[OutputSample]:
    samples: list[OutputSample] = []
    for candidate in candidates:
        issue_id = candidate.issue_ids[0] if candidate.issue_ids else ""
        issue_summary = commit_summary(candidate.commit_message)
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
    seen: set[tuple[str, str, str]] = set()
    per_commit: dict[str, int] = {}
    for sample in samples:
        key = (sample.commit_hash, sample.entity_type, sample.entity_name)
        if key in seen or per_commit.get(sample.commit_hash, 0) >= MAX_SAMPLES_PER_COMMIT:
            continue
        seen.add(key)
        per_commit[sample.commit_hash] = per_commit.get(sample.commit_hash, 0) + 1
        unique.append(sample)
    return unique


def _unique_sample_count(samples: list[PendingOutputSample]) -> int:
    return len(_deduplicate_samples(samples))


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
    return parser
