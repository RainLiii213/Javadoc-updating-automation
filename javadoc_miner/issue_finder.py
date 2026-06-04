import re


ISSUE_PATTERN = re.compile(r"#[0-9]+|[A-Z][A-Z0-9]+-[0-9]+")


def find_issues(text: str) -> list[str]:
    seen: set[str] = set()
    issues: list[str] = []
    for match in ISSUE_PATTERN.finditer(text):
        issue = match.group(0)
        if issue not in seen:
            seen.add(issue)
            issues.append(issue)
    return issues
