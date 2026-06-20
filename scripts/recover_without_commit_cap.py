import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from javadoc_miner.cli import _find_exact_entity
from javadoc_miner.diff_extractor import entity_code_changed, entity_code_text, extract_file_changes
from javadoc_miner.git_repo import GitCommandError, GitRepo
from javadoc_miner.java_parser import parse_entities
from javadoc_miner.models import EntityDoc, FileChange
from javadoc_miner.validation import is_weak_inheritdoc_only_change, validate_code_snippet
from scripts.merge_and_clean_datasets import (
    cache_name,
    content_fingerprint,
    format_only_reason,
    normalize_file_text,
    validate_grouped_dataset,
)


CHANGE_FIELDS = (
    "code_before",
    "code_after",
    "javadoc_before",
    "javadoc_after",
)
NON_CANDIDATE_REASONS = {
    "code_not_changed",
    "identical_code",
    "identical_javadoc",
    "empty_javadoc",
}
UNRESOLVED_REPROCESS_REASONS = {
    "missing_local_repo_cache",
    "git_extract_failed",
}


@dataclass(frozen=True)
class RecoveryPaths:
    root_dir: Path
    current_dir: Path
    cache_dir: Path
    target_source: Path
    target_output: Path
    recovery_dir: Path
    final_output_dir: Path
    git_timeout_seconds: int


