import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ISSUE_PATTERN = re.compile(r"#[0-9]+|[A-Z][A-Z0-9]+-[0-9]+")
_SUMMARY_CACHE: dict[tuple[str, str], str] = {}


def find_issues(text: str) -> list[str]:
    seen: set[str] = set()
    issues: list[str] = []
    for match in ISSUE_PATTERN.finditer(text):
        issue = match.group(0)
        if issue not in seen:
            seen.add(issue)
            issues.append(issue)
    return issues


def resolve_issue_summary(repo_url: str, issue_ids: list[str], commit_message: str) -> str:
    for issue_id in issue_ids:
        summary = _resolve_issue_title(repo_url, issue_id)
        if summary and not _looks_like_issue_id(summary):
            return summary
    return _commit_summary(commit_message)


def _resolve_issue_title(repo_url: str, issue_id: str) -> str:
    cache_key = (repo_url, issue_id)
    if cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]
    title = ""
    if issue_id.startswith("#"):
        title = _github_issue_title(repo_url, issue_id)
    else:
        title = _jira_issue_title(issue_id)
    _SUMMARY_CACHE[cache_key] = title
    return title


def _github_issue_title(repo_url: str, issue_id: str) -> str:
    repo = _github_repo_path(repo_url)
    if not repo:
        return ""
    number = issue_id.lstrip("#")
    return _json_title(f"https://api.github.com/repos/{repo}/issues/{number}", ["title"])


def _jira_issue_title(issue_id: str) -> str:
    if "-" not in issue_id:
        return ""
    return _json_title(
        f"https://issues.apache.org/jira/rest/api/2/issue/{issue_id}?fields=summary",
        ["fields", "summary"],
    )


def _json_title(url: str, path: list[str]) -> str:
    try:
        request = Request(url, headers={"User-Agent": "javadoc-miner"})
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return ""
    value = data
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value.strip() if isinstance(value, str) else ""


def _github_repo_path(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.netloc.lower() != "github.com":
        return ""
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        return ""
    return "/".join(parts[:2])


def _commit_summary(commit_message: str) -> str:
    for line in commit_message.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_issue_id(text: str) -> bool:
    return ISSUE_PATTERN.fullmatch(text.strip()) is not None
