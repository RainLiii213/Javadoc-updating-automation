import difflib
import re

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
    max_lines: int = 500,
    complete_class_lines: int = 300,
) -> tuple[str, str]:
    old_code = entity_code_text(file_change.old_content, old_entity)
    new_code = entity_code_text(file_change.new_content, new_entity)
    if new_entity.entity_type != "class":
        return old_code, new_code
    if max(len(old_code.splitlines()), len(new_code.splitlines())) <= complete_class_lines:
        return old_code, new_code
    old_code, new_code = _relevant_class_context_pair(old_code, new_code)
    if not old_code or not new_code:
        return "", ""
    if max(len(old_code.splitlines()), len(new_code.splitlines())) > max_lines:
        return "", ""
    return old_code, new_code


def _entity_code_without_javadoc(source: str, entity: EntityDoc) -> str:
    lines = source.splitlines()
    code_lines = lines[entity.code_start_line - 1 : entity.code_end_line]
    return "\n".join(line.rstrip() for line in code_lines).strip()


def _relevant_class_context_pair(old_code: str, new_code: str) -> tuple[str, str]:
    old_parts = _split_class_context(old_code)
    new_parts = _split_class_context(new_code)
    if old_parts is None or new_parts is None:
        return "", ""
    old_header, old_members = old_parts
    new_header, new_members = new_parts
    matcher = difflib.SequenceMatcher(
        None,
        [_normalized_member(member) for member in old_members],
        [_normalized_member(member) for member in new_members],
        autojunk=False,
    )
    old_selected: list[str] = []
    new_selected: list[str] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_selected.extend(old_members[old_start:old_end])
        new_selected.extend(new_members[new_start:new_end])
    if old_header == new_header and not old_selected and not new_selected:
        return "", ""
    return (
        _build_class_context(old_header, old_selected),
        _build_class_context(new_header, new_selected),
    )


def _split_class_context(code: str) -> tuple[str, list[str]] | None:
    open_index = _first_code_brace(code)
    if open_index is None:
        return None
    header = code[: open_index + 1].strip()
    members: list[str] = []
    member_start = open_index + 1
    depth = 1
    state = "normal"
    index = open_index + 1
    while index < len(code):
        char = code[index]
        next_char = code[index + 1] if index + 1 < len(code) else ""
        if state == "line_comment":
            if char == "\n":
                state = "normal"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "normal"
                index += 1
        elif state in {"string", "char"}:
            if char == "\\":
                index += 1
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "normal"
        elif char == "/" and next_char == "/":
            state = "line_comment"
            index += 1
        elif char == "/" and next_char == "*":
            state = "block_comment"
            index += 1
        elif char == '"':
            state = "string"
        elif char == "'":
            state = "char"
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 1 and _brace_ends_member(code, index):
                member = code[member_start : index + 1].strip()
                if member:
                    members.append(member)
                member_start = index + 1
            elif depth == 0:
                return header, members
        elif char == ";" and depth == 1:
            member = code[member_start : index + 1].strip()
            if member:
                members.append(member)
            member_start = index + 1
        index += 1
    return None


def _first_code_brace(code: str) -> int | None:
    state = "normal"
    index = 0
    while index < len(code):
        char = code[index]
        next_char = code[index + 1] if index + 1 < len(code) else ""
        if state == "line_comment":
            if char == "\n":
                state = "normal"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "normal"
                index += 1
        elif state in {"string", "char"}:
            if char == "\\":
                index += 1
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "normal"
        elif char == "/" and next_char == "/":
            state = "line_comment"
            index += 1
        elif char == "/" and next_char == "*":
            state = "block_comment"
            index += 1
        elif char == '"':
            state = "string"
        elif char == "'":
            state = "char"
        elif char == "{":
            return index
        index += 1
    return None


def _normalized_member(member: str) -> str:
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", " ", member, flags=re.DOTALL)
    return " ".join(without_comments.split())


def _brace_ends_member(code: str, close_index: int) -> bool:
    remainder = code[close_index + 1 :]
    stripped = remainder.lstrip()
    if not stripped:
        return True
    if stripped.startswith((";", ")", ",", ".", "]", "?", ":")):
        return False
    if re.match(r"^(?:catch|else|finally|while)\b", stripped):
        return False
    return True


def _build_class_context(header: str, members: list[str]) -> str:
    if not members:
        return f"{header}\n}}"
    indented = "\n\n".join(_remove_java_comments(member).strip() for member in members)
    return f"{header}\n{indented}\n}}"


def _remove_java_comments(code: str) -> str:
    output: list[str] = []
    state = "normal"
    index = 0
    while index < len(code):
        char = code[index]
        next_char = code[index + 1] if index + 1 < len(code) else ""
        if state == "line_comment":
            if char == "\n":
                output.append(char)
                state = "normal"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "normal"
                index += 1
            elif char == "\n":
                output.append(char)
        elif state in {"string", "char"}:
            output.append(char)
            if char == "\\" and next_char:
                output.append(next_char)
                index += 1
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "normal"
        elif char == "/" and next_char == "/":
            state = "line_comment"
            index += 1
        elif char == "/" and next_char == "*":
            state = "block_comment"
            index += 1
        else:
            output.append(char)
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
        index += 1
    return "\n".join(line.rstrip() for line in "".join(output).splitlines() if line.strip())