class TimeoutGitRepo(GitRepo):
    def __init__(self, repo_url: str, path: Path, timeout_seconds: int):
        super().__init__(repo_url, path)
        self.timeout_seconds = timeout_seconds

    def run_git(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.path,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise GitCommandError(f"git command timed out after {self.timeout_seconds}s: {' '.join(args)}") from error
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise GitCommandError(message)
        return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recover extra Javadoc changes from commits affected by the old per-commit cap."
    )
    parser.add_argument("--root-dir", type=Path, default=Path("."))
    parser.add_argument("--current-dir", type=Path, default=Path("final_dataset_merged"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/repos"))
    parser.add_argument(
        "--target-source",
        type=Path,
        default=Path("analysis/commits_with_exactly_3_changes.json"),
    )
    parser.add_argument(
        "--target-output",
        type=Path,
        default=Path("analysis/commits_to_reprocess_without_cap.json"),
    )
    parser.add_argument("--recovery-dir", type=Path, default=Path("recovery_without_commit_cap"))
    parser.add_argument(
        "--final-output-dir",
        type=Path,
        default=Path("final_dataset_merged_no_commit_cap"),
    )
    parser.add_argument("--git-timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)

    paths = RecoveryPaths(
        root_dir=args.root_dir.resolve(),
        current_dir=_resolve(args.root_dir, args.current_dir),
        cache_dir=_resolve(args.root_dir, args.cache_dir),
        target_source=_resolve(args.root_dir, args.target_source),
        target_output=_resolve(args.root_dir, args.target_output),
        recovery_dir=_resolve(args.root_dir, args.recovery_dir),
        final_output_dir=_resolve(args.root_dir, args.final_output_dir),
        git_timeout_seconds=args.git_timeout_seconds,
    )
    recover_without_commit_cap(paths)
    return 0


def recover_without_commit_cap(paths: RecoveryPaths) -> dict:
    current_grouped = _read_json(paths.current_dir / "combined_by_commit.json", [])
    if not isinstance(current_grouped, list) or not current_grouped:
        raise ValueError(f"Current merged dataset not found: {paths.current_dir / 'combined_by_commit.json'}")

    targets = build_reprocess_targets(paths.target_source, current_grouped)
    _write_json(paths.target_output, targets)

    paths.recovery_dir.mkdir(parents=True, exist_ok=True)
    paths.final_output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.recovery_dir / "target_commits.json", targets)

    current_flat = flatten_grouped_changes(current_grouped, source_dataset="existing_merged")
    existing_fingerprints = {content_fingerprint(change) for change in current_flat}
    current_by_commit = {
        (commit.get("project_slug", ""), commit.get("commit_hash", "")): commit
        for commit in current_grouped
    }
    _configure_git_safe_directories(paths.cache_dir, targets)

    checkpoint = load_checkpoint(paths.recovery_dir)
    raw_recovered: list[dict] = checkpoint.get("raw_recovered", []) if isinstance(checkpoint, dict) else []
    removed_format_only: list[dict] = (
        checkpoint.get("removed_format_only", []) if isinstance(checkpoint, dict) else []
    )
    reprocess_failures: list[dict] = (
        checkpoint.get("reprocess_failures", []) if isinstance(checkpoint, dict) else []
    )
    target_reports: list[dict] = checkpoint.get("target_reports", []) if isinstance(checkpoint, dict) else []
    completed_targets = {
        (report.get("project_slug", ""), report.get("commit_hash", ""))
        for report in target_reports
        if isinstance(report, dict)
    }

    for target_index, target in enumerate(targets, start=1):
        target_key = (target.get("project_slug", ""), target.get("commit_hash", ""))
        if target_key in completed_targets:
            continue
        _write_json(
            paths.recovery_dir / "progress.json",
            {
                "status": "running",
                "target_index": target_index,
                "target_commit_count": len(targets),
                "target": target,
            },
        )
        report, changes = reprocess_target_commit(
            paths.cache_dir,
            target,
            current_by_commit,
            target_index,
            paths.git_timeout_seconds,
        )
        raw_recovered.extend(changes)
        removed_format_only.extend(report.pop("removed_format_only"))
        reprocess_failures.extend(report.pop("failures"))
        target_reports.append(report)
        completed_targets.add(target_key)
        if len(target_reports) % 10 == 0 or len(target_reports) == len(targets):
            write_checkpoint(
                paths.recovery_dir,
                {
                    "raw_recovered": raw_recovered,
                    "removed_format_only": removed_format_only,
                    "reprocess_failures": reprocess_failures,
                    "target_reports": target_reports,
                },
            )

    cleaned_recovered, duplicate_groups = deduplicate_recovered_changes(
        raw_recovered,
        existing_fingerprints,
    )
    recovered_by_commit = group_flat_changes(cleaned_recovered)

    _write_json(paths.recovery_dir / "recovered_raw_flat.json", strip_recovery_internal(raw_recovered))
    _write_json(paths.recovery_dir / "recovered_cleaned_flat.json", strip_recovery_internal(cleaned_recovered))
    _write_json(paths.recovery_dir / "recovered_by_commit.json", recovered_by_commit)
    _write_json(paths.recovery_dir / "recovered_duplicates.json", duplicate_groups)
    _write_json(paths.recovery_dir / "recovered_format_only.json", removed_format_only)
    _write_json(paths.recovery_dir / "reprocess_failures.json", reprocess_failures)
    _write_json(paths.recovery_dir / "target_reports.json", target_reports)

    final_result = merge_recovered_changes(
        current_grouped=current_grouped,
        recovered_changes=cleaned_recovered,
    )
    final_grouped = final_result["grouped"]
    final_flat = final_result["flat"]
    validation = validate_grouped_dataset(final_grouped)
    unresolved_reprocess_commits = unresolved_commits_from_failures(reprocess_failures)

    final_summary = build_final_summary(
        targets=targets,
        target_reports=target_reports,
        current_grouped=current_grouped,
        current_flat=current_flat,
        raw_recovered=raw_recovered,
        cleaned_recovered=cleaned_recovered,
        duplicate_groups=duplicate_groups,
        removed_format_only=removed_format_only,
        reprocess_failures=reprocess_failures,
        final_grouped=final_grouped,
        validation=validation,
    )
    recovery_summary = build_recovery_summary(
        targets=targets,
        target_reports=target_reports,
        raw_recovered=raw_recovered,
        cleaned_recovered=cleaned_recovered,
        duplicate_groups=duplicate_groups,
        removed_format_only=removed_format_only,
        reprocess_failures=reprocess_failures,
    )

    _write_json(paths.recovery_dir / "summary.json", recovery_summary)
    _write_summary_csv(paths.recovery_dir / "summary.csv", recovery_summary)
    (paths.recovery_dir / "README.md").write_text(
        render_recovery_readme(recovery_summary),
        encoding="utf-8",
    )

    _write_json(paths.final_output_dir / "combined_cleaned_flat.json", strip_final_flat(final_flat))
    _write_json(paths.final_output_dir / "combined_by_commit.json", final_grouped)
    _write_json(
        paths.final_output_dir / "newly_recovered_changes.json",
        strip_recovery_internal(cleaned_recovered),
    )
    _write_json(paths.final_output_dir / "removed_duplicates.json", duplicate_groups)
    _write_json(paths.final_output_dir / "removed_format_only.json", removed_format_only)
    _write_json(paths.final_output_dir / "unresolved_reprocess_commits.json", unresolved_reprocess_commits)
    _write_json(paths.final_output_dir / "validation_report.json", validation)
    _write_json(paths.final_output_dir / "summary.json", final_summary)
    _write_summary_csv(paths.final_output_dir / "summary.csv", final_summary)
    (paths.final_output_dir / "README.md").write_text(
        render_final_readme(final_summary),
        encoding="utf-8",
    )
    _write_json(
        paths.recovery_dir / "progress.json",
        {
            "status": "complete",
            "target_commit_count": len(targets),
            "completed_target_count": len(target_reports),
        },
    )
    return final_summary


def build_reprocess_targets(target_source: Path, current_grouped: list[dict]) -> list[dict]:
    raw_targets = _read_json(target_source, [])
    if not isinstance(raw_targets, list):
        raise ValueError(f"Invalid target source: {target_source}")
    current_counts = {
        (commit.get("project_slug", ""), commit.get("commit_hash", "")): len(commit.get("changes", []))
        for commit in current_grouped
    }
    targets: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        key = (item.get("project_slug", ""), item.get("commit_hash", ""))
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "project_slug": item.get("project_slug", ""),
                "repository_url": item.get("repository_url", ""),
                "commit_hash": item.get("commit_hash", ""),
                "issue_summary": item.get("issue_summary", ""),
                "current_change_count": current_counts.get(key, item.get("change_count", 0)),
                "target_reason": "current_merged_change_count_is_3",
            }
        )
    return targets


