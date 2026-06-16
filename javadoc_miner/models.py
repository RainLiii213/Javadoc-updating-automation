from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EntityDoc:
    entity_type: str
    name: str
    signature: str
    javadoc: str
    start_line: int
    end_line: int
    return_type: str = ""
    parameters: list[str] | None = None
    throws: list[str] | None = None
    code_start_line: int = 0
    code_end_line: int = 0

    def __post_init__(self):
        if self.parameters is None:
            object.__setattr__(self, "parameters", [])
        if self.throws is None:
            object.__setattr__(self, "throws", [])
        if self.code_start_line == 0:
            object.__setattr__(self, "code_start_line", self.end_line + 1)
        if self.code_end_line == 0:
            object.__setattr__(self, "code_end_line", self.code_start_line)


@dataclass(frozen=True)
class FileChange:
    path: str
    old_content: str | None
    new_content: str | None


@dataclass(frozen=True)
class Classification:
    change_type: str
    javadoc_change_type: str
    method_change_type: str


@dataclass(frozen=True)
class OutputSample:
    repo: str
    commit_hash: str
    commit_message: str
    issue_summary: str
    code_before: str
    code_after: str
    javadoc_before: str
    javadoc_after: str
    entity_name: str
    entity_signature: str
    javadoc_change_type: str
    method_change_type: str
    issue_id: str
    commit_url: str
    entity_type: str = ""
    file_path: str = ""
    issue_summary_fallback_applied: bool = False

    def to_json_dict(self) -> dict:
        return {
            "commit_hash": self.commit_hash,
            "issue_summary": self.issue_summary,
            "code_before": self.code_before,
            "code_after": self.code_after,
            "javadoc_before": self.javadoc_before,
            "javadoc_after": self.javadoc_after,
        }


@dataclass
class ExtractionStats:
    total_commits_scanned: int = 0
    total_commits_containing_javadoc_changes: int = 0
    total_commits_containing_code_and_javadoc_changes: int = 0
    candidate_samples_found: int = 0
    samples_retained: int = 0
    samples_filtered: int = 0
    discarded_truncated_code_context: int = 0
    moved_to_review: int = 0
    discarded_weak_inheritdoc: int = 0
    issue_summary_fallbacks: int = 0
    history_complete: bool = False

    def to_json_dict(self) -> dict:
        return asdict(self)
