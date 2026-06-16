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
from .repositories import DEFAULT_JAVA_REPOSITORIES, KNOWN_REPOSITORIES, RepositorySpec


FINAL_SAMPLE_FIELDS = (
    "commit_hash",
    "issue_summary",
    "code_before",
    "code_after",
    "javadoc_before",
    "javadoc_after",
)
PROJECT_SUMMARY_FIELDS = (
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
    "complete_history",
    "stop_reason",
)


@dataclass(frozen=True)
class MultiRepoConfig:
    root_dir: Path = Path(".")
    final_dir: Path = Path("final_dataset")
    cache_dir: Path = Path(".cache/repos")
    target_total: int = 1000
    start_from: str = ""
    max_commits_per_repo: int | None = None
    max_repos: int | None = None
    repo_list: str = "default_java"
    resume: bool = False
    dry_run: bool = False
    force_refresh: bool = False


def mine_multiple_repositories(
    config: MultiRepoConfig,
    repositories: Iterable[RepositorySpec] | None = None,
) -> list[dict]:
    specs = _selected_repositories(
        list(repositories or DEFAULT_JAVA_REPOSITORIES),
        config.start_from,
        config.max_repos,
    )
    final_dir = _resolve_from_root(config.root_dir, config.final_dir)
    cache_dir = _resolve_from_root(config.root_dir, config.cache_dir)
    current_total = final_sample_count(final_dir)

    if config.dry_run:
        _print_dry_run(config, specs, final_dir, current_total)
        return []

    refresh_final_dataset(final_dir, KNOWN_REPOSITORIES)
    current_total = final_sample_count(final_dir)
    completed: list[dict] = []

    for spec in specs:
        if current_total >= config.target_total:
            print(f"Target reached: {current_total}/{config.target_total}. Stopping.")
            break

        existing = _read_metadata(final_dir / spec.slug / "metadata.json")
        if existing and existing.get("complete_history"):
            print(f"Skipping {spec.name}: final output already exists.")
            continue

        remaining = config.target_total - current_total
        in_progress = config.root_dir / f"dataset_{spec.slug}_in_progress"
        miner_config = MinerConfig(
            repo_url=spec.url,
            cache_dir=cache_dir,
            output_dir=in_progress,
            max_commits=config.max_commits_per_repo or 1000,
            max_samples=remaining,
            full_history=config.max_commits_per_repo is None,
            force_refresh=config.force_refresh,
        )
        print(f"Mining {spec.name} ({spec.url})...")
        try:
            samples = mine_repository(miner_config)
        except (GitCommandError, OSError) as error:
            print(f"Failed to mine {spec.name}: {error}")
            continue

        stats = _read_json(in_progress / "stats.json", {})
        source_dir = config.root_dir / f"dataset_{spec.slug}_{len(samples)}"
        _replace_directory(in_progress, source_dir)
        metadata = _project_metadata(
            spec=spec,
            retained_samples=len(samples),
            source_folder=source_dir.name,
            stats=stats,
            complete_history=bool(stats.get("history_complete", False)),
        )
        if metadata["complete_history"]:
            metadata["stop_reason"] = "full_history_scanned"
        elif config.max_commits_per_repo is not None:
            metadata["stop_reason"] = f"max_commits_per_repo={config.max_commits_per_repo} reached"
        elif len(samples) >= remaining:
            metadata["stop_reason"] = f"target_total={config.target_total} reached"
        else:
            metadata["stop_reason"] = "history_incomplete"
        if config.max_commits_per_repo is not None:
            metadata["final_folder"] = ""
        _write_json(source_dir / "metadata.json", metadata)

        if config.max_commits_per_repo is not None:
            completed.append(metadata)
            print(
                f"Retained {len(samples)} bounded-test samples from {spec.name} in "
                f"{source_dir.name}; final dataset remains at {current_total}."
            )
            continue

        final_project_dir = final_dir / spec.slug
        if final_project_dir.exists():
            shutil.rmtree(final_project_dir)
        shutil.copytree(
            source_dir,
            final_project_dir,
            ignore=shutil.ignore_patterns("review_samples.json"),
        )
        _write_json(final_project_dir / "metadata.json", metadata)

        refresh_final_dataset(final_dir, KNOWN_REPOSITORIES)
        current_total = final_sample_count(final_dir)
        completed.append(metadata)
        print(f"Retained {len(samples)} samples from {spec.name}; final total is {current_total}.")

    print(f"Final dataset contains {current_total} samples.")
    return completed