def reprocess_target_commit(
    cache_dir: Path,
    target: dict,
    current_by_commit: dict[tuple[str, str], dict],
    target_index: int,
    git_timeout_seconds: int,
) -> tuple[dict, list[dict]]:
    project_slug = target["project_slug"]
    repository_url = target["repository_url"]
    commit_hash = target["commit_hash"]
    repo_dir = cache_dir / cache_name(repository_url)
    commit_key = (project_slug, commit_hash)
    current_commit = current_by_commit.get(commit_key, {})
    issue_summary = current_commit.get("issue_summary") or target.get("issue_summary", "")
    report = {
        "project_slug": project_slug,
        "repository_url": repository_url,
        "commit_hash": commit_hash,
        "current_change_count": target.get("current_change_count", 0),
        "raw_reprocessed_change_count": 0,
        "retained_raw_change_count": 0,
        "removed_format_only_count": 0,
        "invalid_candidate_count": 0,
        "weak_inheritdoc_only_count": 0,
        "removed_format_only": [],
        "failures": [],
    }
    if not repo_dir.exists():
        report["failures"].append(_commit_failure(target, "missing_local_repo_cache"))
        return report, []

    repo = TimeoutGitRepo(repository_url, repo_dir, git_timeout_seconds)
    try:
        file_changes = extract_file_changes(repo, commit_hash)
    except GitCommandError as error:
        report["failures"].append(_commit_failure(target, "git_extract_failed", str(error)))
        return report, []

    changes: list[dict] = []
    for file_change in file_changes:
        for change, reason in recover_file_change_entities(
            file_change=file_change,
            target=target,
            issue_summary=issue_summary,
            source_order_seed=target_index,
        ):
            if change is not None:
                report["raw_reprocessed_change_count"] += 1
                changes.append(change)
                continue
            if reason == "format_only_javadoc":
                report["removed_format_only_count"] += 1
                report["removed_format_only"].append(_candidate_failure(target, file_change.path, reason))
            elif reason == "weak_inheritdoc_only":
                report["weak_inheritdoc_only_count"] += 1
                report["failures"].append(_candidate_failure(target, file_change.path, reason))
            else:
                report["invalid_candidate_count"] += 1
                report["failures"].append(_candidate_failure(target, file_change.path, reason))

    report["retained_raw_change_count"] = len(changes)
    return report, changes


