import re
from dataclasses import dataclass

from .models import OutputSample
from .text_utils import normalize_javadoc_for_semantic_compare


PLACEHOLDER_CONTEXT = "// ... relevant changed context ..."
FORBIDDEN_ENDINGS = ("/**", "*", "(", ",", "=", "+")
CONTROL_PREFIXES = {"if", "for", "while", "switch", "catch", "return", "throw", "new"}
CLASS_PATTERN = re.compile(r"\b(?:class|interface|enum|record)\s+[A-Za-z_$][\w$]*")
METHOD_PATTERN = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\([^;{}]*\)")


@dataclass(frozen=True)
class ValidationResult:
    disposition: str
    reason: str = ""


@dataclass(frozen=True)
class CodeScan:
    brace_balance: int
    minimum_brace_balance: int
    unclosed_block_comment: bool
    unclosed_string: bool


def validate_output_sample(sample: OutputSample, max_class_lines: int = 500) -> ValidationResult:
    if is_weak_inheritdoc_only_change(sample.javadoc_before, sample.javadoc_after):
        return ValidationResult("discard", "weak_inheritdoc_only")

    reasons = [
        reason
        for code in (sample.code_before, sample.code_after)
        if (reason := validate_code_snippet(code, sample.entity_type))
    ]
    if reasons:
        if sample.entity_type == "class":
            return ValidationResult("review", f"invalid_class_context:{reasons[0]}")
        return ValidationResult("discard", f"truncated_code_context:{reasons[0]}")

    if sample.entity_type == "class" and max(
        len(sample.code_before.splitlines()),
        len(sample.code_after.splitlines()),
    ) > max_class_lines:
        return ValidationResult("discard", "class_context_too_large")
    return ValidationResult("retain")


def validate_code_snippet(code: str, entity_type: str) -> str:
    stripped = code.rstrip()
    if not stripped:
        return "empty_code"
    if PLACEHOLDER_CONTEXT in code:
        return "placeholder_context"
    if code.count("/**") > code.count("*/"):
        return "unclosed_javadoc"
    if stripped.endswith(FORBIDDEN_ENDINGS):
        return "unfinished_ending"

    scan = scan_java_structure(code)
    if scan.unclosed_block_comment:
        return "unclosed_comment"
    if scan.unclosed_string:
        return "unclosed_string"
    if scan.brace_balance != 0 or scan.minimum_brace_balance < 0:
        return "unbalanced_braces"

    declaration = _declaration_prefix(code)
    if entity_type == "method":
        match = METHOD_PATTERN.search(declaration)
        if match is None or match.group(1) in CONTROL_PREFIXES:
            return "missing_method_signature"
        if "{" in code:
            if not stripped.endswith("}"):
                return "unfinished_method"
        elif not stripped.endswith(";"):
            return "unfinished_method"
    elif entity_type == "class":
        if CLASS_PATTERN.search(declaration) is None:
            return "missing_class_declaration"
        if not stripped.endswith("}"):
            return "unfinished_class"
    else:
        return "unsupported_entity_type"
    return ""


def scan_java_structure(code: str) -> CodeScan:
    state = "normal"
    depth = 0
    minimum_depth = 0
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
        else:
            if char == "/" and next_char == "/":
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
                minimum_depth = min(minimum_depth, depth)
        index += 1
    return CodeScan(
        brace_balance=depth,
        minimum_brace_balance=minimum_depth,
        unclosed_block_comment=state == "block_comment",
        unclosed_string=state in {"string", "char"},
    )


def is_weak_inheritdoc_only_change(old_doc: str, new_doc: str) -> bool:
    if not re.search(r"\{@inheritDoc\}|@inheritDoc\b", new_doc, re.IGNORECASE):
        return False
    without_inheritdoc = re.sub(
        r"\{@inheritDoc\}|@inheritDoc\b",
        " ",
        new_doc,
        flags=re.IGNORECASE,
    )
    normalized = normalize_javadoc_for_semantic_compare(without_inheritdoc)
    return not normalized.strip()


def _declaration_prefix(code: str) -> str:
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", " ", code, flags=re.DOTALL)
    lines = []
    for line in without_comments.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("@"):
            continue
        lines.append(stripped)
        if "{" in stripped or ";" in stripped:
            break
    return " ".join(lines)
