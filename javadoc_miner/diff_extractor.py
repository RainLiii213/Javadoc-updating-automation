import difflib

from .git_repo import GitRepo
from .models import EntityDoc, FileChange
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


def build_entity_patch(
    file_change: FileChange,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
    context_lines: int = 3,
) -> str:
    old_lines = _entity_window(file_change.old_content or "", old_entity, context_lines)
    new_lines = _entity_window(file_change.new_content or "", new_entity, context_lines)
    old_start = _window_start_line(old_entity, context_lines)
    new_start = _window_start_line(new_entity, context_lines)
    old_header = f"a/{file_change.path}"
    new_header = f"b/{file_change.path}"
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_header,
        tofile=new_header,
        fromfiledate="",
        tofiledate="",
        n=context_lines,
        lineterm="",
    )
    patch_lines = [
        f"diff --git {old_header} {new_header}",
        *_with_adjusted_hunk_headers(list(diff), old_start, new_start),
    ]
    return "\n".join(patch_lines).strip()


def entity_code_changed(
    file_change: FileChange,
    old_entity: EntityDoc | None,
    new_entity: EntityDoc | None,
) -> bool:
    if old_entity is None or new_entity is None:
        return old_entity is not None or new_entity is not None
    old_code = _entity_code_without_javadoc(file_change.old_content or "", old_entity)
    new_code = _entity_code_without_javadoc(file_change.new_content or "", new_entity)
    return old_code != new_code


def _entity_window(source: str, entity: EntityDoc | None, context_lines: int) -> list[str]:
    if entity is None:
        return []
    lines = source.splitlines()
    start = max(1, entity.start_line - context_lines)
    end = min(len(lines), entity.code_end_line)
    return lines[start - 1 : end]


def _window_start_line(entity: EntityDoc | None, context_lines: int) -> int:
    if entity is None:
        return 1
    return max(1, entity.start_line - context_lines)


def _entity_code_without_javadoc(source: str, entity: EntityDoc) -> str:
    lines = source.splitlines()
    code_lines = lines[entity.code_start_line - 1 : entity.code_end_line]
    return "\n".join(line.rstrip() for line in code_lines).strip()


def _with_adjusted_hunk_headers(diff_lines: list[str], old_start: int, new_start: int) -> list[str]:
    adjusted: list[str] = []
    for line in diff_lines:
        if line.startswith(("--- ", "+++ ")):
            adjusted.append(line)
            continue
        if line.startswith("@@ "):
            adjusted.append(_adjust_hunk_header(line, old_start, new_start))
            continue
        adjusted.append(line)
    return adjusted


def _adjust_hunk_header(header: str, old_start: int, new_start: int) -> str:
    parts = header.split(" ")
    if len(parts) < 3:
        return header
    parts[1] = _adjust_range(parts[1], old_start)
    parts[2] = _adjust_range(parts[2], new_start)
    return " ".join(parts)


def _adjust_range(range_text: str, base_start: int) -> str:
    sign = range_text[0]
    body = range_text[1:]
    if "," in body:
        start_text, length_text = body.split(",", 1)
        return f"{sign}{int(start_text) + base_start - 1},{length_text}"
    return f"{sign}{int(body) + base_start - 1}"