def recover_file_change_entities(
    file_change: FileChange,
    target: dict,
    issue_summary: str,
    source_order_seed: int,
) -> list[tuple[dict | None, str]]:
    if file_change.old_content is None or file_change.new_content is None:
        return []
    old_entities = parse_entities(file_change.old_content)
    new_entities = parse_entities(file_change.new_content)
    matched_old: set[int] = set()
    results: list[tuple[dict | None, str]] = []

    for new_entity in new_entities:
        old_index = _find_exact_entity(old_entities, new_entity, matched_old)
        if old_index is None:
            continue
        matched_old.add(old_index)
        old_entity = old_entities[old_index]
        if old_entity.entity_type not in {"method", "class"} or new_entity.entity_type not in {"method", "class"}:
            continue
        result = build_recovered_change(
            file_change=file_change,
            old_entity=old_entity,
            new_entity=new_entity,
            target=target,
            issue_summary=issue_summary,
            source_order=source_order_seed * 100000 + len(results),
        )
        if result is not None:
            results.append((result, ""))
        else:
            reason = rejection_reason(file_change, old_entity, new_entity)
            if reason and reason not in NON_CANDIDATE_REASONS:
                results.append((None, reason))
    return results


def build_recovered_change(
    file_change: FileChange,
    old_entity: EntityDoc,
    new_entity: EntityDoc,
    target: dict,
    issue_summary: str,
    source_order: int,
) -> dict | None:
    reason = rejection_reason(file_change, old_entity, new_entity)
    if reason:
        return None
    code_before = normalize_file_text(entity_code_text(file_change.old_content, old_entity))
    code_after = normalize_file_text(entity_code_text(file_change.new_content, new_entity))
    return {
        "project_slug": target["project_slug"],
        "repository_url": target["repository_url"],
        "commit_hash": target["commit_hash"],
        "issue_summary": issue_summary,
        "entity_type": new_entity.entity_type,
        "entity_name": new_entity.name,
        "entity_signature": new_entity.signature,
        "file_path": file_change.path,
        "code_before": code_before,
        "code_after": code_after,
        "javadoc_before": normalize_file_text(old_entity.javadoc),
        "javadoc_after": normalize_file_text(new_entity.javadoc),
        "_source_dataset": "recovery_without_commit_cap",
        "_source_order": source_order,
    }


def rejection_reason(file_change: FileChange, old_entity: EntityDoc, new_entity: EntityDoc) -> str:
    if not old_entity.javadoc.strip() or not new_entity.javadoc.strip():
        return "empty_javadoc"
    if is_weak_inheritdoc_only_change(old_entity.javadoc, new_entity.javadoc):
        return "weak_inheritdoc_only"
    if not entity_code_changed(file_change, old_entity, new_entity):
        return "code_not_changed"
    code_before = normalize_file_text(entity_code_text(file_change.old_content, old_entity))
    code_after = normalize_file_text(entity_code_text(file_change.new_content, new_entity))
    javadoc_before = normalize_file_text(old_entity.javadoc)
    javadoc_after = normalize_file_text(new_entity.javadoc)
    if not code_before or not code_after:
        return "empty_code"
    if code_before == code_after:
        return "identical_code"
    if javadoc_before == javadoc_after:
        return "identical_javadoc"
    if format_only_reason(javadoc_before, javadoc_after):
        return "format_only_javadoc"
    code_reason = validate_code_snippet(code_before, new_entity.entity_type)
    if code_reason:
        return f"invalid_code_before:{code_reason}"
    code_reason = validate_code_snippet(code_after, new_entity.entity_type)
    if code_reason:
        return f"invalid_code_after:{code_reason}"
    return ""


def deduplicate_recovered_changes(
    raw_changes: list[dict],
    existing_fingerprints: set[str],
) -> tuple[list[dict], list[dict]]:
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for change in raw_changes:
        groups.setdefault(content_fingerprint(change), []).append(change)

    cleaned: list[dict] = []
    duplicate_groups: list[dict] = []
    for fingerprint, group in groups.items():
        if fingerprint in existing_fingerprints:
            duplicate_groups.append(
                {
                    "fingerprint": fingerprint,
                    "reason": "duplicate_with_existing_final_dataset",
                    "kept": "existing_merged_change",
                    "removed": [_audit_change(change) for change in group],
                }
            )
            continue
        winner = group[0]
        cleaned.append(winner)
        if len(group) > 1:
            duplicate_groups.append(
                {
                    "fingerprint": fingerprint,
                    "reason": "duplicate_within_recovered_dataset",
                    "kept": _audit_change(winner),
                    "removed": [_audit_change(change) for change in group[1:]],
                }
            )
    cleaned.sort(key=lambda change: int(change.get("_source_order", 0)))
    return cleaned, duplicate_groups


