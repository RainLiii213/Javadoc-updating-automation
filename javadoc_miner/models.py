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

    def __post_init__(self):
        if self.parameters is None:
            object.__setattr__(self, "parameters", [])
        if self.throws is None:
            object.__setattr__(self, "throws", [])


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
    quality: str

    def to_json_dict(self) -> dict:
        return asdict(self)
