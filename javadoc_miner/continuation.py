import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .cli import mine_repository
from .config import MinerConfig
from .git_repo import GitCommandError
from .repositories import DEFAULT_JAVA_REPOSITORIES, RepositorySpec
from .text_utils import normalize_javadoc_for_semantic_compare
from .validation import scan_java_structure, validate_code_snippet


FINAL_SAMPLE_FIELDS = (
    "commit_hash",
    "issue_summary",
    "code_before",
    "code_after",
    "javadoc_before",
    "javadoc_after",
)
SUMMARY_FIELDS = (
    "project_slug",
    "repository_url",
    "retained_samples",
    "source_folder",
    "final_folder",
    "commits_scanned",
    "candidate_samples_found",
    "filtered_samples",
    "discarded_truncated_code_context",
    "moved_to_review",
    "discarded_weak_inheritdoc",
    "issue_summary_fallbacks",
    "duplicate_against_baseline",
    "duplicate_inside_new_dataset",
    "complete_history",
    "stop_reason",
)
PROJECT_SAMPLE_FIELDS = ("sample_id", "commit_hash", "issue_summary")
DANGLING_SUMMARY_WORDS = {"by", "to", "for", "with", "of", "in", "on", "and", "or", "from", "into"}


@dataclass(frozen=True)
class ContinuationConfig:
    root_dir: Path = Path(".")
    baseline_dir: Path = Path("final_dataset")
    output_dir: Path = Path("final_dataset_extra_3k")
    cache_dir: Path = Path(".cache/repos")
    target_new: int = 3000
    start_from: str = ""
    max_commits_per_repo: int | None = None
    max_repos: int | None = None
    dry_run: bool = False
    force_refresh: bool = False


@dataclass(frozen=True)
class ContinuationPlan:
    baseline_count: int
    baseline_per_project: dict[str, int]
    completed_repositories: list[str]
    repositories_to_scan: list[str]
    output_dir: Path
    target_new: int
    stop_conditions: tuple[str, str]