def merge_recovered_changes(current_grouped: list[dict], recovered_changes: list[dict]) -> dict:
    current_flat = flatten_grouped_changes(current_grouped, source_dataset="existing_merged")
    combined = current_flat + recovered_changes
    seen: set[str] = set()
    deduped: list[dict] = []
    for change in combined:
        fingerprint = content_fingerprint(change)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(change)
    grouped = group_flat_changes(deduped)
    return {"flat": deduped, "grouped": grouped}


def flatten_grouped_changes(grouped: list[dict], source_dataset: str) -> list[dict]:
    flat: list[dict] = []
    for commit_order, commit in enumerate(grouped):
        for change in commit.get("changes", []):
            flat.append(
                {
                    "project_slug": commit.get("project_slug", ""),
                    "repository_url": commit.get("repository_url", ""),
                    "commit_hash": commit.get("commit_hash", ""),
                    "issue_summary": commit.get("issue_summary", ""),
                    "entity_type": change.get("entity_type", ""),
                    "code_before": change.get("code_before", ""),
                    "code_after": change.get("code_after", ""),
                    "javadoc_before": change.get("javadoc_before", ""),
                    "javadoc_after": change.get("javadoc_after", ""),
                    "_source_dataset": source_dataset,
                    "_source_order": commit_order * 100000 + int(change.get("change_index", 0)),
                }
            )
    return flat


def group_flat_changes(changes: list[dict]) -> list[dict]:
    groups: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    for change in changes:
        key = (change.get("project_slug", ""), change.get("commit_hash", ""))
        groups.setdefault(key, []).append(change)

    grouped: list[dict] = []
    for (project_slug, commit_hash), group in groups.items():
        commit = {
            "project_slug": project_slug,
            "repository_url": group[0].get("repository_url", ""),
            "commit_hash": commit_hash,
            "issue_summary": group[0].get("issue_summary", ""),
            "changes": [],
        }
        local_seen: set[str] = set()
        for change in group:
            fingerprint = content_fingerprint(change)
            if fingerprint in local_seen:
                continue
            local_seen.add(fingerprint)
            commit["changes"].append(
                {
                    "change_index": len(commit["changes"]) + 1,
                    "entity_type": change["entity_type"],
                    "code_before": change["code_before"],
                    "code_after": change["code_after"],
                    "javadoc_before": change["javadoc_before"],
                    "javadoc_after": change["javadoc_after"],
                }
            )
        if commit["changes"]:
            grouped.append(commit)
    return grouped


def build_recovery_summary(
    targets: list[dict],
    target_reports: list[dict],
    raw_recovered: list[dict],
    cleaned_recovered: list[dict],
    duplicate_groups: list[dict],
    removed_format_only: list[dict],
    reprocess_failures: list[dict],
) -> dict:
    duplicate_with_existing = sum(
        len(group["removed"])
        for group in duplicate_groups
        if group.get("reason") == "duplicate_with_existing_final_dataset"
    )
    duplicate_within_recovery = sum(
        len(group["removed"])
        for group in duplicate_groups
        if group.get("reason") == "duplicate_within_recovered_dataset"
    )
    unresolved_commit_count = unresolved_commit_count_from_failures(reprocess_failures)
    return {
        "target_commit_count": len(targets),
        "successfully_reprocessed_commit_count": max(0, len(target_reports) - unresolved_commit_count),
        "failed_or_partially_failed_commit_count": unresolved_commit_count,
        "raw_reprocessed_change_count": len(raw_recovered),
        "new_recovered_change_count": len(cleaned_recovered),
        "duplicate_with_existing_count": duplicate_with_existing,
        "duplicate_within_recovery_count": duplicate_within_recovery,
        "format_only_removed_count": len(removed_format_only),
        "invalid_candidate_count": sum(report["invalid_candidate_count"] for report in target_reports),
        "weak_inheritdoc_only_count": sum(report["weak_inheritdoc_only_count"] for report in target_reports),
        "per_project_new_recovered_count": _per_project_count(cleaned_recovered),
    }


