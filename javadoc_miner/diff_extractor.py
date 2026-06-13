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
        path = parts[-1]
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


def commit_has_javadoc_changes(patch: str) -> bool:
    for line in patch.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        if is_javadoc_diff_line(line):
            return True
    return False


def extract_file_changes(repo: GitRepo, commit_hash: str) -> list[FileChange]:
    changed_paths = parse_changed_paths(repo.show_name_status(commit_hash))
    changes: list[FileChange] = []
    for path in changed_paths:
        old_content = repo.show_file(f"{commit_hash}^", path)
        new_content = repo.show_file(commit_hash, path)
        changes.append(
            FileChange(
                path=path,
                old_content=old_content,
                new_content=new_content,
            )
        )
    return changes


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


def entity_code_text(source: str | None, entity: EntityDoc | None) -> str:
    if source is None or entity is None:
        return ""
    return _entity_code_without_javadoc(source, entity)


def bounded_entity_code_pair(
    file_change: FileChange,
    old_entity: EntityDoc,
    new_entity: EntityDoc,
    max_lines: int = 100,
) -> tuple[str, str]:
    old_code = entity_code_text(file_change.old_content, old_entity)
    new_code = entity_code_text(file_change.new_content, new_entity)
    if len(old_code.splitlines()) <= max_lines and len(new_code.splitlines()) <= max_lines:
        return old_code, new_code
    return (
        _changed_code_window(old_code, new_code, old_side=True, max_lines=max_lines),
        _changed_code_window(old_code, new_code, old_side=False, max_lines=max_lines),
    )


def _entity_code_without_javadoc(source: str, entity: EntityDoc) -> str:
    lines = source.splitlines()
    code_lines = lines[entity.code_start_line - 1 : entity.code_end_line]
    return "\n".join(line.rstrip() for line in code_lines).strip()


def _changed_code_window(old_code: str, new_code: str, old_side: bool, max_lines: int) -> str:
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    opcodes = difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes()
    changed_indexes: list[int] = []
    for tag, old_start, old_end, new_start, new_end in opcodes:
        if tag == "equal":
            continue
        start, end = (old_start, old_end) if old_side else (new_start, new_end)
        changed_indexes.extend(range(start, max(start + 1, end)))
    lines = old_lines if old_side else new_lines
    if not lines:
        return ""
    center = changed_indexes[0] if changed_indexes else 0
    half = max(1, (max_lines - 2) // 2)
    start = max(0, center - half)
    end = min(len(lines), start + max_lines)
    start = max(0, end - max_lines)
    window = lines[start:end]
    if start > 0:
        window = [lines[0], "    // ... relevant changed context ...", *window[2:]]
    return "\n".join(window).strip()
