import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


class GitCommandError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, repo_url: str, path: Path):
        self.repo_url = repo_url
        self.path = path

    @classmethod
    def clone_or_update(
        cls,
        repo_url: str,
        cache_dir: Path,
        force_refresh: bool = False,
        fetch_existing: bool = True,
    ) -> "GitRepo":
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / _cache_name(repo_url)
        if force_refresh and target.exists():
            shutil.rmtree(target)
        if target.exists():
            repo = cls(repo_url, target)
            if fetch_existing:
                repo.run_git(["fetch", "--all", "--tags", "--prune"])
            return repo
        _run(["git", "clone", repo_url, str(target)], cwd=None)
        return cls(repo_url, target)

    def run_git(self, args: list[str]) -> str:
        return _run(["git", *args], cwd=self.path)

    def iter_commits(self, full_history: bool, max_commits: int) -> list[str]:
        args = ["rev-list"]
        if not full_history:
            args.append("--first-parent")
        args.append("HEAD")
        commits = [line for line in self.run_git(args).splitlines() if line]
        if full_history:
            return commits
        return commits[:max_commits]

    def show_commit_patch(self, commit_hash: str) -> str:
        return self.run_git(["show", "--format=fuller", "--find-renames", "--patch", commit_hash])

    def show_name_status(self, commit_hash: str) -> str:
        return self.run_git(["diff-tree", "--no-commit-id", "--name-status", "-r", commit_hash])

    def show_file(self, commit_ref: str, path: str) -> str | None:
        try:
            return self.run_git(["show", f"{commit_ref}:{path}"])
        except GitCommandError:
            return None

    def commit_message(self, commit_hash: str) -> str:
        return self.run_git(["log", "--format=%B", "-n", "1", commit_hash]).strip()

    def repo_name(self) -> str:
        parsed = urlparse(self.repo_url)
        if parsed.scheme and parsed.netloc:
            path = parsed.path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return path
        return Path(self.repo_url).name

    def commit_url(self, commit_hash: str) -> str:
        parsed = urlparse(self.repo_url)
        if parsed.scheme and parsed.netloc:
            base = self.repo_url[:-4] if self.repo_url.endswith(".git") else self.repo_url
            return f"{base}/commit/{commit_hash}"
        return f"file://{self.path.as_posix()}/commit/{commit_hash}"


def _run(args: list[str], cwd: Path | None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise GitCommandError(message)
    return result.stdout


def _cache_name(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path.replace("/", "__")
    return Path(repo_url).name