def build_final_summary(
    targets: list[dict],
    target_reports: list[dict],
    current_grouped: list[dict],
    current_flat: list[dict],
    raw_recovered: list[dict],
    cleaned_recovered: list[dict],
    duplicate_groups: list[dict],
    removed_format_only: list[dict],
    reprocess_failures: list[dict],
    final_grouped: list[dict],
    validation: dict,
) -> dict:
    final_flat_count = sum(len(commit.get("changes", [])) for commit in final_grouped)
    distribution = _change_distribution(final_grouped)
    audit_examples = {
        (commit.get("project_slug", ""), commit.get("commit_hash", "")): len(commit.get("changes", []))
        for commit in final_grouped
        if (
            commit.get("project_slug", ""),
            commit.get("commit_hash", ""),
        )
        in {
            ("apache_commons_compress", "86c20cdc037a8a3b73927b2ad51f0f9e844ba5f8"),
            ("apache_commons_io", "8b6d4969ffb55bf7301a44a8156f02b0213e6d68"),
            ("jodaorg_joda_time", "0e07ac6b2cff63550d7df336355ca63cc05aa40b"),
        }
    }
    return {
        "current_dataset_path": "final_dataset_merged",
        "output_dataset_path": "final_dataset_merged_no_commit_cap",
        "recovery_dataset_path": "recovery_without_commit_cap",
        "target_commit_count": len(targets),
        "current_commit_count": len(current_grouped),
        "current_change_count": len(current_flat),
        "raw_reprocessed_change_count": len(raw_recovered),
        "newly_recovered_change_count": len(cleaned_recovered),
        "final_commit_count": len(final_grouped),
        "final_change_count": final_flat_count,
        "added_change_count": final_flat_count - len(current_flat),
        "method_change_count": sum(
            1 for commit in final_grouped for change in commit["changes"] if change["entity_type"] == "method"
        ),
        "class_change_count": sum(
            1 for commit in final_grouped for change in commit["changes"] if change["entity_type"] == "class"
        ),
        "commits_with_more_than_3_changes": sum(1 for commit in final_grouped if len(commit["changes"]) > 3),
        "max_changes_in_one_commit": max((len(commit["changes"]) for commit in final_grouped), default=0),
        "changes_per_commit_distribution": distribution,
        "per_project_final_change_count": _per_project_count(flatten_grouped_changes(final_grouped, "final")),
        "per_project_new_recovered_count": _per_project_count(cleaned_recovered),
        "duplicate_with_existing_count": sum(
            len(group["removed"])
            for group in duplicate_groups
            if group.get("reason") == "duplicate_with_existing_final_dataset"
        ),
        "duplicate_within_recovery_count": sum(
            len(group["removed"])
            for group in duplicate_groups
            if group.get("reason") == "duplicate_within_recovered_dataset"
        ),
        "format_only_removed_count": len(removed_format_only),
        "failed_or_partially_failed_commit_count": unresolved_commit_count_from_failures(reprocess_failures),
        "target_report_count": len(target_reports),
        "audit_example_change_counts": {
            f"{project_slug}/{commit_hash}": count
            for (project_slug, commit_hash), count in sorted(audit_examples.items())
        },
        "top_commits_by_change_count": _top_commits(final_grouped, limit=20),
        "validation": validation,
    }


