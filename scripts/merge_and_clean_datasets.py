import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from javadoc_miner.validation import validate_code_snippet


FINAL_SAMPLE_FIELDS = (
    "commit_hash",
    "issue_summary",
    "code_before",
    "code_after",
    "javadoc_before",
    "javadoc_after",
)
CHANGE_FIELDS = (
    "change_index",
    "entity_type",
    "code_before",
    "code_after",
    "javadoc_before",
    "javadoc_after",
)
WEAK_ISSUE_SUMMARIES = {
    "pr",
    "fix",
    "fixed",
    "update",
    "changes",
    "cleanup",
    "clean up",
    "revert",
}
DANGLING_SUMMARY_WORDS = {"by", "to", "for", "with", "of", "in", "on", "and", "or", "from", "into"}
FORMAT_TAG_PATTERN = re.compile(
    r"</?(?:p|br|b|i|em|strong|code|pre|ul|ol|li|blockquote|span)\b[^>]*>",
    re.IGNORECASE,
)
JAVADOC_INLINE_PATTERN = re.compile(r"\{@([a-zA-Z]+)\s+([^}]*)\}")
JAVA_CLASS_PATTERN = re.compile(r"\b(?:class|interface|enum|record)\s+[A-Za-z_$][\w$]*")
JAVA_METHOD_PATTERN = re.compile(r"\b[A-Za-z_$][\w$]*\s*\([^;{}]*\)")


