import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ISSUE_PATTERN = re.compile(r"#[0-9]+|[A-Z][A-Z0-9]+-[0-9]+")
_SUMMARY_CACHE: dict[tuple[str, str], "IssueCandidate | None"] = {}


@dataclass(frozen=True)
class IssueCandidate:
    issue_id: str
    title: str
    source: str


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
    return resolve_issue_context(repo_url, issue_ids, commit_message)[1]


def resolve_issue_context(repo_url: str, issue_ids: list[str], commit_message: str) -> tuple[str, str]:
    candidates = [
        candidate
        for issue_id in issue_ids
        if (candidate := _resolve_issue_candidate(repo_url, issue_id)) is not None
    ]
    for source in ("github_issue", "jira_issue", "pull_request"):
        for candidate in candidates:
            if candidate.source == source and not _looks_like_issue_id(candidate.title):
                return candidate.issue_id, candidate.title
    return (issue_ids[0] if issue_ids else ""), _commit_summary(commit_message)


def _resolve_issue_title(repo_url: str, issue_id: str) -> str:
    candidate = _resolve_issue_candidate(repo_url, issue_id)
    return candidate.title if candidate is not None else ""


def _resolve_issue_candidate(repo_url: str, issue_id: str) -> IssueCandidate | None:
    cache_key = (repo_url, issue_id)
    if cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]
    candidate = None
    if issue_id.startswith("#"):
        metadata = _github_issue_metadata(repo_url, issue_id)
        if metadata:
            title = metadata.get("title", "").strip()
            if title:
                source = "pull_request" if metadata.get("is_pull_request") else "github_issue"
                candidate = IssueCandidate(issue_id=issue_id, title=title, source=source)
    else:
        title = _jira_issue_title(issue_id)
        if title:
            candidate = IssueCandidate(issue_id=issue_id, title=title, source="jira_issue")
    _SUMMARY_CACHE[cache_key] = candidate
    return candidate


def _github_issue_title(repo_url: str, issue_id: str) -> str:
    metadata = _github_issue_metadata(repo_url, issue_id)
    return metadata["title"] if metadata else ""


def _github_issue_metadata(repo_url: str, issue_id: str) -> dict[str, str | bool] | None:
    repo = _github_repo_path(repo_url)
    if not repo:
        return None
    number = issue_id.lstrip("#")
    data = _json_payload(f"https://api.github.com/repos/{repo}/issues/{number}")
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    return {
        "title": title.strip(),
        "is_pull_request": isinstance(data.get("pull_request"), dict),
    }


def _jira_issue_title(issue_id: str) -> str:
    if "-" not in issue_id:
        return ""
    return _json_title(
        f"https://issues.apache.org/jira/rest/api/2/issue/{issue_id}?fields=summary",
        ["fields", "summary"],
    )


def _json_payload(url: str) -> dict | None:
    try:
        request = Request(url, headers={"User-Agent": "javadoc-miner"})
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _json_title(url: str, path: list[str]) -> str:
    data = _json_payload(url)
    if data is None:
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
        stripped = _clean_commit_summary_line(line)
        if stripped:
            return stripped
    return ""


def _clean_commit_summary_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"\((?:\s*(?:#[0-9]+|[A-Z][A-Z0-9]+-[0-9]+)\s*)+\)", "", cleaned)
    cleaned = ISSUE_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"^[\s:;,\-\[\]]+", "", cleaned)
    cleaned = re.sub(r"[\s:;,\-\[\]]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _looks_like_issue_id(text: str) -> bool:
    return ISSUE_PATTERN.fullmatch(text.strip()) is not None
