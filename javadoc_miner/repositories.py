import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RepositorySpec:
    name: str
    url: str

    @property
    def slug(self) -> str:
        return repository_slug(self.name)


def repository_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


COMMONS_LANG = RepositorySpec(
    "apache/commons-lang",
    "https://github.com/apache/commons-lang.git",
)

DEFAULT_JAVA_REPOSITORIES = (
    RepositorySpec("apache/commons-collections", "https://github.com/apache/commons-collections.git"),
    RepositorySpec("apache/commons-text", "https://github.com/apache/commons-text.git"),
    RepositorySpec("apache/commons-compress", "https://github.com/apache/commons-compress.git"),
    RepositorySpec("apache/commons-codec", "https://github.com/apache/commons-codec.git"),
    RepositorySpec("apache/commons-math", "https://github.com/apache/commons-math.git"),
    RepositorySpec("google/guava", "https://github.com/google/guava.git"),
    RepositorySpec("JodaOrg/joda-time", "https://github.com/JodaOrg/joda-time.git"),
    RepositorySpec("apache/lucene", "https://github.com/apache/lucene.git"),
    RepositorySpec(
        "FasterXML/jackson-databind",
        "https://github.com/FasterXML/jackson-databind.git",
    ),
    RepositorySpec(
        "spring-projects/spring-data-commons",
        "https://github.com/spring-projects/spring-data-commons.git",
    ),
    RepositorySpec("junit-team/junit5", "https://github.com/junit-team/junit5.git"),
)

COMMONS_IO = RepositorySpec(
    "apache/commons-io",
    "https://github.com/apache/commons-io.git",
)

KNOWN_REPOSITORIES = (COMMONS_LANG, COMMONS_IO, *DEFAULT_JAVA_REPOSITORIES)
