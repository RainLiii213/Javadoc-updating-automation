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
    quality: str
    issue_id: str
    commit_url: str
    entity_type: str = ""

    def to_json_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionStats:
    total_commits_processed: int = 0
    total_commits_containing_javadoc_changes: int = 0
    total_samples_extracted: int = 0
    quality_a_samples: int = 0
    quality_b_samples: int = 0
    quality_c_samples: int = 0
    javadoc_additions: int = 0
    javadoc_modifications: int = 0
    javadoc_deletions: int = 0
    method_additions: int = 0
    method_modifications: int = 0
    method_deletions: int = 0
    target_a_samples: int = 40
    target_b_samples: int = 5
    target_c_samples: int = 5
    a_sample_yield: float = 0.0
    a_sample_density: float = 0.0
    a_sample_shortfall: int = 0

    def record(self, classification: Classification) -> None:
        self.total_samples_extracted += 1
        if classification.quality == "A":
            self.quality_a_samples += 1
        elif classification.quality == "B":
            self.quality_b_samples += 1
        elif classification.quality == "C":
            self.quality_c_samples += 1

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

    def finalize(self) -> None:
        if self.total_commits_processed:
            self.a_sample_yield = self.quality_a_samples / self.total_commits_processed
        if self.total_samples_extracted:
            self.a_sample_density = self.quality_a_samples / self.total_samples_extracted
        self.a_sample_shortfall = max(0, self.target_a_samples - self.quality_a_samples)

    def to_json_dict(self) -> dict:
        return asdict(self)
