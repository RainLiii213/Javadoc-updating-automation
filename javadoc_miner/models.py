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
    patch: str


@dataclass(frozen=True)
class CommitInfo:
    repo: str
    commit_hash: str
    commit_url: str
    commit_message: str
    patch: str


@dataclass(frozen=True)
class Classification:
    change_type: str
    quality: str
    javadoc_change_type: str
    method_change_type: str


@dataclass(frozen=True)
class CandidateSample:
    old_entity: EntityDoc | None
    new_entity: EntityDoc | None
    classification: Classification
    file_change: FileChange


@dataclass(frozen=True)
class OutputSample:
    repo: str
    commit_hash: str
    commit_url: str
    issue: str
    issues: list[str]
    entity_type: str
    entity_name: str
    old_javadoc: str
    new_javadoc: str
    patch: str
    commit_message: str
    change_type: str
    javadoc_change_type: str
    method_change_type: str
    quality: str

    def to_json_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionStats:
    total_commits_processed: int = 0
    total_samples_extracted: int = 0
    javadoc_additions: int = 0
    javadoc_modifications: int = 0
    javadoc_deletions: int = 0
    method_additions: int = 0
    method_modifications: int = 0
    method_deletions: int = 0

    def record(self, classification: Classification) -> None:
        self.total_samples_extracted += 1
        if classification.javadoc_change_type == "JAVADOC_ADDITION":
            self.javadoc_additions += 1
        elif classification.javadoc_change_type == "JAVADOC_MODIFICATION":
            self.javadoc_modifications += 1
        elif classification.javadoc_change_type == "JAVADOC_DELETION":
            self.javadoc_deletions += 1

        if classification.method_change_type == "METHOD_ADDITION":
            self.method_additions += 1
        elif classification.method_change_type == "METHOD_MODIFICATION":
            self.method_modifications += 1
        elif classification.method_change_type == "METHOD_DELETION":
            self.method_deletions += 1

    def to_json_dict(self) -> dict:
        return asdict(self)
