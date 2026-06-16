import difflib
import html
import re
from collections import Counter
from pathlib import PurePosixPath


JAVADOC_TAGS = ("@param", "@return", "@throws", "@exception", "@see", "@since")
TEST_NAME_PATTERN = re.compile(r"(^Test.*|.*Tests?|.*TestCase)\.java$")
NON_PRODUCTION_PATH_PATTERN = re.compile(
    r"(^|[-_])(?:test|tests|testlib|testdata|benchmark|benchmarks|generated)([-_]|$)"
)
IGNORED_JAVADOC_TAGS = {"@see", "@since", "@version", "@author"}
UNINFORMATIVE_WORDS = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "this",
    "that",
    "method",
    "class",
    "function",
}
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
ISSUE_PATTERN = re.compile(r"(?:#|[A-Z][A-Z0-9]+-)\d+\b", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"\bv?\d+(?:\.\d+){1,}(?:[-._][a-z0-9]+)?\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|"
    r"(?:19|20)\d{2})\b"
)
INLINE_LINK_PATTERN = re.compile(r"\{@(?:link|linkplain)\s+([^}\s]+)(?:\s+([^}]+))?\}")
CONTRACT_TERMS = {
    "allow",
    "allowed",
    "blank",
    "default",
    "deprecated",
    "deprecation",
    "empty",
    "epoch",
    "exception",
    "fail",
    "fails",
    "invalid",
    "milliseconds",
    "nonnull",
    "null",
    "nullable",
    "overflow",
    "seconds",
    "throw",
    "throws",
    "timeout",
    "valid",
}
LOW_SIGNAL_COMMIT_PATTERN = re.compile(
    r"^(?:"
    r"javadocs?|docs?|documentation|"
    r"sort(?:ed|ing)?\s+members?|"
    r"format(?:ting)?|reformat(?:ting)?|"
    r"cleanup|clean\s*up|"
    r"typos?|fix\s+typos?"
    r")\b",
    re.IGNORECASE,
)
LOW_SIGNAL_COMMIT_ANYWHERE_PATTERN = re.compile(
    r"\b(?:refactor(?:ing)?|rename(?:d|s|ing)?\s+internal|"
    r"empty\s+lines?|whitespace|imports?\s+only|code\s+duplication)\b",
    re.IGNORECASE,
)


def is_target_java_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    name = pure_path.name
    if not normalized.endswith(".java"):
        return False
    parts = [part.lower() for part in pure_path.parts]
    if "src" not in parts:
        return False
    if parts and parts[0] == "android":
        return False
    if any(
        part in {"test", "tests", "testdata", "generated", "target", "build"}
        or NON_PRODUCTION_PATH_PATTERN.search(part)
        for part in parts[:-1]
    ):
        return False
    return not TEST_NAME_PATTERN.match(name)


def is_low_signal_commit_message(message: str) -> bool:
    first_line = next((line.strip() for line in message.splitlines() if line.strip()), "")
    return bool(
        LOW_SIGNAL_COMMIT_PATTERN.match(first_line)
        or LOW_SIGNAL_COMMIT_ANYWHERE_PATTERN.search(first_line)
    )


def _diff_payload(line: str) -> str:
    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
        return line[1:].strip()
    return line.strip()


def is_javadoc_diff_line(line: str) -> bool:
    payload = _diff_payload(line)
    return (
        payload.startswith("/**")
        or payload.startswith("*/")
        or payload.startswith("*")
        or any(tag in payload for tag in JAVADOC_TAGS)
    )


def is_code_diff_line(line: str) -> bool:
    if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
        return False
    payload = _diff_payload(line)
    if not payload:
        return False
    if is_javadoc_diff_line(line):
        return False
    if payload.startswith("//") or payload.startswith("/*") or payload.startswith("*"):
        return False
    return True


def normalize_doc_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("/**"):
            line = line[3:].strip()
        if line.endswith("*/"):
            line = line[:-2].strip()
        if line.startswith("*"):
            line = line[1:].strip()
        if line:
            lines.append(" ".join(line.split()))
    return "\n".join(lines)


def normalize_javadoc_for_semantic_compare(text: str) -> str:
    """Return stable, core Javadoc content for substantive-change comparison."""
    core_lines: list[str] = []
    ignoring_tag_block = False
    for line in normalize_doc_text(text).splitlines():
        tag_match = re.match(r"(@\w+)\b", line)
        if tag_match:
            ignoring_tag_block = tag_match.group(1).lower() in IGNORED_JAVADOC_TAGS
        if ignoring_tag_block:
            continue
        core_lines.append(line)

    normalized = html.unescape(" ".join(core_lines))
    normalized = INLINE_LINK_PATTERN.sub(lambda match: match.group(2) or match.group(1), normalized)
    normalized = URL_PATTERN.sub(" ", normalized)
    normalized = ISSUE_PATTERN.sub(" ", normalized)
    normalized = VERSION_PATTERN.sub(" ", normalized)
    normalized = DATE_PATTERN.sub(" ", normalized)
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"\b\d+(?:[._-]\d+)*\b", " ", normalized)
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", normalized.lower())
    return " ".join(tokens)


def is_substantive_javadoc_change(old_doc: str, new_doc: str) -> bool:
    """Determine whether core explanatory Javadoc changed meaningfully."""
    old_tokens = normalize_javadoc_for_semantic_compare(old_doc).split()
    new_tokens = normalize_javadoc_for_semantic_compare(new_doc).split()
    if Counter(old_tokens) == Counter(new_tokens):
        return False

    old_effective = [token for token in old_tokens if token not in UNINFORMATIVE_WORDS]
    new_effective = [token for token in new_tokens if token not in UNINFORMATIVE_WORDS]
    if not old_effective or not new_effective:
        content = old_effective or new_effective
        return len(content) >= 3

    removed = list((Counter(old_effective) - Counter(new_effective)).elements())
    added = list((Counter(new_effective) - Counter(old_effective)).elements())
    changed_count = len(removed) + len(added)
    if changed_count == 0:
        return False
    if changed_count == 1 and (set(removed) | set(added)) & CONTRACT_TERMS:
        return True
    if changed_count >= 2 and not _only_minor_spelling_change(removed, added):
        return True

    similarity = javadoc_similarity(old_doc, new_doc)
    return changed_count == 1 and similarity < 0.9


def javadoc_similarity(old_doc: str, new_doc: str) -> float:
    old_tokens = normalize_javadoc_for_semantic_compare(old_doc).split()
    new_tokens = normalize_javadoc_for_semantic_compare(new_doc).split()
    return difflib.SequenceMatcher(None, old_tokens, new_tokens).ratio()


def _only_minor_spelling_change(removed: list[str], added: list[str]) -> bool:
    if not removed or len(removed) != len(added):
        return False
    unmatched = added.copy()
    for old_token in removed:
        match_index = next(
            (
                index
                for index, new_token in enumerate(unmatched)
                if difflib.SequenceMatcher(None, old_token, new_token).ratio() >= 0.8
            ),
            None,
        )
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return True