def _change_distribution(grouped: list[dict]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for commit in grouped:
        count = len(commit.get("changes", []))
        if count <= 3:
            buckets[str(count)] += 1
        elif count <= 5:
            buckets["4-5"] += 1
        elif count <= 10:
            buckets["6-10"] += 1
        elif count <= 20:
            buckets["11-20"] += 1
        elif count <= 50:
            buckets["21-50"] += 1
        else:
            buckets[">50"] += 1
    order = ["1", "2", "3", "4-5", "6-10", "11-20", "21-50", ">50"]
    return {bucket: buckets[bucket] for bucket in order if buckets[bucket]}


def _top_commits(grouped: list[dict], limit: int) -> list[dict]:
    rows = [
        {
            "project_slug": commit.get("project_slug", ""),
            "commit_hash": commit.get("commit_hash", ""),
            "change_count": len(commit.get("changes", [])),
            "issue_summary": commit.get("issue_summary", ""),
        }
        for commit in grouped
    ]
    rows.sort(key=lambda row: (-row["change_count"], row["project_slug"], row["commit_hash"]))
    return rows[:limit]


def unresolved_commits_from_failures(failures: list[dict]) -> list[dict]:
    by_commit: OrderedDict[tuple[str, str], dict] = OrderedDict()
    for failure in failures:
        if not is_unresolved_reprocess_failure(failure):
            continue
        key = (failure.get("project_slug", ""), failure.get("commit_hash", ""))
        entry = by_commit.setdefault(
            key,
            {
                "project_slug": failure.get("project_slug", ""),
                "repository_url": failure.get("repository_url", ""),
                "commit_hash": failure.get("commit_hash", ""),
                "reasons": [],
            },
        )
        reason = failure.get("reason", "")
        if reason and reason not in entry["reasons"]:
            entry["reasons"].append(reason)
    return list(by_commit.values())


def unresolved_commit_count_from_failures(failures: list[dict]) -> int:
    return len(
        {
            (failure.get("project_slug", ""), failure.get("commit_hash", ""))
            for failure in failures
            if is_unresolved_reprocess_failure(failure)
        }
    )


def is_unresolved_reprocess_failure(failure: dict) -> bool:
    return failure.get("reason", "").split(":", 1)[0] in UNRESOLVED_REPROCESS_REASONS


def load_checkpoint(recovery_dir: Path) -> dict:
    candidates = [recovery_dir / "checkpoint.json", recovery_dir / ".checkpoint.json.tmp"]
    candidates.extend(sorted(recovery_dir.glob("checkpoint_*.json")))
    best: dict = {}
    best_count = -1
    for path in candidates:
        data = _read_json(path, {})
        if not isinstance(data, dict):
            continue
        reports = data.get("target_reports", [])
        if not isinstance(reports, list):
            continue
        count = len(reports)
        if count > best_count:
            best = data
            best_count = count
    return best


def write_checkpoint(recovery_dir: Path, checkpoint: dict) -> None:
    count = len(checkpoint.get("target_reports", []))
    path = recovery_dir / f"checkpoint_{count:04d}.json"
    if path.exists():
        return
    _write_json(path, checkpoint)


def strip_recovery_internal(changes: list[dict]) -> list[dict]:
    output: list[dict] = []
    for change in changes:
        output.append(
            {
                "project_slug": change.get("project_slug", ""),
                "repository_url": change.get("repository_url", ""),
                "commit_hash": change.get("commit_hash", ""),
                "issue_summary": change.get("issue_summary", ""),
                "entity_type": change.get("entity_type", ""),
                "entity_name": change.get("entity_name", ""),
                "entity_signature": change.get("entity_signature", ""),
                "file_path": change.get("file_path", ""),
                "code_before": change.get("code_before", ""),
                "code_after": change.get("code_after", ""),
                "javadoc_before": change.get("javadoc_before", ""),
                "javadoc_after": change.get("javadoc_after", ""),
            }
        )
    return output


def strip_final_flat(changes: list[dict]) -> list[dict]:
    output: list[dict] = []
    for change in changes:
        output.append(
            {
                "project_slug": change.get("project_slug", ""),
                "repository_url": change.get("repository_url", ""),
                "commit_hash": change.get("commit_hash", ""),
                "issue_summary": change.get("issue_summary", ""),
                "entity_type": change.get("entity_type", ""),
                "code_before": change.get("code_before", ""),
                "code_after": change.get("code_after", ""),
                "javadoc_before": change.get("javadoc_before", ""),
                "javadoc_after": change.get("javadoc_after", ""),
                "source_dataset": change.get("_source_dataset", ""),
            }
        )
    return output


def render_recovery_readme(summary: dict) -> str:
    return f"""# Recovery Without Commit Cap

This directory contains the independent recovery pass for commits that had
exactly three changes in `final_dataset_merged`.

The pass reprocesses only the target commits listed in
`target_commits.json`; it does not scan full repository histories.

## Counts

- Target commits: {summary['target_commit_count']}
- Raw reprocessed changes: {summary['raw_reprocessed_change_count']}
- New recovered changes after content dedupe: {summary['new_recovered_change_count']}
- Duplicates with existing merged dataset: {summary['duplicate_with_existing_count']}
- Duplicates inside recovery: {summary['duplicate_within_recovery_count']}
- Format-only removed: {summary['format_only_removed_count']}
- Failed or partially failed commits: {summary['failed_or_partially_failed_commit_count']}

## Files

- `target_commits.json`
- `recovered_raw_flat.json`
- `recovered_cleaned_flat.json`
- `recovered_by_commit.json`
- `recovered_duplicates.json`
- `recovered_format_only.json`
- `reprocess_failures.json`
- `target_reports.json`
- `summary.json`
- `summary.csv`
"""


def render_final_readme(summary: dict) -> str:
    return f"""# Merged Dataset Without Per-Commit Cap

This directory is a no-cap successor to `final_dataset_merged`.

The old merged dataset is preserved. The recovery pass only reprocessed target
commits that already had exactly three changes and added newly discovered
non-duplicate method/class Javadoc updates.

## Counts

- Original merged commits: {summary['current_commit_count']}
- Original merged changes: {summary['current_change_count']}
- Target commits reprocessed: {summary['target_commit_count']}
- Raw reprocessed changes: {summary['raw_reprocessed_change_count']}
- Newly recovered changes: {summary['newly_recovered_change_count']}
- Final commits: {summary['final_commit_count']}
- Final changes: {summary['final_change_count']}
- Commits with more than 3 changes: {summary['commits_with_more_than_3_changes']}
- Max changes in one commit: {summary['max_changes_in_one_commit']}
- Validation passed: {summary['validation']['passed']}

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
"""


def _audit_change(change: dict) -> dict:
    return {
        "project_slug": change.get("project_slug", ""),
        "repository_url": change.get("repository_url", ""),
        "commit_hash": change.get("commit_hash", ""),
        "issue_summary": change.get("issue_summary", ""),
        "entity_type": change.get("entity_type", ""),
        "entity_name": change.get("entity_name", ""),
        "entity_signature": change.get("entity_signature", ""),
        "file_path": change.get("file_path", ""),
    }


def _commit_failure(target: dict, reason: str, detail: str = "") -> dict:
    failure = {
        "project_slug": target.get("project_slug", ""),
        "repository_url": target.get("repository_url", ""),
        "commit_hash": target.get("commit_hash", ""),
        "reason": reason,
    }
    if detail:
        failure["detail"] = detail[:1000]
    return failure


def _candidate_failure(target: dict, file_path: str, reason: str) -> dict:
    return {
        "project_slug": target.get("project_slug", ""),
        "repository_url": target.get("repository_url", ""),
        "commit_hash": target.get("commit_hash", ""),
        "file_path": file_path,
        "reason": reason,
    }


def _per_project_count(changes: list[dict]) -> dict[str, int]:
    counter: Counter[str] = Counter(change.get("project_slug", "") for change in changes)
    return dict(sorted(counter.items()))


def _configure_git_safe_directories(cache_dir: Path, targets: list[dict]) -> None:
    repo_dirs = []
    seen: set[Path] = set()
    for target in targets:
        repository_url = target.get("repository_url", "")
        if not repository_url:
            continue
        repo_dir = (cache_dir / cache_name(repository_url)).resolve()
        if repo_dir in seen or not repo_dir.exists():
            continue
        seen.add(repo_dir)
        repo_dirs.append(repo_dir)
    os.environ["GIT_CONFIG_COUNT"] = str(len(repo_dirs))
    for index, repo_dir in enumerate(repo_dirs):
        os.environ[f"GIT_CONFIG_KEY_{index}"] = "safe.directory"
        os.environ[f"GIT_CONFIG_VALUE_{index}"] = repo_dir.as_posix()


def _write_summary_csv(path: Path, summary: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in summary.items():
            if isinstance(value, (dict, list)):
                writer.writerow([key, json.dumps(value, ensure_ascii=False, sort_keys=True)])
            else:
                writer.writerow([key, value])


def _resolve(root_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else root_dir / path


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=True, indent=2)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


if __name__ == "__main__":
    raise SystemExit(main())
