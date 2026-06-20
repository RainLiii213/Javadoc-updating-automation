from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MinerConfig:
    repo_url: str
    cache_dir: Path = Path(".cache/repos")
    output_dir: Path = Path("dataset")
    max_commits: int = 1000
    max_samples: int = 50
    full_history: bool = False
    force_refresh: bool = False
    skip_commits: int = 0
    fetch_existing: bool = True
    progress_interval: int = 0