@dataclass(frozen=True)
class DatasetPaths:
    old_dir: Path
    new_dir: Path
    output_dir: Path
    cache_dir: Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge, clean, deduplicate, and group Javadoc update datasets by commit."
    )
    parser.add_argument("--root-dir", type=Path, default=Path("."))
    parser.add_argument("--old-dir", type=Path, default=Path("final_dataset"))
    parser.add_argument("--new-dir", type=Path, default=Path("final_dataset_extra_3k"))
    parser.add_argument("--output-dir", type=Path, default=Path("final_dataset_merged"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/repos"))
    args = parser.parse_args(argv)

    paths = DatasetPaths(
        old_dir=_resolve(args.root_dir, args.old_dir),
        new_dir=_resolve(args.root_dir, args.new_dir),
        output_dir=_resolve(args.root_dir, args.output_dir),
        cache_dir=_resolve(args.root_dir, args.cache_dir),
    )
    merge_and_clean(paths)
    return 0


def merge_and_clean(paths: DatasetPaths) -> dict:
    _require_dataset(paths.old_dir, expected_count=2000)
    _require_dataset(paths.new_dir, expected_count=1621)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _backup_sources(paths)

    old_changes = load_dataset(paths.old_dir, "old")
    new_changes = load_dataset(paths.new_dir, "new")
    raw_changes = old_changes + new_changes
    _write_json(paths.output_dir / "combined_raw_flat.json", raw_changes)

    cleaned: list[dict] = []
    removed_format_only: list[dict] = []
    entity_type_review: list[dict] = []
    invalid_changes: list[dict] = []

    for change in raw_changes:
        sample = clean_change(change)
        if sample is None:
            invalid_changes.append({"change": _redacted_change(change), "reason": "invalid_schema_or_empty_field"})
            continue
        entity_type = infer_entity_type(sample["code_before"], sample["code_after"])
        if entity_type is None:
            entity_type_review.append({"change": _redacted_change(sample), "reason": "unknown_entity_type"})
            continue
        sample["_entity_type"] = entity_type
        if sample["code_before"] == sample["code_after"]:
            invalid_changes.append({"change": _redacted_change(sample), "reason": "identical_code"})
            continue
        if sample["javadoc_before"] == sample["javadoc_after"]:
            invalid_changes.append({"change": _redacted_change(sample), "reason": "identical_javadoc"})
            continue
        format_reason = format_only_reason(sample["javadoc_before"], sample["javadoc_after"])
        if format_reason:
            removed_format_only.append({"change": _redacted_change(sample), "reason": format_reason})
            continue
        cleaned.append(sample)

    deduped, duplicate_groups = deduplicate_changes(cleaned)
    _write_json(paths.output_dir / "removed_duplicates.json", duplicate_groups)
    _write_json(paths.output_dir / "removed_format_only.json", removed_format_only)
    _write_json(paths.output_dir / "entity_type_review.json", entity_type_review)
    _write_json(paths.output_dir / "invalid_changes.json", invalid_changes)

    resolved, unresolved_issue_summary, issue_source_counts = resolve_issue_summaries(
        deduped,
        paths.cache_dir,
    )
    _write_json(paths.output_dir / "unresolved_issue_summary.json", unresolved_issue_summary)
    _write_json(paths.output_dir / "issue_summary_sources.json", issue_source_counts)

    grouped, issue_conflicts = group_by_commit(resolved)
    _write_json(paths.output_dir / "issue_summary_conflicts.json", issue_conflicts)
    _write_json(paths.output_dir / "combined_cleaned_flat.json", strip_internal_fields(resolved))
    _write_json(paths.output_dir / "combined_by_commit.json", grouped)

    validation = validate_grouped_dataset(grouped)
    _write_json(paths.output_dir / "validation_report.json", validation)

    javadoc_review = find_javadoc_format_review(resolved)
    _write_json(paths.output_dir / "javadoc_format_review.json", javadoc_review)

    summary = build_summary(
        old_changes=old_changes,
        new_changes=new_changes,
        raw_changes=raw_changes,
        cleaned_changes=resolved,
        grouped=grouped,
        duplicate_groups=duplicate_groups,
        removed_format_only=removed_format_only,
        unresolved_issue_summary=unresolved_issue_summary,
        issue_source_counts=issue_source_counts,
        entity_type_review=entity_type_review,
        invalid_changes=invalid_changes,
        javadoc_review=javadoc_review,
        validation=validation,
    )
    _write_json(paths.output_dir / "summary.json", summary)
    _write_summary_csv(paths.output_dir / "summary.csv", summary)
    (paths.output_dir / "README.md").write_text(render_output_readme(summary), encoding="utf-8")
    return summary


def load_dataset(dataset_dir: Path, dataset_label: str) -> list[dict]:
    changes: list[dict] = []
    project_dirs = sorted(path for path in dataset_dir.iterdir() if path.is_dir())
    for project_dir in project_dirs:
        combined_path = project_dir / "combined_samples.json"
        if not combined_path.exists():
            continue
        metadata = _read_json(project_dir / "metadata.json", {})
        repository_url = metadata.get("repository_url", "") if isinstance(metadata, dict) else ""
        raw_samples = _read_json(combined_path, [])
        if not isinstance(raw_samples, list):
            continue
        for index, sample in enumerate(raw_samples, start=1):
            if not isinstance(sample, dict):
                continue
            change = {field: sample.get(field, "") for field in FINAL_SAMPLE_FIELDS}
            change["_dataset"] = dataset_label
            change["_project_slug"] = project_dir.name
            change["_repository_url"] = repository_url
            change["_source_sample_id"] = f"{project_dir.name}/sample_{index:04d}"
            change["_source_path"] = str(combined_path)
            change["_source_order"] = len(changes)
            changes.append(change)
    return changes


def clean_change(change: dict) -> dict | None:
    if not all(field in change for field in FINAL_SAMPLE_FIELDS):
        return None
    cleaned = dict(change)
    for field in FINAL_SAMPLE_FIELDS:
        value = cleaned[field]
        if not isinstance(value, str):
            return None
        value = normalize_file_text(value)
        if not value.strip():
            return None
        cleaned[field] = value
    return cleaned


def normalize_file_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def content_fingerprint(change: dict) -> str:
    payload = "\u241e".join(
        normalize_file_text(str(change[field]))
        for field in ("code_before", "code_after", "javadoc_before", "javadoc_after")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deduplicate_changes(changes: list[dict]) -> tuple[list[dict], list[dict]]:
    by_fingerprint: OrderedDict[str, list[dict]] = OrderedDict()
    for change in changes:
        by_fingerprint.setdefault(content_fingerprint(change), []).append(change)

    kept: list[dict] = []
    removed_groups: list[dict] = []
    for fingerprint, group in by_fingerprint.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        winner = max(group, key=_dedupe_priority)
        kept.append(winner)
        removed = [item for item in group if item is not winner]
        removed_groups.append(
            {
                "fingerprint": fingerprint,
                "kept": _audit_change(winner),
                "removed": [_audit_change(item) for item in removed],
                "reason": "identical_content",
            }
        )
    kept.sort(key=lambda item: int(item.get("_source_order", 0)))
    return kept, removed_groups


def _dedupe_priority(change: dict) -> tuple[int, int, int]:
    summary = change.get("issue_summary", "")
    non_weak = 0 if is_weak_issue_summary(summary) else 1
    old_baseline = 1 if change.get("_dataset") == "old" else 0
    source_order = -int(change.get("_source_order", 0))
    return (non_weak, old_baseline, source_order)


def infer_entity_type(code_before: str, code_after: str) -> str | None:
    before_class = validate_code_snippet(code_before, "class") == ""
    after_class = validate_code_snippet(code_after, "class") == ""
    before_method = validate_code_snippet(code_before, "method") == ""
    after_method = validate_code_snippet(code_after, "method") == ""
    if before_class and after_class:
        return "class"
    if before_method and after_method:
        return "method"

    before_decl = _declaration_text(code_before)
    after_decl = _declaration_text(code_after)
    if JAVA_CLASS_PATTERN.search(before_decl) and JAVA_CLASS_PATTERN.search(after_decl):
        return "class"
    if (
        JAVA_METHOD_PATTERN.search(before_decl)
        and JAVA_METHOD_PATTERN.search(after_decl)
        and not JAVA_CLASS_PATTERN.search(before_decl)
        and not JAVA_CLASS_PATTERN.search(after_decl)
    ):
        return "method"
    return None


def _declaration_text(code: str) -> str:
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", " ", code, flags=re.DOTALL)
    lines: list[str] = []
    for line in without_comments.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("@"):
            continue
        lines.append(stripped)
        if "{" in stripped or ";" in stripped:
            break
    return " ".join(lines)


def format_only_reason(old_doc: str, new_doc: str) -> str:
    if normalize_javadoc_layout(old_doc) == normalize_javadoc_layout(new_doc):
        return "whitespace_or_line_wrapping_only"
    if normalize_javadoc_format(old_doc) == normalize_javadoc_format(new_doc):
        return "punctuation_or_html_formatting_only"
    return ""


def normalize_javadoc_layout(text: str) -> str:
    return " ".join(_javadoc_content_lines(text))


def normalize_javadoc_format(text: str) -> str:
    content = " ".join(_javadoc_content_lines(text))
    content = FORMAT_TAG_PATTERN.sub(" ", content)
    content = re.sub(r"<[^>]+>", " ", content)
    content = JAVADOC_INLINE_PATTERN.sub(lambda match: f"{match.group(1)} {match.group(2)}", content)
    tokens = re.findall(r"@?[A-Za-z0-9_$]+", content.lower())
    return " ".join(tokens)


def _javadoc_content_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in normalize_file_text(text).split("\n"):
        line = raw_line.strip()
        if line.startswith("/**"):
            line = line[3:].strip()
        if line.endswith("*/"):
            line = line[:-2].strip()
        if line.startswith("*"):
            line = line[1:].strip()
        if line:
            lines.append(" ".join(line.split()))
    return lines


def resolve_issue_summaries(
    changes: list[dict],
    cache_dir: Path,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    resolved: list[dict] = []
    unresolved: list[dict] = []
    source_counts: Counter[str] = Counter()
    commit_cache: dict[tuple[str, str], tuple[str, str]] = {}

    for change in changes:
        updated = dict(change)
        summary = updated["issue_summary"]
        source = "existing_issue_summary"
        if is_weak_issue_summary(summary):
            key = (updated.get("_project_slug", ""), updated["commit_hash"])
            commit_summary, commit_source = commit_cache.get(key, ("", ""))
            if key not in commit_cache:
                commit_summary, commit_source = commit_subject_from_cache(
                    cache_dir,
                    updated.get("_repository_url", ""),
                    updated["commit_hash"],
                )
                commit_cache[key] = (commit_summary, commit_source)
            if commit_summary and not is_weak_issue_summary(commit_summary):
                updated["issue_summary"] = commit_summary
                source = commit_source or "commit_subject"
            else:
                unresolved.append(
                    {
                        "project_slug": updated.get("_project_slug", ""),
                        "repository_url": updated.get("_repository_url", ""),
                        "commit_hash": updated["commit_hash"],
                        "issue_summary": summary,
                        "source_sample_id": updated.get("_source_sample_id", ""),
                        "reason": "weak_issue_summary_unresolved",
                    }
                )
                continue
        updated["_issue_summary_source"] = source
        source_counts[source] += 1
        resolved.append(updated)
    return resolved, unresolved, dict(sorted(source_counts.items()))


def is_weak_issue_summary(summary: str) -> bool:
    stripped = re.sub(r"\s+", " ", summary.strip())
    normalized = stripped.strip(" .,:;!-_").lower()
    if not normalized:
        return True
    if normalized in WEAK_ISSUE_SUMMARIES:
        return True
    if len(normalized) <= 3:
        return True
    if stripped.rstrip().endswith((".", "!", "?")):
        return False
    words = normalized.split()
    return bool(words and words[-1].strip(".,;:!?") in DANGLING_SUMMARY_WORDS)


def commit_subject_from_cache(cache_dir: Path, repository_url: str, commit_hash: str) -> tuple[str, str]:
    if not repository_url:
        return "", ""
    repo_dir = cache_dir / cache_name(repository_url)
    if not repo_dir.exists():
        return "", ""
    env = _git_safe_env(repo_dir)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "--format=%B", "-n", "1", commit_hash],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    if result.returncode != 0:
        return "", ""
    for line in result.stdout.splitlines():
        subject = line.strip()
        if subject:
            return subject, "commit_subject"
    return "", ""


def cache_name(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path.replace("/", "__")
    return Path(repo_url).name


def _git_safe_env(repo_dir: Path) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "safe.directory"
    env["GIT_CONFIG_VALUE_0"] = repo_dir.resolve().as_posix()
    return env


def group_by_commit(changes: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    for change in changes:
        key = (change.get("_project_slug", ""), change["commit_hash"])
        groups.setdefault(key, []).append(change)

    grouped: list[dict] = []
    conflicts: list[dict] = []
    for (project_slug, commit_hash), group in groups.items():
        summary = choose_commit_issue_summary(group)
        unique_summaries = sorted({item["issue_summary"] for item in group})
        if len(unique_summaries) > 1:
            conflicts.append(
                {
                    "project_slug": project_slug,
                    "commit_hash": commit_hash,
                    "chosen_issue_summary": summary,
                    "candidate_issue_summaries": unique_summaries,
                }
            )
        commit = {
            "project_slug": project_slug,
            "repository_url": group[0].get("_repository_url", ""),
            "commit_hash": commit_hash,
            "issue_summary": summary,
            "changes": [],
        }
        seen_in_commit: set[str] = set()
        for change in group:
            fingerprint = content_fingerprint(change)
            if fingerprint in seen_in_commit:
                continue
            seen_in_commit.add(fingerprint)
            commit["changes"].append(
                {
                    "change_index": len(commit["changes"]) + 1,
                    "entity_type": change["_entity_type"],
                    "code_before": change["code_before"],
                    "code_after": change["code_after"],
                    "javadoc_before": change["javadoc_before"],
                    "javadoc_after": change["javadoc_after"],
                }
            )
        if commit["changes"]:
            grouped.append(commit)
    return grouped, conflicts


def choose_commit_issue_summary(group: list[dict]) -> str:
    source_rank = {
        "issue_title": 5,
        "pull_request_title": 4,
        "commit_subject": 3,
        "commit_body": 2,
        "existing_issue_summary": 1,
    }
    return max(
        group,
        key=lambda item: (
            0 if is_weak_issue_summary(item["issue_summary"]) else 1,
            source_rank.get(item.get("_issue_summary_source", "existing_issue_summary"), 0),
            -int(item.get("_source_order", 0)),
        ),
    )["issue_summary"]


def validate_grouped_dataset(grouped: list[dict]) -> dict:
    errors: dict[str, list] = defaultdict(list)
    seen_commits: set[tuple[str, str]] = set()
    seen_changes: set[str] = set()
    for commit_index, commit in enumerate(grouped, start=1):
        commit_id = f"commit_{commit_index:04d}"
        for field in ("commit_hash", "issue_summary", "changes"):
            if field not in commit:
                errors["missing_commit_fields"].append({"commit": commit_id, "field": field})
        commit_key = (commit.get("project_slug", ""), commit.get("commit_hash", ""))
        if commit_key in seen_commits:
            errors["duplicate_commits"].append(commit_key)
        seen_commits.add(commit_key)
        if not isinstance(commit.get("issue_summary"), str) or not commit.get("issue_summary", "").strip():
            errors["empty_issue_summary"].append(commit_id)
        elif is_weak_issue_summary(commit["issue_summary"]):
            errors["weak_issue_summary"].append(
                {"commit": commit_id, "issue_summary": commit["issue_summary"]}
            )
        changes = commit.get("changes")
        if not isinstance(changes, list) or not changes:
            errors["empty_changes"].append(commit_id)
            continue
        local_fingerprints: set[str] = set()
        for expected_index, change in enumerate(changes, start=1):
            change_id = f"{commit_id}/change_{expected_index:04d}"
            if set(change) != set(CHANGE_FIELDS):
                errors["change_schema"].append(change_id)
                continue
            if change["change_index"] != expected_index:
                errors["bad_change_index"].append(change_id)
            if change["entity_type"] not in {"method", "class"}:
                errors["bad_entity_type"].append(change_id)
            if any(not isinstance(change[field], str) or not change[field].strip() for field in CHANGE_FIELDS if field != "change_index"):
                errors["empty_change_fields"].append(change_id)
            if change["code_before"] == change["code_after"]:
                errors["identical_code"].append(change_id)
            if change["javadoc_before"] == change["javadoc_after"]:
                errors["identical_javadoc"].append(change_id)
            if format_only_reason(change["javadoc_before"], change["javadoc_after"]):
                errors["format_only_javadoc"].append(change_id)
            fingerprint = content_fingerprint(change)
            if fingerprint in seen_changes:
                errors["duplicate_changes"].append(change_id)
            if fingerprint in local_fingerprints:
                errors["duplicate_changes_within_commit"].append(change_id)
            seen_changes.add(fingerprint)
            local_fingerprints.add(fingerprint)
    report = {
        "passed": not errors,
        "commit_count": len(grouped),
        "change_count": sum(len(commit.get("changes", [])) for commit in grouped),
        "errors": dict(errors),
    }
    return report


def strip_internal_fields(changes: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for change in changes:
        item = {
            "project_slug": change.get("_project_slug", ""),
            "repository_url": change.get("_repository_url", ""),
            "commit_hash": change["commit_hash"],
            "issue_summary": change["issue_summary"],
            "entity_type": change["_entity_type"],
            "code_before": change["code_before"],
            "code_after": change["code_after"],
            "javadoc_before": change["javadoc_before"],
            "javadoc_after": change["javadoc_after"],
            "source_dataset": change.get("_dataset", ""),
            "source_sample_id": change.get("_source_sample_id", ""),
            "issue_summary_source": change.get("_issue_summary_source", ""),
        }
        flat.append(item)
    return flat


def build_summary(
    old_changes: list[dict],
    new_changes: list[dict],
    raw_changes: list[dict],
    cleaned_changes: list[dict],
    grouped: list[dict],
    duplicate_groups: list[dict],
    removed_format_only: list[dict],
    unresolved_issue_summary: list[dict],
    issue_source_counts: dict[str, int],
    entity_type_review: list[dict],
    invalid_changes: list[dict],
    javadoc_review: list[dict],
    validation: dict,
) -> dict:
    method_count = 0
    class_count = 0
    per_project: Counter[str] = Counter()
    per_entity: Counter[str] = Counter()
    distribution: Counter[str] = Counter()
    for commit in grouped:
        count = len(commit["changes"])
        distribution[str(count)] += 1
        project_slug = commit.get("project_slug", "")
        for change in commit["changes"]:
            per_project[project_slug] += 1
            per_entity[change["entity_type"]] += 1
            if change["entity_type"] == "method":
                method_count += 1
            elif change["entity_type"] == "class":
                class_count += 1
    final_total = method_count + class_count
    duplicate_count = sum(len(group["removed"]) for group in duplicate_groups)
    old_new_duplicate_count = sum(
        1
        for group in duplicate_groups
        if {group["kept"].get("source_dataset"), *(item.get("source_dataset") for item in group["removed"])}
        == {"old", "new"}
    )
    weak_detected = sum(
        1 for change in raw_changes if is_weak_issue_summary(str(change.get("issue_summary", "")))
    )
    weak_unresolved = len(unresolved_issue_summary)
    summary = {
        "old_dataset_path": "final_dataset",
        "new_dataset_path": "final_dataset_extra_3k",
        "old_dataset_raw_change_count": len(old_changes),
        "new_dataset_raw_change_count": len(new_changes),
        "merged_raw_change_count": len(raw_changes),
        "duplicate_change_count": duplicate_count,
        "old_new_duplicate_count": old_new_duplicate_count,
        "format_only_removed_count": len(removed_format_only),
        "weak_issue_detected_count": weak_detected,
        "weak_issue_resolved_count": max(0, weak_detected - weak_unresolved),
        "weak_issue_unresolved_count": weak_unresolved,
        "entity_type_review_count": len(entity_type_review),
        "invalid_change_count": len(invalid_changes),
        "final_commit_count": len(grouped),
        "final_method_change_count": method_count,
        "final_class_change_count": class_count,
        "final_total_change_count": final_total,
        "average_changes_per_commit": round(final_total / len(grouped), 4) if grouped else 0,
        "max_changes_in_one_commit": max((len(commit["changes"]) for commit in grouped), default=0),
        "commits_with_multiple_changes": sum(1 for commit in grouped if len(commit["changes"]) > 1),
        "changes_per_commit_distribution": dict(sorted(distribution.items(), key=lambda item: int(item[0]))),
        "per_project_change_count": dict(sorted(per_project.items())),
        "per_entity_type_count": dict(sorted(per_entity.items())),
        "issue_summary_source_counts": issue_source_counts,
        "javadoc_format_review_count": len(javadoc_review),
        "validation": validation,
    }
    return summary


def find_javadoc_format_review(changes: list[dict]) -> list[dict]:
    review: list[dict] = []
    for change in changes:
        for field in ("javadoc_before", "javadoc_after"):
            value = change[field]
            stripped = value.strip()
            reasons = []
            if "\ufffd" in value:
                reasons.append("replacement_character")
            if stripped.startswith("/**") and not stripped.endswith("*/"):
                reasons.append("unclosed_javadoc")
            if value.count("<") != value.count(">"):
                reasons.append("unbalanced_angle_brackets")
            if reasons:
                review.append(
                    {
                        "project_slug": change.get("_project_slug", ""),
                        "commit_hash": change["commit_hash"],
                        "source_sample_id": change.get("_source_sample_id", ""),
                        "field": field,
                        "reasons": reasons,
                    }
                )
    return review


def render_output_readme(summary: dict) -> str:
    return f"""# Merged Patch-Aware Javadoc Updating Dataset

This directory contains the locally merged and cleaned Java dataset for the
Patch-Aware Javadoc Updating task.

Input fields for each change are `issue_summary`, `code_before`, `code_after`,
and `javadoc_before`. The target field is `javadoc_after`.

## Sources

- Old accepted baseline: `final_dataset` ({summary['old_dataset_raw_change_count']} flat changes)
- New continuation dataset: `final_dataset_extra_3k` ({summary['new_dataset_raw_change_count']} flat changes)

The source datasets are not overwritten. Key source files are copied under
`source_backups/` before the merged outputs are written.

## Cleaning Rules

- Deduplicate by content fingerprint over `code_before`, `code_after`,
  `javadoc_before`, and `javadoc_after`.
- Remove only pure Javadoc formatting changes: whitespace, line wrapping,
  punctuation-only, and HTML formatting-only changes.
- Do not judge whether the code patch caused the Javadoc edit.
- Keep both method-level and class-level changes.
- Weak `issue_summary` values are repaired only from real project history
  available in local git caches. They are not generated or paraphrased.

## Two-Level Schema

`combined_by_commit.json` is grouped by commit:

```json
[
  {{
    "project_slug": "...",
    "repository_url": "...",
    "commit_hash": "...",
    "issue_summary": "...",
    "changes": [
      {{
        "change_index": 1,
        "entity_type": "method",
        "code_before": "...",
        "code_after": "...",
        "javadoc_before": "...",
        "javadoc_after": "..."
      }}
    ]
  }}
]
```

`project_slug` and `repository_url` are preserved from the dataset directory
metadata so commits from different repositories cannot be accidentally merged.

## Final Counts

- Final commits: {summary['final_commit_count']}
- Final changes: {summary['final_total_change_count']}
- Method-level changes: {summary['final_method_change_count']}
- Class-level changes: {summary['final_class_change_count']}
- Commits with multiple changes: {summary['commits_with_multiple_changes']}
- Average changes per commit: {summary['average_changes_per_commit']}
- Max changes in one commit: {summary['max_changes_in_one_commit']}

## Cleaning Statistics

- Merged raw changes: {summary['merged_raw_change_count']}
- Removed duplicate changes: {summary['duplicate_change_count']}
- Removed format-only changes: {summary['format_only_removed_count']}
- Weak issue summaries detected: {summary['weak_issue_detected_count']}
- Weak issue summaries resolved: {summary['weak_issue_resolved_count']}
- Weak issue summaries unresolved: {summary['weak_issue_unresolved_count']}
- Entity-type review changes: {summary['entity_type_review_count']}
- Invalid changes: {summary['invalid_change_count']}
- Validation passed: {summary['validation']['passed']}

## Files

- `combined_raw_flat.json`
- `combined_cleaned_flat.json`
- `combined_by_commit.json`
- `removed_duplicates.json`
- `removed_format_only.json`
- `unresolved_issue_summary.json`
- `entity_type_review.json`
- `invalid_changes.json`
- `javadoc_format_review.json`
- `summary.json`
- `summary.csv`
- `validation_report.json`

## Re-run

```powershell
python scripts/merge_and_clean_datasets.py `
  --old-dir final_dataset `
  --new-dir final_dataset_extra_3k `
  --output-dir final_dataset_merged
```
"""


def _write_summary_csv(path: Path, summary: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in summary.items():
            if isinstance(value, (dict, list)):
                writer.writerow([key, json.dumps(value, ensure_ascii=False, sort_keys=True)])
            else:
                writer.writerow([key, value])


def _backup_sources(paths: DatasetPaths) -> None:
    backup_root = paths.output_dir / "source_backups"
    for dataset_dir in (paths.old_dir, paths.new_dir):
        target = backup_root / dataset_dir.name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for file_name in ("combined_samples.json", "summary.csv", "README.md", "validation_report.json"):
            source = dataset_dir / file_name
            if source.exists():
                shutil.copy2(source, target / file_name)


def _require_dataset(dataset_dir: Path, expected_count: int | None = None) -> None:
    combined = dataset_dir / "combined_samples.json"
    if not combined.exists():
        raise FileNotFoundError(f"Dataset not found: {combined}")
    samples = _read_json(combined, [])
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"Dataset has no combined samples: {combined}")
    if expected_count is not None and len(samples) != expected_count:
        raise ValueError(
            f"Unexpected sample count for {dataset_dir}: expected {expected_count}, got {len(samples)}"
        )


def _audit_change(change: dict) -> dict:
    return {
        "source_dataset": change.get("_dataset", ""),
        "project_slug": change.get("_project_slug", ""),
        "repository_url": change.get("_repository_url", ""),
        "source_sample_id": change.get("_source_sample_id", ""),
        "commit_hash": change.get("commit_hash", ""),
        "issue_summary": change.get("issue_summary", ""),
    }


def _redacted_change(change: dict) -> dict:
    audit = _audit_change(change)
    audit["entity_type"] = change.get("_entity_type", "")
    return audit


def _resolve(root_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else root_dir / path


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
