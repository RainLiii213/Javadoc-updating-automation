from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MinerConfig:
    repo_url: str
    cache_dir: Path = Path(".cache/repos")
    output_dir: Path = Path("dataset")
    max_commits: int = 1000
    max_samples: int = 100
    full_history: bool = False
    min_quality: str = "B"
    force_refresh: bool = False