def mine_continuation_dataset(
    config: ContinuationConfig,
    repositories: Iterable[RepositorySpec] | None = None,
) -> list[dict]:
    specs = list(repositories or DEFAULT_JAVA_REPOSITORIES)
    root_dir = config.root_dir
    baseline_dir = _resolve_from_root(root_dir, config.baseline_dir)
    output_dir = _resolve_from_root(root_dir, config.output_dir)
    cache_dir = _resolve_from_root(root_dir, config.cache_dir)
    _require_baseline(baseline_dir)

    plan = build_continuation_plan(config, specs)
    print_continuation_plan(plan)

    selected_specs = _selected_repositories(specs, config.start_from, config.max_repos)
    if not config.start_from:
        selected_specs = _start_at_first_incomplete_or_unscanned(selected_specs, baseline_dir)
    if config.dry_run:
        return []

    refresh_continuation_dataset(output_dir, baseline_dir)
    completed: list[dict] = []
    baseline_keys = sample_keys_for_dataset(baseline_dir)
    baseline_counts = project_sample_counts(baseline_dir)
    baseline_metadata = project_metadata_by_slug(baseline_dir)

    for spec in selected_specs:
        refresh_continuation_dataset(output_dir, baseline_dir)
        current_total = dataset_sample_count(output_dir)
        if current_total >= config.target_new:
            print(f"Target reached: {current_total}/{config.target_new} new samples. Stopping.")
            break

        baseline_project_metadata = baseline_metadata.get(spec.slug, {})
        if baseline_project_metadata.get("complete_history"):
            print(f"Skipping {spec.name}: old baseline metadata marks full history complete.")
            completed.append(_skip_metadata(spec, output_dir, "old_baseline_complete"))
            continue

        extra_metadata = _read_metadata(output_dir / spec.slug / "metadata.json")
        if extra_metadata.get("complete_history"):
            print(f"Skipping {spec.name}: continuation output already has complete history.")
            completed.append(_skip_metadata(spec, output_dir, "continuation_complete"))
            continue

        other_total = current_total - project_sample_counts(output_dir).get(spec.slug, 0)
        remaining = config.target_new - other_total
        if remaining <= 0:
            print(f"Target reached without re-mining {spec.name}.")
            break

        skip_commits = int(baseline_project_metadata.get("commits_scanned", 0) or 0)
        raw_limit = remaining if skip_commits > 0 else remaining + baseline_counts.get(spec.slug, 0)
        in_progress = root_dir / f"dataset_{spec.slug}_extra_3k_in_progress"
        miner_config = MinerConfig(
            repo_url=spec.url,
            cache_dir=cache_dir,
            output_dir=in_progress,
            max_commits=config.max_commits_per_repo or 1000,
            max_samples=raw_limit,
            full_history=config.max_commits_per_repo is None,
            force_refresh=config.force_refresh,
            skip_commits=skip_commits,
            fetch_existing=False,
            progress_interval=100,
        )
        print(
            f"Mining {spec.name} for continuation "
            f"(need up to {remaining} new samples, raw limit {raw_limit}, "
            f"skipping {skip_commits} previously scanned commits)..."
        )
        try:
            raw_samples = mine_repository(miner_config)
        except (GitCommandError, OSError) as error:
            print(f"Failed to mine {spec.name}: {error}")
            continue

        stats = _read_json(in_progress / "stats.json", {})
        source_dir = _next_source_dir(root_dir, spec.slug, len(raw_samples))
        _replace_directory(in_progress, source_dir)

        existing_new_keys = sample_keys_for_dataset(output_dir, exclude_project=spec.slug)
        filtered, duplicate_baseline, duplicate_new = _filter_new_samples(
            spec.slug,
            [sample.to_json_dict() for sample in raw_samples],
            baseline_keys,
            existing_new_keys,
            max_samples=remaining,
        )
        metadata = _project_metadata(
            spec=spec,
            retained_samples=len(filtered),
            source_folder=source_dir.name,
            stats=stats,
            duplicate_baseline=duplicate_baseline,
            duplicate_new=duplicate_new,
            complete_history=bool(stats.get("history_complete", False)),
            final_dir_name=output_dir.name,
        )
        metadata["skipped_previously_scanned_commits"] = skip_commits
        if metadata["complete_history"]:
            metadata["stop_reason"] = "full_history_scanned"
        elif config.max_commits_per_repo is not None:
            metadata["stop_reason"] = f"max_commits_per_repo={config.max_commits_per_repo} reached"
        elif other_total + len(filtered) >= config.target_new:
            metadata["stop_reason"] = f"target_new={config.target_new} reached"
        else:
            metadata["stop_reason"] = "history_incomplete"

        _write_json(source_dir / "continuation_metadata.json", metadata)
        _write_project_samples(output_dir / spec.slug, filtered, metadata)
        refresh_continuation_dataset(output_dir, baseline_dir)
        current_total = dataset_sample_count(output_dir)
        completed.append(metadata)
        _print_repository_report(spec.name, metadata, current_total, project_sample_count_sum(baseline_dir))

    refresh_continuation_dataset(output_dir, baseline_dir)
    print(f"Continuation dataset contains {dataset_sample_count(output_dir)} new samples.")
    return completed


def build_continuation_plan(
    config: ContinuationConfig,
    repositories: Iterable[RepositorySpec] | None = None,
) -> ContinuationPlan:
    specs = list(repositories or DEFAULT_JAVA_REPOSITORIES)
    root_dir = config.root_dir
    baseline_dir = _resolve_from_root(root_dir, config.baseline_dir)
    output_dir = _resolve_from_root(root_dir, config.output_dir)
    _require_baseline(baseline_dir)
    baseline_counts = project_sample_counts(baseline_dir)
    metadata = project_metadata_by_slug(baseline_dir)
    selected_specs = _selected_repositories(specs, config.start_from, config.max_repos)
    if not config.start_from:
        selected_specs = _start_at_first_incomplete_or_unscanned(selected_specs, baseline_dir)
    completed = [
        spec.name
        for spec in specs
        if metadata.get(spec.slug, {}).get("complete_history")
    ]
    to_scan = [
        spec.name
        for spec in selected_specs
        if not metadata.get(spec.slug, {}).get("complete_history")
    ]
    return ContinuationPlan(
        baseline_count=dataset_sample_count(baseline_dir),
        baseline_per_project=baseline_counts,
        completed_repositories=completed,
        repositories_to_scan=to_scan,
        output_dir=output_dir,
        target_new=config.target_new,
        stop_conditions=(
            f"new continuation dataset reaches {config.target_new} samples",
            "all repositories in the configured Java list have been scanned",
        ),
    )


