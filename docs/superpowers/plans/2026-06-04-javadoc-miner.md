# JavaDoc Miner 瀹炵幇璁″垝

> **缁?agentic workers:** 蹇呴』浣跨敤 `superpowers:subagent-driven-development` 鎴?`superpowers:executing-plans` 閫愪换鍔℃墽琛屻€傛湰璁″垝浣跨敤 checkbox (`- [x]`) 杩借釜銆傚綋鍓嶅伐浣滃尯涓嶆槸 git 浠撳簱锛屾墍浠ユ墽琛屾椂涓嶅仛 `git commit`锛涘鏋滅敤鎴蜂箣鍚庡垵濮嬪寲 git锛屽啀鎸夋瘡涓换鍔℃湯灏剧殑鎻愪氦鐐规彁浜ゃ€?
**鐩爣:** 瀹炵幇涓€涓?Python CLI锛屼粠 GitHub Java 浠撳簱鑷姩 clone銆侀亶鍘?commit銆佹寲鎺樹唬鐮佷笌 JavaDoc 鍚屾椂鍙樺寲鐨勫疄浣撶骇鏍锋湰锛屽苟杈撳嚭 JSON 鏁版嵁闆嗗拰 summary CSV銆?
**鏋舵瀯:** 鍏堢敤 git diff 鍋?commit 绮楃瓫锛屽啀璇诲彇 commit 鍓嶅悗鏂囦欢锛岀敤杞婚噺 JavaDoc 瑙ｆ瀽鍣ㄧ粦瀹氭柟娉?绫诲疄浣擄紝鏈€鍚庢寜鍙В閲婅鍒欏垎绫昏川閲忋€傚悇妯″潡閫氳繃 dataclass 浼犻€掔粨鏋勫寲鏁版嵁锛屼究浜庡悗缁浛鎹?Java parser 鎴栨帴鍏?GitHub API銆?
**Tech Stack:** Python 3.10+銆佹爣鍑嗗簱 `argparse` / `subprocess` / `dataclasses` / `json` / `csv` / `pathlib` / `tempfile`銆佹祴璇曚娇鐢?`pytest`銆?
---

## 鏂囦欢缁撴瀯

鍒涘缓锛?
- `javadoc_miner/__init__.py`锛氬寘鏍囪瘑鍜岀増鏈彿銆?- `javadoc_miner/__main__.py`锛歚python -m javadoc_miner` 鍏ュ彛銆?- `javadoc_miner/cli.py`锛氬懡浠よ鍙傛暟鍜屼富娴佺▼銆?- `javadoc_miner/config.py`锛氳繍琛岄厤缃?dataclass銆?- `javadoc_miner/models.py`锛氬疄浣撱€乧ommit銆佹牱鏈瓑 dataclass銆?- `javadoc_miner/issue_finder.py`锛歩ssue ID 鎻愬彇銆?- `javadoc_miner/text_utils.py`锛氭枃鏈綊涓€鍖栧拰 diff 琛屽垽鏂€?- `javadoc_miner/java_parser.py`锛欽avaDoc 涓?Java 瀹炰綋鍚彂寮忚В鏋愩€?- `javadoc_miner/classifier.py`锛歝hange type 涓?quality 瑙勫垯銆?- `javadoc_miner/git_repo.py`锛歝lone銆乫etch銆乬it 鍛戒护灏佽銆?- `javadoc_miner/diff_extractor.py`锛氱洰鏍囨枃浠惰繃婊ゃ€乸atch 涓庡墠鍚庢枃浠惰鍙栥€?- `javadoc_miner/writer.py`锛欽SON 鍜?CSV 杈撳嚭銆?- `tests/test_issue_finder.py`
- `tests/test_text_utils.py`
- `tests/test_java_parser.py`
- `tests/test_classifier.py`
- `tests/test_writer.py`
- `tests/test_diff_extractor.py`
- `tests/test_cli_integration.py`

---

## Task 1: 椤圭洰楠ㄦ灦涓庡熀纭€閰嶇疆

**Files:**

- Create: `javadoc_miner/__init__.py`
- Create: `javadoc_miner/__main__.py`
- Create: `javadoc_miner/config.py`
- Create: `javadoc_miner/models.py`
- Create: `tests/test_models_import.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