def refresh_final_dataset(
    final_dir: Path,
    repositories: Iterable[RepositorySpec] = KNOWN_REPOSITORIES,
) -> list[dict]:
    final_dir.mkdir(parents=True, exist_ok=True)
    known = {spec.slug: spec for spec in repositories}
    combined: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    metadata_rows: list[dict] = []

    for project_dir in sorted(path for path in final_dir.iterdir() if path.is_dir()):
        combined_path = project_dir / "combined_samples.json"
        if not combined_path.exists():
            continue
        project_samples = _read_json(combined_path, [])
        clean_samples = [_clean_sample(sample) for sample in project_samples]
        clean_samples = [sample for sample in clean_samples if sample is not None]
        for sample in clean_samples:
            key = (project_dir.name, *(sample[field] for field in FINAL_SAMPLE_FIELDS))
            if key not in seen:
                seen.add(key)
                combined.append(sample)

        metadata_path = project_dir / "metadata.json"
        metadata = _read_metadata(metadata_path)
        spec = known.get(project_dir.name)
        inferred = _project_metadata(
            spec=spec or RepositorySpec(project_dir.name, ""),
            retained_samples=len(clean_samples),
            source_folder=_find_source_folder(final_dir.parent, project_dir.name),
            stats={},
            complete_history=True,
        )
        inferred.update(metadata)
        metadata = inferred
        if metadata.get("complete_history"):
            metadata["stop_reason"] = "full_history_scanned"
        elif metadata.get("stop_reason") in {"", "full_history_scanned", None}:
            metadata["stop_reason"] = "history_incomplete"
        metadata["retained_samples"] = len(clean_samples)
        metadata["final_folder"] = f"{final_dir.name}/{project_dir.name}"
        _write_json(metadata_path, metadata)
        metadata_rows.append(metadata)

    _write_json(final_dir / "combined_samples.json", combined)
    _write_project_summary(final_dir / "summary.csv", metadata_rows)
    (final_dir / "README.md").write_text(
        _final_dataset_readme(metadata_rows, len(combined)),
        encoding="utf-8",
    )
    return metadata_rows


def final_sample_count(final_dir: Path) -> int:
    combined = _read_json(final_dir / "combined_samples.json", [])
    return len(combined) if isinstance(combined, list) else 0


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


def _print_dry_run(
    config: MultiRepoConfig,
    repositories: list[RepositorySpec],
    final_dir: Path,
    current_total: int,
) -> None:
    print(f"Dry run: final dataset currently contains {current_total} samples.")
    for spec in repositories:
        metadata = _read_metadata(final_dir / spec.slug / "metadata.json")
        if metadata and metadata.get("complete_history"):
            action = "skip existing final output"
        else:
            limit = config.max_commits_per_repo or "full history"
            action = f"mine up to {limit} commits"
        print(f"- {spec.name}: {action}")


def _project_metadata(
    spec: RepositorySpec,
    retained_samples: int,
    source_folder: str,
    stats: dict,
    complete_history: bool,
) -> dict:
    return {
        "project_slug": spec.slug,
        "repository_name": spec.name,
        "repository_url": spec.url,
        "retained_samples": retained_samples,
        "source_folder": source_folder,
        "final_folder": f"final_dataset/{spec.slug}",
        "mined_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commits_scanned": stats.get("total_commits_scanned", 0),
        "candidate_samples_found": stats.get("candidate_samples_found", 0),
        "filtered_samples": stats.get("samples_filtered", 0),
        "discarded_truncated_code_context": stats.get(
            "discarded_truncated_code_context",
            0,
        ),
        "moved_to_review": stats.get("moved_to_review", 0),
        "discarded_weak_inheritdoc": stats.get("discarded_weak_inheritdoc", 0),
        "issue_summary_fallbacks": stats.get("issue_summary_fallbacks", 0),
        "complete_history": complete_history,
        "stop_reason": "full_history_scanned" if complete_history else "history_incomplete",
    }


def _clean_sample(sample: object) -> dict | None:
    if not isinstance(sample, dict) or not all(field in sample for field in FINAL_SAMPLE_FIELDS):
        return None
    return {field: sample[field] for field in FINAL_SAMPLE_FIELDS}


def _write_project_summary(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROJECT_SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PROJECT_SUMMARY_FIELDS})


def _find_source_folder(root_dir: Path, project_slug: str) -> str:
    matches = sorted(
        path
        for path in root_dir.glob(f"dataset_{project_slug}_*")
        if "_backup_full_context" not in path.name
    )
    return matches[-1].name if matches else ""


def _replace_directory(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    source.rename(target)


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


def _final_dataset_readme(rows: list[dict], total: int) -> str:
    sources = "\n".join(
        f"- `{row['project_slug']}`: {row['retained_samples']} samples"
        for row in rows
    ) or "- No accepted sources yet."
    return f"""# Final Dataset / 最终数据集

## 中文

此目录保存通过高精度筛选的 Patch-Aware Javadoc Updating 样本。
当前累计样本数：**{total}**。

每个项目保存在独立子目录中，`combined_samples.json` 汇总全部项目，
`summary.csv` 保存项目来源和简单挖掘统计。样本 JSON 始终只包含六个任务字段。

## English

This directory stores high-precision Patch-Aware Javadoc Updating samples.
Current cumulative sample count: **{total}**.

Each repository has its own subdirectory. `combined_samples.json` aggregates
all repositories, and `summary.csv` records source and simple mining metadata.
Sample JSON objects always contain only the six task fields.

Method-level samples contain complete methods or constructors. Class-level
samples contain a structurally complete class context. Invalid or arbitrarily
truncated code is never promoted to this directory.

Repositories whose metadata has `complete_history: false` stopped before their
full history was exhausted. Consult `stop_reason` for the exact reason.

## Sources

{sources}
"""
