import re
from pathlib import PurePosixPath


JAVADOC_TAGS = ("@param", "@return", "@throws", "@exception", "@see", "@since")
TEST_NAME_PATTERN = re.compile(r"(^Test.*|.*Tests?|.*TestCase)\.java$")


def is_target_java_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    name = pure_path.name
    if not normalized.startswith("src/main/java/"):
        return False
    if not normalized.endswith(".java"):
        return False
    return not TEST_NAME_PATTERN.match(name)


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