`tests/test_models_import.py`锛?
```python
from pathlib import Path

from javadoc_miner.config import MinerConfig
from javadoc_miner.models import OutputSample


def test_config_has_research_defaults():
    config = MinerConfig(repo_url="https://github.com/apache/commons-lang")

    assert config.cache_dir == Path(".cache/repos")
    assert config.output_dir == Path("dataset")
    assert config.max_commits == 1000
    assert config.max_samples == 100
    assert config.full_history is False
    assert config.min_quality == "B"


def test_output_sample_serializes_required_fields():
    sample = OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        issue="LANG-1234",
        issues=["LANG-1234"],
        entity_type="method",
        entity_name="getFullName",
        old_javadoc="/** Returns the display name. */",
        new_javadoc="/** Returns the full display name. */",
        patch="diff --git a/A.java b/A.java",
        commit_message="LANG-1234 rename method",
        change_type="method_rename",
        quality="A",
    )

    assert sample.to_json_dict()["quality"] == "A"
    assert sample.to_json_dict()["entity_name"] == "getFullName"
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_models_import.py -v
```

Expected: 鍥犱负 `javadoc_miner` 鍖呭拰 dataclass 灏氫笉瀛樺湪鑰屽け璐ャ€?
- [x] **Step 3: 瀹炵幇鏈€灏忛鏋?*

`javadoc_miner/config.py` 瀹氫箟锛?
```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MinerConfig:
    repo_url: str
    cache_dir: Path = Path(".cache/repos")
    output_dir: Path = Path("dataset")
    max_commits: int = 1000
    max_samples: int = 100
    full_history: bool = False
    min_quality: str = "B"
    force_refresh: bool = False
```

`javadoc_miner/models.py` 瀹氫箟鏍稿績 dataclass锛歚EntityDoc`銆乣FileChange`銆乣CommitInfo`銆乣CandidateSample`銆乣OutputSample`銆俙OutputSample.to_json_dict()` 杩斿洖 JSON 鍙簭鍒楀寲瀛楀吀銆?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_models_import.py -v
```

Expected: `2 passed`銆?
---

## Task 2: Issue ID 鎻愬彇

**Files:**

- Create: `javadoc_miner/issue_finder.py`
- Create: `tests/test_issue_finder.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
from javadoc_miner.issue_finder import find_issues


def test_find_issues_extracts_github_and_apache_ids_in_order():
    text = "LANG-1234 fix docs. See #56 and IO-77. LANG-1234 repeated."

    assert find_issues(text) == ["LANG-1234", "#56", "IO-77"]


def test_find_issues_returns_empty_list_when_no_issue_id():
    assert find_issues("Improve JavaDoc for renamed method") == []
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_issue_finder.py -v
```

Expected: import 澶辫触鎴栧嚱鏁颁笉瀛樺湪銆?
- [x] **Step 3: 瀹炵幇鎻愬彇鍑芥暟**

浣跨敤涓や釜姝ｅ垯锛?
```python
ISSUE_PATTERN = re.compile(r"#[0-9]+|[A-Z][A-Z0-9]+-[0-9]+")
```

閬嶅巻鍖归厤缁撴灉锛屾寜鍑虹幇椤哄簭鍘婚噸銆?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_issue_finder.py -v
```

Expected: `2 passed`銆?
---

## Task 3: 鏂囨湰宸ュ叿涓庢枃浠惰繃婊?
**Files:**

- Create: `javadoc_miner/text_utils.py`
- Create: `tests/test_text_utils.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
from javadoc_miner.text_utils import (
    is_javadoc_diff_line,
    is_code_diff_line,
    is_target_java_path,
    normalize_doc_text,
)


def test_target_java_path_accepts_main_java_only():
    assert is_target_java_path("src/main/java/org/example/Foo.java")
    assert not is_target_java_path("src/test/java/org/example/FooTest.java")
    assert not is_target_java_path("src/main/java/org/example/FooTest.java")
    assert not is_target_java_path("pom.xml")


def test_diff_line_classification_separates_javadoc_and_code():
    assert is_javadoc_diff_line("+     * @param name user name")
    assert is_javadoc_diff_line("-     /**")
    assert not is_javadoc_diff_line("+     public String getName() {")
    assert is_code_diff_line("+     public String getName() {")
    assert not is_code_diff_line("+     * @return name")
    assert not is_code_diff_line("+")


def test_normalize_doc_text_removes_formatting_noise():
    left = "/**\n * Returns name.\n */"
    right = "/**\n* Returns   name.\n*/"

    assert normalize_doc_text(left) == normalize_doc_text(right)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_text_utils.py -v
```