def print_continuation_plan(plan: ContinuationPlan) -> None:
    print("Continuation plan")
    print(f"- old baseline sample count: {plan.baseline_count}")
    print("- old per-project sample counts:")
    for slug, count in sorted(plan.baseline_per_project.items()):
        print(f"  - {slug}: {count}")
    print("- repositories already completed:")
    for name in plan.completed_repositories or ["(none)"]:
        print(f"  - {name}")
    print("- repositories still to scan:")
    for name in plan.repositories_to_scan or ["(none)"]:
        print(f"  - {name}")
    print(f"- new output folder: {plan.output_dir}")
    print(f"- new target count: {plan.target_new} additional samples")
    print("- stop conditions:")
    for condition in plan.stop_conditions:
        print(f"  - {condition}")


def refresh_continuation_dataset(output_dir: Path, baseline_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_keys = sample_keys_for_dataset(baseline_dir)
    combined: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    rows: list[dict] = []

    for project_dir in sorted(path for path in output_dir.iterdir() if path.is_dir()):
        combined_path = project_dir / "combined_samples.json"
        if not combined_path.exists():
            continue
        raw_samples = _read_json(combined_path, [])
        metadata = _read_metadata(project_dir / "metadata.json")
        clean: list[dict] = []
        duplicate_baseline = 0
        duplicate_new = 0
        for raw_sample in raw_samples if isinstance(raw_samples, list) else []:
            sample = _clean_sample(raw_sample)
            if sample is None:
                continue
            key = sample_key(project_dir.name, sample)
            if key in baseline_keys:
                duplicate_baseline += 1
                continue
            if key in seen:
                duplicate_new += 1
                continue
            seen.add(key)
            clean.append(sample)
            combined.append(sample)

        metadata["retained_samples"] = len(clean)
        metadata["final_folder"] = f"{output_dir.name}/{project_dir.name}"
        metadata["duplicate_against_baseline"] = max(
            int(metadata.get("duplicate_against_baseline", 0) or 0),
            duplicate_baseline,
        )
        metadata["duplicate_inside_new_dataset"] = max(
            int(metadata.get("duplicate_inside_new_dataset", 0) or 0),
            duplicate_new,
        )
        if "project_slug" not in metadata:
            metadata["project_slug"] = project_dir.name
        if "repository_url" not in metadata:
            metadata["repository_url"] = ""
        if "source_folder" not in metadata:
            metadata["source_folder"] = ""
        if "complete_history" not in metadata:
            metadata["complete_history"] = False
        if "stop_reason" not in metadata:
            metadata["stop_reason"] = "history_incomplete"
        _write_project_samples(project_dir, clean, metadata)
        rows.append(metadata)

    _write_json(output_dir / "combined_samples.json", combined)
    _write_project_summary(output_dir / "summary.csv", rows)
    _write_json(output_dir / "validation_report.json", validate_continuation_dataset(output_dir, baseline_dir))
    (output_dir / "README.md").write_text(
        _continuation_readme(rows, len(combined), baseline_dir),
        encoding="utf-8",
    )
    return rows


def validate_continuation_dataset(output_dir: Path, baseline_dir: Path) -> dict:
    baseline_keys = sample_keys_for_dataset(baseline_dir)
    per_project: dict[str, int] = {}
    schema_failures: list[str] = []
    empty_field_failures: list[str] = []
    duplicate_inside_new: list[str] = []
    duplicate_against_baseline: list[str] = []
    dangling_issue_summaries: list[dict] = []
    invalid_code: list[dict] = []
    identical_code: list[str] = []
    identical_javadoc: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for project_dir in sorted(path for path in output_dir.iterdir() if path.is_dir()):
        combined_path = project_dir / "combined_samples.json"
        if not combined_path.exists():
            continue
        samples = _read_json(combined_path, [])
        if not isinstance(samples, list):
            schema_failures.append(f"{project_dir.name}:combined_samples_not_list")
            continue
        per_project[project_dir.name] = len(samples)
        for index, raw_sample in enumerate(samples, start=1):
            sample_id = f"{project_dir.name}/sample_{index:04d}"
            if not isinstance(raw_sample, dict) or set(raw_sample) != set(FINAL_SAMPLE_FIELDS):
                schema_failures.append(sample_id)
                continue
            if any(not isinstance(raw_sample[field], str) or not raw_sample[field].strip() for field in FINAL_SAMPLE_FIELDS):
                empty_field_failures.append(sample_id)
            sample = {field: raw_sample[field] for field in FINAL_SAMPLE_FIELDS}
            key = sample_key(project_dir.name, sample)
            if key in baseline_keys:
                duplicate_against_baseline.append(sample_id)
            if key in seen:
                duplicate_inside_new.append(sample_id)
            seen.add(key)
            if _is_dangling_issue_summary(sample["issue_summary"]):
                dangling_issue_summaries.append(
                    {"sample": sample_id, "issue_summary": sample["issue_summary"]}
                )
            if sample["code_before"] == sample["code_after"]:
                identical_code.append(sample_id)
            before_doc = " ".join(sample["javadoc_before"].split())
            after_doc = " ".join(sample["javadoc_after"].split())
            if before_doc == after_doc:
                identical_javadoc.append(sample_id)
            for field in ("code_before", "code_after"):
                reason = _basic_code_problem(sample[field])
                if reason:
                    invalid_code.append({"sample": sample_id, "field": field, "reason": reason})

    report = {
        "total_samples": sum(per_project.values()),
        "project_sample_total": sum(per_project.values()),
        "per_project": per_project,
        "schema_failures": schema_failures,
        "empty_field_failures": empty_field_failures,
        "duplicate_count": len(duplicate_inside_new),
        "duplicate_inside_new": duplicate_inside_new,
        "duplicate_against_baseline_count": len(duplicate_against_baseline),
        "duplicate_against_baseline": duplicate_against_baseline,
        "dangling_issue_summary_count": len(dangling_issue_summaries),
        "dangling_issue_summaries": dangling_issue_summaries,
        "truncated_or_invalid_code_count": len(invalid_code),
        "truncated_or_invalid_code": invalid_code,
        "identical_code_count": len(identical_code),
        "identical_code": identical_code,
        "identical_javadoc_after_whitespace_count": len(identical_javadoc),
        "identical_javadoc_after_whitespace": identical_javadoc,
    }
    report["passed"] = not any(
        [
            schema_failures,
            empty_field_failures,
            duplicate_inside_new,
            duplicate_against_baseline,
            dangling_issue_summaries,
            invalid_code,
            identical_code,
            identical_javadoc,
        ]
    )
    return report


def sample_keys_for_dataset(dataset_dir: Path, exclude_project: str = "") -> set[tuple[str, ...]]:
    keys: set[tuple[str, ...]] = set()
    if not dataset_dir.exists():
        return keys
    for project_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir()):
        if project_dir.name == exclude_project:
            continue
        samples = _read_json(project_dir / "combined_samples.json", [])
        if not isinstance(samples, list):
            continue
        for raw_sample in samples:
            sample = _clean_sample(raw_sample)
            if sample is not None:
                keys.add(sample_key(project_dir.name, sample))
    return keys


