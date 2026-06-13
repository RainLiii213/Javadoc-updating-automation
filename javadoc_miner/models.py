from dataclasses import asdict, dataclass, field


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
    file_path: str = ""

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
    total_samples_generated: int = 0
    quality_distribution: dict[str, int] = field(
        default_factory=lambda: {"A": 0, "B": 0, "C": 0}
    )
    method_change_distribution: dict[str, int] = field(
        default_factory=lambda: {
            "METHOD_ADDITION": 0,
            "METHOD_MODIFICATION": 0,
            "METHOD_DELETION": 0,
        }
    )
    javadoc_change_distribution: dict[str, int] = field(
        default_factory=lambda: {
            "JAVADOC_ADDITION": 0,
            "JAVADOC_MODIFICATION": 0,
            "JAVADOC_DELETION": 0,
        }
    )
    target_a_samples: int = 50
    target_b_samples: int = 0
    target_c_samples: int = 0
    a_sample_yield: float = 0.0
    a_sample_density: float = 0.0
    a_sample_shortfall: int = 0
    a_sample_shortfall_reason: str = ""

    def record(self, classification: Classification) -> None:
        self.total_samples_generated += 1
        if classification.quality in self.quality_distribution:
            self.quality_distribution[classification.quality] += 1
        if classification.method_change_type in self.method_change_distribution:
            self.method_change_distribution[classification.method_change_type] += 1
        if classification.javadoc_change_type in self.javadoc_change_distribution:
            self.javadoc_change_distribution[classification.javadoc_change_type] += 1

    def finalize(self) -> None:
        a_samples = self.quality_distribution["A"]
        if self.total_commits_scanned:
            self.a_sample_yield = a_samples / self.total_commits_scanned
        if self.total_samples_generated:
            self.a_sample_density = a_samples / self.total_samples_generated
        self.a_sample_shortfall = max(0, self.target_a_samples - a_samples)
        if self.a_sample_shortfall:
            self.a_sample_shortfall_reason = (
                f"Only {a_samples} A-quality samples were generated. "
                "Strict A-quality requires a substantial entity-level code modification, "
                "a meaningful Javadoc modification, and a clear logical connection."
            )
        else:
            self.a_sample_shortfall_reason = ""

    def to_json_dict(self) -> dict:
        data = asdict(self)
        data["target_distribution"] = {
            "A": self.target_a_samples,
            "B": self.target_b_samples,
            "C": self.target_c_samples,
        }
        return data

    @property
    def total_commits_processed(self) -> int:
        return self.total_commits_scanned

    @property
    def total_samples_extracted(self) -> int:
        return self.total_samples_generated

    @property
    def quality_a_samples(self) -> int:
        return self.quality_distribution["A"]

    @property
    def quality_b_samples(self) -> int:
        return self.quality_distribution["B"]

    @property
    def quality_c_samples(self) -> int:
        return self.quality_distribution["C"]

    @property
    def javadoc_additions(self) -> int:
        return self.javadoc_change_distribution["JAVADOC_ADDITION"]

    @property
    def javadoc_modifications(self) -> int:
        return self.javadoc_change_distribution["JAVADOC_MODIFICATION"]

    @property
    def javadoc_deletions(self) -> int:
        return self.javadoc_change_distribution["JAVADOC_DELETION"]

    @property
    def method_additions(self) -> int:
        return self.method_change_distribution["METHOD_ADDITION"]

    @property
    def method_modifications(self) -> int:
        return self.method_change_distribution["METHOD_MODIFICATION"]

    @property
    def method_deletions(self) -> int:
        return self.method_change_distribution["METHOD_DELETION"]