Expected: import 澶辫触鎴栧嚱鏁颁笉瀛樺湪銆?
- [x] **Step 3: 瀹炵幇宸ュ叿鍑芥暟**

瀹炵幇锛?
- `is_target_java_path(path: str) -> bool`
- `is_javadoc_diff_line(line: str) -> bool`
- `is_code_diff_line(line: str) -> bool`
- `normalize_doc_text(text: str) -> str`

浠ｇ爜鍙樺寲鍒ゆ柇瑕佹帓闄ょ┖琛屻€佹櫘閫氭敞閲婅銆丣avaDoc 琛屻€?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_text_utils.py -v
```

Expected: `3 passed`銆?
---

## Task 4: JavaDoc 杞婚噺瑙ｆ瀽鍣?
**Files:**

- Create: `javadoc_miner/java_parser.py`
- Create: `tests/test_java_parser.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
from javadoc_miner.java_parser import parse_entities


def test_parse_method_javadoc_with_signature_parts():
    source = """
package org.example;

public class Person {
    /**
     * Returns the full name.
     *
     * @param fallback fallback value
     * @return full name
     * @throws IllegalStateException when missing
     */
    public String getFullName(String fallback) throws IllegalStateException {
        return fallback;
    }
}
"""

    entities = parse_entities(source)
    method = next(entity for entity in entities if entity.name == "getFullName")

    assert method.entity_type == "method"
    assert method.return_type == "String"
    assert method.parameters == ["String fallback"]
    assert method.throws == ["IllegalStateException"]
    assert "@param fallback" in method.javadoc


def test_parse_class_javadoc():
    source = """
/**
 * Person value object.
 */
public final class Person {
}
"""

    entities = parse_entities(source)

    assert entities[0].entity_type == "class"
    assert entities[0].name == "Person"


