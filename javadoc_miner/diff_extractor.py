from .git_repo import GitRepo
from .models import FileChange
from .text_utils import is_code_diff_line, is_javadoc_diff_line, is_target_java_path


def parse_changed_paths(name_status: str) -> list[str]:
    paths: list[str] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        path = parts[-1]
        if status.startswith("D"):
            continue
        if is_target_java_path(path):
            paths.append(path)
    return paths


def commit_has_javadoc_and_code_changes(patch: str) -> bool:
    has_javadoc = False
    has_code = False
    for line in patch.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        if is_javadoc_diff_line(line):
            has_javadoc = True
        if is_code_diff_line(line):
            has_code = True
        if has_javadoc and has_code:
            return True
    return False


def extract_file_changes(repo: GitRepo, commit_hash: str) -> list[FileChange]:
    changed_paths = parse_changed_paths(repo.show_name_status(commit_hash))
    patch = repo.show_commit_patch(commit_hash)
    changes: list[FileChange] = []
    for path in changed_paths:
        old_content = repo.show_file(f"{commit_hash}^", path)
        new_content = repo.show_file(commit_hash, path)
        changes.append(
            FileChange(
                path=path,
                old_content=old_content,
                new_content=new_content,
                patch=patch,
            )
        )
    return changes