def sample_key(project_slug: str, sample: dict) -> tuple[str, ...]:
    return (project_slug, *(str(sample[field]) for field in FINAL_SAMPLE_FIELDS))


def dataset_sample_count(dataset_dir: Path) -> int:
    combined = _read_json(dataset_dir / "combined_samples.json", [])
    return len(combined) if isinstance(combined, list) else project_sample_count_sum(dataset_dir)


def project_sample_count_sum(dataset_dir: Path) -> int:
    return sum(project_sample_counts(dataset_dir).values())


def project_sample_counts(dataset_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not dataset_dir.exists():
        return counts
    for project_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir()):
        samples = _read_json(project_dir / "combined_samples.json", [])
        if isinstance(samples, list):
            counts[project_dir.name] = len(samples)
    return counts


def project_metadata_by_slug(dataset_dir: Path) -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    if not dataset_dir.exists():
        return metadata
    for project_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir()):
        value = _read_metadata(project_dir / "metadata.json")
        if value:
            metadata[project_dir.name] = value
    return metadata


def _filter_new_samples(
    project_slug: str,
    samples: list[dict],
    baseline_keys: set[tuple[str, ...]],
    existing_new_keys: set[tuple[str, ...]],
    max_samples: int,
) -> tuple[list[dict], int, int]:
    filtered: list[dict] = []
    local_seen: set[tuple[str, ...]] = set()
    duplicate_baseline = 0
    duplicate_new = 0
    for raw_sample in samples:
        sample = _clean_sample(raw_sample)
        if sample is None:
            continue
        key = sample_key(project_slug, sample)
        if key in baseline_keys:
            duplicate_baseline += 1
            continue
        if key in existing_new_keys or key in local_seen:
            duplicate_new += 1
            continue
        if len(filtered) >= max_samples:
            break
        local_seen.add(key)
        filtered.append(sample)
    return filtered, duplicate_baseline, duplicate_new