def test_parse_constructor_as_method_entity():
    source = """
public class Person {
    /**
     * Creates a person.
     */
    public Person(String name) {
    }
}
"""

    entities = parse_entities(source)

    assert entities[0].entity_type == "method"
    assert entities[0].name == "Person"
    assert entities[0].return_type == ""
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_java_parser.py -v
```

Expected: import 澶辫触鎴栬В鏋愬嚱鏁颁笉瀛樺湪銆?
- [x] **Step 3: 瀹炵幇瑙ｆ瀽鍣?*

瀹炵幇 `parse_entities(source: str) -> list[EntityDoc]`锛?
- 姝ｅ垯鎵弿褰㈠ `/** Returns the full display name. */` 鐨?JavaDoc 鍧楋紝璁板綍 JavaDoc 鏂囨湰銆?- 浠?JavaDoc 鍚庣户缁鍙栧０鏄庤锛岀洿鍒伴亣鍒?`{` 鎴?`;`銆?- 绫诲０鏄庡尮閰?`class|interface|enum|record`銆?- 鏂规硶澹版槑鍖归厤鍖呭惈 `(` 鍜?`)` 涓斾笉鏄帶鍒舵祦鍏抽敭瀛椼€?- 鎻愬彇鏂规硶鍚嶃€佸弬鏁板垪琛ㄣ€佽繑鍥炵被鍨嬨€乼hrows 鍒楄〃銆?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_java_parser.py -v
```

Expected: `3 passed`銆?
---

## Task 5: 鍒嗙被鍣?
**Files:**

- Create: `javadoc_miner/classifier.py`
- Create: `tests/test_classifier.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
from javadoc_miner.classifier import classify_entity_change
from javadoc_miner.models import EntityDoc


def entity(name, javadoc, return_type="String", parameters=None, throws=None):
    return EntityDoc(
        entity_type="method",
        name=name,
        signature=f"public {return_type} {name}()",
        javadoc=javadoc,
        start_line=1,
        end_line=5,
        return_type=return_type,
        parameters=parameters or [],
        throws=throws or [],
    )


def test_classify_method_rename_as_quality_a():
    old = entity("getName", "/** Returns name. */")
    new = entity("getFullName", "/** Returns full name. */")

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result.change_type == "method_rename"
    assert result.quality == "A"


def test_classify_parameter_change_as_quality_a():
    old = entity("format", "/** Formats value. */", parameters=["String value"])
    new = entity("format", "/** Formats value with locale. */", parameters=["String value", "Locale locale"])

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result.change_type == "parameter_change"
    assert result.quality == "A"


def test_classify_new_method_with_javadoc_as_quality_b():
    new = entity("isBlank", "/** Returns true when blank. */", return_type="boolean")

    result = classify_entity_change(None, new, nearby_code_changed=True)

    assert result.change_type == "method_addition"
    assert result.quality == "B"


def test_filter_only_see_change():
    old = entity("getName", "/** Returns name. */")
    new = entity("getName", "/** Returns name.\\n * @see Person\\n */")

    result = classify_entity_change(old, new, nearby_code_changed=True)

    assert result is None
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_classifier.py -v
```

Expected: import 澶辫触鎴栧垎绫诲嚱鏁颁笉瀛樺湪銆?
- [x] **Step 3: 瀹炵幇鍒嗙被鍑芥暟**

瀹炵幇锛?
- `classify_entity_change(old: EntityDoc | None, new: EntityDoc | None, nearby_code_changed: bool) -> Classification | None`
- JavaDoc 鏂囨湰褰掍竴鍖栧悗鏈彉鍖栧垯杩斿洖 `None`銆?- API 绾у彉鍖栬繑鍥?`A`銆?- 鏂板甯?JavaDoc 鐨勬柟娉曟垨绫昏繑鍥?`B`銆?- 浠?`@see` 鍙樺寲銆佺函鏍煎紡鍙樺寲杩斿洖 `None`銆?- 鏃犲己璇佹嵁浣嗛檮杩戜唬鐮佸彉鍖栬繑鍥?`C`銆?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_classifier.py -v
```

Expected: `4 passed`銆?
---

## Task 6: Git 浠撳簱涓?diff 鎻愬彇

**Files:**

- Create: `javadoc_miner/git_repo.py`
- Create: `javadoc_miner/diff_extractor.py`
- Create: `tests/test_diff_extractor.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
from javadoc_miner.diff_extractor import commit_has_javadoc_and_code_changes, parse_changed_paths


def test_parse_changed_paths_filters_main_java_files():
    name_status = "\\n".join([
        "M\\tsrc/main/java/org/example/Foo.java",
        "M\\tsrc/test/java/org/example/FooTest.java",
        "M\\tpom.xml",
    ])

    assert parse_changed_paths(name_status) == ["src/main/java/org/example/Foo.java"]


def test_commit_has_javadoc_and_code_changes_requires_both():
    patch = """
diff --git a/src/main/java/Foo.java b/src/main/java/Foo.java
-     * Returns name.
+     * Returns full name.
-    public String getName() {
+    public String getFullName() {
"""

    assert commit_has_javadoc_and_code_changes(patch)


def test_commit_has_javadoc_and_code_changes_rejects_docs_only():
    patch = """
-     * Returns name.
+     * Returns full name.
"""

    assert not commit_has_javadoc_and_code_changes(patch)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_diff_extractor.py -v
```

Expected: import 澶辫触鎴栧嚱鏁颁笉瀛樺湪銆?
- [x] **Step 3: 瀹炵幇 git 鍜?diff 灏佽**

`git_repo.py` 瀹炵幇锛?
- `GitRepo.clone_or_update(repo_url, cache_dir, force_refresh=False) -> GitRepo`
- `GitRepo.run_git(args: list[str]) -> str`
- `GitRepo.iter_commits(full_history: bool, max_commits: int) -> list[str]`
- `GitRepo.show_commit_patch(commit_hash: str) -> str`
- `GitRepo.show_file(commit_hash: str, path: str) -> str | None`
- `GitRepo.commit_url(commit_hash: str) -> str`

`diff_extractor.py` 瀹炵幇锛?
- `parse_changed_paths(name_status: str) -> list[str]`
- `commit_has_javadoc_and_code_changes(patch: str) -> bool`
- `extract_file_changes(repo: GitRepo, commit_hash: str) -> list[FileChange]`

- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_diff_extractor.py -v
```

Expected: `3 passed`銆?
---

## Task 7: 鏍锋湰鍐欏叆鍣?
**Files:**

- Create: `javadoc_miner/writer.py`
- Create: `tests/test_writer.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇?*

```python
import csv
import json

from javadoc_miner.models import OutputSample
from javadoc_miner.writer import SampleWriter


def make_sample(name="getFullName"):
    return OutputSample(
        repo="apache/commons-lang",
        commit_hash="abc123",
        commit_url="https://github.com/apache/commons-lang/commit/abc123",
        issue="LANG-1234",
        issues=["LANG-1234"],
        entity_type="method",
        entity_name=name,
        old_javadoc="/** Returns name. */",
        new_javadoc="/** Returns full name. */",
        patch="diff --git a/A.java b/A.java",
        commit_message="LANG-1234 rename method",
        change_type="method_rename",
        quality="A",
    )


def test_writer_creates_json_and_summary_csv(tmp_path):
    writer = SampleWriter(tmp_path)
    writer.write_samples([make_sample()])

    sample_path = tmp_path / "sample_0001.json"
    summary_path = tmp_path / "summary.csv"

    assert json.loads(sample_path.read_text(encoding="utf-8"))["entity_name"] == "getFullName"

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["sample_id"] == "sample_0001"
    assert rows[0]["quality"] == "A"
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_writer.py -v
```

Expected: import 澶辫触鎴?writer 涓嶅瓨鍦ㄣ€?
- [x] **Step 3: 瀹炵幇鍐欏叆鍣?*

瀹炵幇 `SampleWriter.write_samples(samples: list[OutputSample]) -> None`锛?
- 鍒涘缓鎴栨竻绌鸿緭鍑虹洰褰曘€?- 鎸?`sample_0001.json` 搴忓彿鍐?JSON銆?- 鍐?`summary.csv`锛屽瓧娈典负 `sample_id,repo,commit_hash,entity_name,change_type,quality`銆?- JSON 浣跨敤 `ensure_ascii=False` 鍜岀缉杩?2銆?
- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_writer.py -v
```

Expected: `1 passed`銆?
---

## Task 8: CLI 涓绘祦绋嬩笌闆嗘垚娴嬭瘯

**Files:**

- Create: `javadoc_miner/cli.py`
- Modify: `javadoc_miner/__main__.py`
- Create: `tests/test_cli_integration.py`

- [x] **Step 1: 鍐欏け璐ラ泦鎴愭祴璇?*

娴嬭瘯鍒涘缓涓存椂 git 浠撳簱锛屼笉渚濊禆缃戠粶锛?
```python
import subprocess
from pathlib import Path

from javadoc_miner.cli import mine_repository
from javadoc_miner.config import MinerConfig


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def test_mine_repository_extracts_method_rename_sample(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")

    java_path = repo / "src/main/java/org/example/Person.java"
    java_path.parent.mkdir(parents=True)
    java_path.write_text(
        '''
package org.example;

public class Person {
    /**
     * Returns the display name.
     */
    public String getName() {
        return "name";
    }
}
'''.strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")

    java_path.write_text(
        '''
package org.example;

public class Person {
    /**
     * Returns the full display name.
     */
    public String getFullName() {
        return "full name";
    }
}
'''.strip(),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "LANG-1234 rename getter")

    config = MinerConfig(
        repo_url=str(repo),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "dataset",
        max_commits=10,
        max_samples=10,
    )

    samples = mine_repository(config)

    assert len(samples) == 1
    assert samples[0].entity_name == "getFullName"
    assert samples[0].change_type == "method_rename"
    assert samples[0].quality == "A"
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

```bash
pytest tests/test_cli_integration.py -v
```

Expected: `mine_repository` 涓嶅瓨鍦ㄦ垨娴佺▼鏈疄鐜般€?
- [x] **Step 3: 瀹炵幇涓绘祦绋?*

`mine_repository(config: MinerConfig) -> list[OutputSample]` 娴佺▼锛?
1. `GitRepo.clone_or_update` 鍑嗗浠撳簱銆?2. 閬嶅巻 commit銆?3. 鎻愬彇 patch 鍜岀洰鏍囨枃浠跺彉鍖栥€?4. 绮楃瓫 commit 鏄惁鍚屾椂鍖呭惈 JavaDoc 鍜屼唬鐮佸彉鍖栥€?5. 瀵规瘡涓枃浠惰В鏋愭棫瀹炰綋銆佹柊瀹炰綋銆?6. 瀵归綈瀹炰綋骞惰皟鐢?classifier銆?7. 鏋勯€?`OutputSample`銆?8. 鍒拌揪 `max_samples` 鍋滄銆?9. 浣跨敤 `SampleWriter` 杈撳嚭鏁版嵁闆嗐€?
`__main__.py` 璋冪敤 `cli.main()`銆?
- [x] **Step 4: 杩愯闆嗘垚娴嬭瘯纭閫氳繃**

```bash
pytest tests/test_cli_integration.py -v
```

Expected: `1 passed`銆?
---

## Task 9: 鍏ㄩ噺楠岃瘉涓庣ず渚嬭繍琛?
**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-javadoc-miner.md`锛屽嬀閫夋墽琛岃繃鐨勬楠ゃ€?
- [x] **Step 1: 璺戝叏閮ㄦ祴璇?*

```bash
pytest -v
```

Expected: 鎵€鏈夋祴璇曢€氳繃銆?
- [x] **Step 2: 瀵?Apache Commons Lang 鍋氬皬瑙勬ā鐪熷疄杩愯**

```bash
python -m javadoc_miner mine \
  --repo-url https://github.com/apache/commons-lang \
  --max-commits 200 \
  --max-samples 10 \
  --output-dir dataset
```

Expected:

- `.cache/repos/apache__commons-lang` 瀛樺湪銆?- `dataset/sample_0001.json` 瀛樺湪锛岄櫎闈炴渶杩?200 涓?commit 娌℃湁绗﹀悎鏉′欢鏍锋湰銆?- `dataset/summary.csv` 瀛樺湪銆?- 鎺у埗鍙拌緭鍑烘壂鎻?commit 鏁般€佸€欓€?commit 鏁般€佹牱鏈暟銆?
- [x] **Step 3: 妫€鏌ヨ緭鍑?JSON**

```bash
python -m json.tool dataset/sample_0001.json
```

Expected: JSON 鏍煎紡鏈夋晥锛屽寘鍚?`repo`銆乣commit_hash`銆乣commit_url`銆乣entity_name`銆乣old_javadoc`銆乣new_javadoc`銆乣patch`銆乣change_type`銆乣quality`銆?
---

## 鑷煡娓呭崟

- [x] 姣忎釜鏂板嚱鏁伴兘鏈夋祴璇曡鐩栥€?- [x] 姣忎釜娴嬭瘯閮藉厛澶辫触锛屽啀瀹炵幇閫氳繃銆?- [x] `src/main/java/**/*.java` 杩囨护瑙勫垯琚祴璇曡鐩栥€?- [x] `src/test/java`銆佹祴璇曠被銆侀潪 Java 鏂囦欢浼氳蹇界暐銆?- [x] `A/B/C` 鍒嗙被瑙勫垯琚祴璇曡鐩栥€?- [x] `sample_0001.json` 鍜?`summary.csv` 鍐欏叆琚祴璇曡鐩栥€?- [x] 鍗曚釜 commit 澶辫触涓嶄細涓柇涓绘祦绋嬨€?- [x] 鐪熷疄 Apache Commons Lang 灏忚妯¤繍琛屾湁鏄庣‘杈撳嚭缁撴灉銆?