def _write_project_samples(project_dir: Path, samples: list[dict], metadata: dict) -> None:
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for index, sample in enumerate(samples, start=1):
        sample_id = f"sample_{index:04d}"
        (project_dir / f"{sample_id}.json").write_text(
            json.dumps(sample, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            {
                "sample_id": sample_id,
                "commit_hash": sample["commit_hash"],
                "issue_summary": sample["issue_summary"],
            }
        )
    with (project_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROJECT_SAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _write_json(project_dir / "combined_samples.json", samples)
    _write_json(project_dir / "metadata.json", metadata)


def _write_project_summary(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def _project_metadata(
    spec: RepositorySpec,
    retained_samples: int,
    source_folder: str,
    stats: dict,
    duplicate_baseline: int,
    duplicate_new: int,
    complete_history: bool,
    final_dir_name: str,
) -> dict:
    return {
        "project_slug": spec.slug,
        "repository_name": spec.name,
        "repository_url": spec.url,
        "retained_samples": retained_samples,
        "source_folder": source_folder,
        "final_folder": f"{final_dir_name}/{spec.slug}",
        "mined_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commits_scanned": stats.get("total_commits_scanned", 0),
        "candidate_samples_found": stats.get("candidate_samples_found", 0),
        "filtered_samples": stats.get("samples_filtered", 0),
        "discarded_truncated_code_context": stats.get("discarded_truncated_code_context", 0),
        "moved_to_review": stats.get("moved_to_review", 0),
        "discarded_weak_inheritdoc": stats.get("discarded_weak_inheritdoc", 0),
        "issue_summary_fallbacks": stats.get("issue_summary_fallbacks", 0),
        "duplicate_against_baseline": duplicate_baseline,
        "duplicate_inside_new_dataset": duplicate_new,
        "complete_history": complete_history,
        "stop_reason": "full_history_scanned" if complete_history else "history_incomplete",
    }


def _skip_metadata(spec: RepositorySpec, output_dir: Path, stop_reason: str) -> dict:
    return {
        "project_slug": spec.slug,
        "repository_name": spec.name,
        "repository_url": spec.url,
        "retained_samples": 0,
        "source_folder": "",
        "final_folder": f"{output_dir.name}/{spec.slug}",
        "commits_scanned": 0,
        "candidate_samples_found": 0,
        "filtered_samples": 0,
        "discarded_truncated_code_context": 0,
        "moved_to_review": 0,
        "discarded_weak_inheritdoc": 0,
        "issue_summary_fallbacks": 0,
        "duplicate_against_baseline": 0,
        "duplicate_inside_new_dataset": 0,
        "complete_history": True,
        "stop_reason": stop_reason,
    }


def _print_repository_report(
    repository_name: str,
    metadata: dict,
    new_total: int,
    old_total: int,
) -> None:
    print(f"Repository report: {repository_name}")
    print(f"- status: {metadata.get('stop_reason', 'history_incomplete')}")
    print(f"- commits scanned: {metadata.get('commits_scanned', 0)}")
    print(f"- candidate samples found: {metadata.get('candidate_samples_found', 0)}")
    print(f"- retained high-quality samples: {metadata.get('retained_samples', 0)}")
    print(f"- discarded samples: {metadata.get('filtered_samples', 0)}")
    print(f"- duplicate count against old baseline: {metadata.get('duplicate_against_baseline', 0)}")
    print(f"- duplicate count inside new dataset: {metadata.get('duplicate_inside_new_dataset', 0)}")
    print(f"- invalid/truncated code count: {metadata.get('discarded_truncated_code_context', 0)}")
    print(f"- weak inheritDoc-only discard count: {metadata.get('discarded_weak_inheritdoc', 0)}")
    print(f"- issue summary fallback count: {metadata.get('issue_summary_fallbacks', 0)}")
    print(f"- new continuation dataset count so far: {new_total}")
    print(f"- optional total combined count: {old_total + new_total}")


def _continuation_readme(rows: list[dict], total: int, baseline_dir: Path) -> str:
    sources = "\n".join(
        f"- `{row['project_slug']}`: {row['retained_samples']} samples"
        for row in rows
    ) or "- No continuation samples yet."
    return f"""# Extra 3k Continuation Dataset

This directory stores only new Patch-Aware Javadoc Updating samples that are
not present in the frozen baseline at `{baseline_dir}`.

Current new continuation sample count: **{total}**.

Every training sample JSON object contains exactly six fields:

```json
{{
  "commit_hash": "...",
  "issue_summary": "...",
  "code_before": "...",
  "code_after": "...",
  "javadoc_before": "...",
  "javadoc_after": "..."
}}
```

The old baseline is not copied into this directory. Repository metadata and
duplicate counts are recorded separately in `summary.csv`, per-project
`metadata.json` files, and `validation_report.json`.

## Sources

{sources}
"""


def _basic_code_problem(code: str) -> str:
    if not code.strip():
        return "empty_code"
    if code.count("/**") > code.count("*/"):
        return "unclosed_javadoc"
    scan = scan_java_structure(code)
    if scan.unclosed_block_comment:
        return "unclosed_comment"
    if scan.unclosed_string:
        return "unclosed_string"
    if scan.brace_balance != 0 or scan.minimum_brace_balance < 0:
        return "unbalanced_braces"
    method_reason = validate_code_snippet(code, "method")
    class_reason = validate_code_snippet(code, "class")
    if method_reason and class_reason:
        return method_reason
    return ""


def _is_dangling_issue_summary(summary: str) -> bool:
    words = summary.lower().strip().split()
    return bool(words and words[-1].strip(".,;:!?") in DANGLING_SUMMARY_WORDS)


def _clean_sample(sample: object) -> dict | None:
    if not isinstance(sample, dict):
        return None
    if not all(field in sample for field in FINAL_SAMPLE_FIELDS):
        return None
    clean = {field: sample[field] for field in FINAL_SAMPLE_FIELDS}
    if any(not isinstance(value, str) for value in clean.values()):
        return None
    before = normalize_javadoc_for_semantic_compare(clean["javadoc_before"])
    after = normalize_javadoc_for_semantic_compare(clean["javadoc_after"])
    if before == after:
        return None
    return clean


def _selected_repositories(
    repositories: list[RepositorySpec],
    start_from: str,
    max_repos: int | None,
) -> list[RepositorySpec]:
    if start_from:
        start_index = next(
            (
                index
                for index, spec in enumerate(repositories)
                if start_from in {spec.name, spec.slug}
            ),
            None,
        )
        if start_index is None:
            raise ValueError(f"Unknown start repository: {start_from}")
        repositories = repositories[start_index:]
    if max_repos is not None:
        repositories = repositories[:max_repos]
    return repositories


def _start_at_first_incomplete_or_unscanned(
    repositories: list[RepositorySpec],
    baseline_dir: Path,
) -> list[RepositorySpec]:
    metadata = project_metadata_by_slug(baseline_dir)
    for index, spec in enumerate(repositories):
        if not metadata.get(spec.slug, {}).get("complete_history"):
            return repositories[index:]
    return []


def _next_source_dir(root_dir: Path, project_slug: str, raw_count: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return root_dir / f"dataset_{project_slug}_extra_3k_{raw_count}_{stamp}"


def _replace_directory(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    source.rename(target)


def _require_baseline(baseline_dir: Path) -> None:
    if not (baseline_dir / "combined_samples.json").exists():
        raise FileNotFoundError(f"baseline dataset not found at {baseline_dir}")
    if dataset_sample_count(baseline_dir) == 0:
        raise FileNotFoundError(f"baseline dataset at {baseline_dir} has no samples")


def _resolve_from_root(root_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else root_dir / path


def _read_metadata(path: Path) -> dict:
    value = _read_json(path, {})
    return value if isinstance(value, dict) else {}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
