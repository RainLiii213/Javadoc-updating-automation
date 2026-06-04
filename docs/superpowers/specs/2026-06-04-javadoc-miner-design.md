# JavaDoc 更新数据集挖掘工具设计文档

## 目标

构建一个 Python 命令行工具，用于从 GitHub 上的 Java 仓库中挖掘“代码变更与 JavaDoc 更新相关”的提交，并生成实体级数据集。第一版以 Apache Commons Lang 为试验仓库，后续应能扩展到其他 Apache Java 项目。

这里的“实体级”指一个样本对应一个被修改或新增的 Java 方法、构造器或类，而不是一个样本对应整个 commit。原因是一个 commit 可能同时修改多个方法的 JavaDoc，如果把它们混成一个样本，后续研究“某段代码变化为什么要求某段 JavaDoc 更新”时会引入噪声。

## 非目标

第一版不追求完整理解 Java 语义，也不调用大模型判断 JavaDoc 是否正确。它只做可解释的静态挖掘：从 git 历史、patch、前后版本文件和启发式 Java 结构解析中提取候选样本。

第一版不依赖 GitHub API。commit URL 可以根据仓库 URL 和 commit hash 拼出；只有未来需要 issue 标题、PR 信息、作者信息或 rate-limited 元数据时，才引入 GitHub API。

## 总体方案

采用“两阶段混合方案”：

1. 快速筛选 commit：用 git diff 判断 commit 是否修改了 `src/main/java/**/*.java`，且同一 commit 中同时存在 JavaDoc 变化和 Java 代码变化。
2. 实体级抽取：读取 commit 前后文件内容，用轻量 JavaDoc 解析器把 JavaDoc 块绑定到紧邻的方法、构造器或类，再判断 JavaDoc 变化和代码变化是否相关。

这个方案的核心理由是：研究工具第一版最重要的是稳定产出可审查样本，而不是一开始就完全解析 Java。快速筛选保证运行效率，实体级解析保证样本不只是一段粗糙 patch。解析器会设计成可替换接口，后续可替换为 Java AST parser。

## 命令行接口

入口命令：

```bash
python -m javadoc_miner mine --repo-url https://github.com/apache/commons-lang
```

常用参数：

```bash
python -m javadoc_miner mine \
  --repo-url https://github.com/apache/commons-lang \
  --max-commits 1000 \
  --max-samples 100 \
  --min-quality B \
  --output-dir dataset
```

全量扫描：

```bash
python -m javadoc_miner mine \
  --repo-url https://github.com/apache/commons-lang \
  --full-history \
  --min-quality C \
  --output-dir dataset
```

参数含义：

- `--repo-url`：目标 GitHub 仓库 URL。第一版只支持 URL 输入，由工具自动 clone。
- `--cache-dir`：仓库缓存目录，默认 `.cache/repos`。
- `--output-dir`：样本输出目录，默认 `dataset`。
- `--max-commits`：默认扫描 commit 数上限，建议默认 `1000`。
- `--max-samples`：默认输出样本数上限，建议默认 `100`。
- `--full-history`：忽略 `--max-commits`，遍历完整历史。
- `--min-quality`：最小样本质量，取值 `A`、`B`、`C`。默认 `B`，即输出 `A` 和 `B`，不输出弱相关样本 `C`。
- `--force-refresh`：删除并重新 clone 缓存仓库。用于缓存损坏或远程仓库大幅变化时。

## 文件结构

计划创建如下结构：

```text
javadoc_miner/
  __init__.py
  __main__.py
  cli.py
  config.py
  git_repo.py
  commit_walker.py
  diff_extractor.py
  java_parser.py
  classifier.py
  models.py
  writer.py
  issue_finder.py
  text_utils.py

tests/
  test_issue_finder.py
  test_java_parser.py
  test_classifier.py
  test_writer.py
  test_diff_extractor.py
```

模块职责：

- `cli.py`：解析参数，组织挖掘流程。
- `config.py`：保存命令行配置和默认值。
- `git_repo.py`：clone、fetch、生成 commit URL、执行 git 命令。
- `commit_walker.py`：按新到旧遍历 commit，处理数量限制。
- `diff_extractor.py`：过滤目标文件，提取 full patch、旧文件内容、新文件内容。
- `java_parser.py`：识别 JavaDoc 块，并绑定到方法、构造器、类。
- `classifier.py`：判断 change type 和 quality。
- `models.py`：定义数据结构，例如 `EntityDoc`、`CandidateSample`、`OutputSample`。
- `writer.py`：写 JSON 样本和 summary CSV。
- `issue_finder.py`：从 commit message 和 patch 提取 issue ID。
- `text_utils.py`：处理空白、格式变化、JavaDoc tag 判断等小工具。

## Git 操作设计

第一版使用直接 git 命令，通过 Python `subprocess` 调用，而不是 GitPython。

理由：

1. patch、父提交、文件前后版本这些能力本来就是 git 的强项。
2. 直接命令更接近研究者手动验证时看到的结果。
3. 减少第三方依赖，降低第一版安装失败概率。

关键命令：

```bash
git clone <repo-url> <cache-path>
git fetch --all --tags --prune
git rev-list --first-parent HEAD
git show --format=fuller --find-renames --patch <commit>
git diff-tree --no-commit-id --name-status -r <commit>
git show <commit>^:<path>
git show <commit>:<path>
```

默认遍历 `HEAD` 的 `--first-parent` 历史。原因是第一版更关注项目主线上的文档演化，而不是把所有合并分支的历史都展开。后续可以增加 `--all-parents` 支持完整 DAG 遍历。

## 文件过滤规则

只保留路径满足以下条件的文件：

- 位于 `src/main/java/` 下。
- 以 `.java` 结尾。

明确忽略：

- `src/test/java/`。
- 文件名中明显是测试类的 Java 文件，例如 `*Test.java`、`*Tests.java`、`Test*.java`。
- Markdown、XML、Gradle、Maven、Ant、shell 脚本等非 Java 源文件。

如果一个 commit 没有任何目标 Java 文件，直接跳过。

## JavaDoc 与实体解析

JavaDoc 定义为以 `/**` 开始、以 `*/` 结束的注释块。

JavaDoc tag 包括：

- `@param`
- `@return`
- `@throws`
- `@exception`
- `@see`
- `@since`

解析步骤：

1. 扫描文件，找到所有 JavaDoc 块的起止行和文本。
2. 找到 JavaDoc 块后面第一个非空、非注释的声明。
3. 如果声明是 `class`、`interface`、`enum`、`record`，绑定为类实体。
4. 如果声明看起来像方法或构造器签名，绑定为方法实体。
5. 记录实体名称、实体类型、签名文本、参数列表、返回类型、throws 列表和 JavaDoc 文本。

启发式解析必须保守：无法可靠识别的实体不生成高质量样本。这样做的原因是宁可少收一些，也不要把明显错误的实体名写进数据集。

## Commit 候选筛选

一个 commit 成为候选 commit，需要同时满足：

1. 至少一个目标 Java 文件发生变更。
2. patch 中存在 JavaDoc 变化，即新增或删除行包含 `/**`、`*/`、`@param`、`@return`、`@throws`、`@exception`、`@see`、`@since`，或者 JavaDoc 块内部文本发生变化。
3. patch 中存在 Java 代码变化，即新增或删除行不是空白、不是普通注释、不是 JavaDoc 行。

只改 JavaDoc 不算“代码与 JavaDoc 同时变化”。只改代码不算候选。

## 实体对齐规则

对每个变更文件，分别解析旧版本和新版本实体。

对齐优先级：

1. 同类型、同名、相同参数个数的实体。
2. 同类型、同名、参数列表相似的实体。
3. 同类型、签名相似但名称不同的实体，用于识别方法重命名。
4. 旧版本不存在、新版本存在的实体，视为新增方法或新增类。

如果一个 JavaDoc 块无法对齐到明确实体，则不输出 `A` 或 `B` 样本；只有在 `--min-quality C` 时，才允许输出弱相关候选。

## 分类规则

`quality = A`：API 级变化，并伴随对应 JavaDoc 更新。

可识别的 `change_type`：

- `method_rename`：方法名发生变化，并且 JavaDoc 更新。
- `parameter_change`：参数新增、删除、重命名或类型变化，并且 JavaDoc 更新。
- `return_type_change`：返回类型变化，并且 JavaDoc 更新。
- `exception_change`：`throws` 声明或 `@throws` / `@exception` 说明变化。
- `class_api_change`：类、接口、枚举或 record 声明变化，并且 JavaDoc 更新。

`quality = B`：新增方法或新增类，并带有 JavaDoc。

可识别的 `change_type`：

- `method_addition`
- `class_addition`

`quality = C`：JavaDoc 和代码都变了，但关系较弱。

可识别的 `change_type`：

- `body_behavior_change`
- `nearby_code_and_javadoc_change`
- `unknown_related_change`

低优先级变化：

- 只改拼写、标点、大小写。
- 只改空白、缩进、换行。
- 只新增或删除 `@see`。
- 只有 line wrapping 变化。

这些变化默认过滤；如果同时存在其他强证据，可以保留但降级。

## 输出格式

每个样本写入一个 JSON 文件：

```json
{
  "repo": "apache/commons-lang",
  "commit_hash": "4f8d9e0a1b2c3d4e5f60718293a4b5c6d7e8f901",
  "commit_url": "https://github.com/apache/commons-lang/commit/4f8d9e0a1b2c3d4e5f60718293a4b5c6d7e8f901",
  "issue": "LANG-1234",
  "issues": ["LANG-1234", "#1234"],
  "entity_type": "method",
  "entity_name": "getFullName",
  "old_javadoc": "/** Returns the display name. */",
  "new_javadoc": "/** Returns the full display name. */",
  "patch": "diff --git a/src/main/java/org/apache/commons/lang3/Person.java b/src/main/java/org/apache/commons/lang3/Person.java\\n- public String getName()\\n+ public String getFullName()",
  "commit_message": "LANG-1234 update JavaDoc for renamed method",
  "change_type": "method_rename",
  "quality": "A"
}
```

`issue` 保存第一个识别到的 issue ID，兼容简单数据消费场景。`issues` 保存全部识别结果，避免多个 issue ID 被丢掉。

样本文件路径：

```text
dataset/
  sample_0001.json
  sample_0002.json
  sample_0003.json
```

同时生成 summary CSV：

```csv
sample_id,repo,commit_hash,entity_name,change_type,quality
sample_0001,apache/commons-lang,abc123,getFullName,method_rename,A
```

## Issue ID 提取

从 commit message 和 patch 文本中提取：

- GitHub issue：`#1234`
- Apache JIRA：`LANG-1234`、`IO-1234`、`TEXT-1234` 等。

正则策略：

- `#[0-9]+`
- `[A-Z][A-Z0-9]+-[0-9]+`

提取结果去重并保持出现顺序。

## 错误处理

工具遇到单个 commit 解析失败时，不应中断整个挖掘流程。它应该记录错误并继续下一个 commit。

需要处理的错误：

- clone 失败：终止运行，并提示仓库 URL、目标缓存路径和 git 输出。
- git show 某个文件失败：跳过该文件，继续同 commit 其他文件。
- commit 没有父提交：通常是 initial commit，按新增文件处理。
- JavaDoc 解析失败：跳过该实体，不生成高质量样本。
- 输出文件已存在：默认清空并重建输出目录；后续可支持 `--append`。

错误日志第一版输出到控制台即可。后续大规模挖掘时可增加 `run.log` 和失败 commit 清单。

## 测试策略

采用 TDD。先写失败测试，再实现代码。

核心测试：

1. `issue_finder` 能提取 `#1234`、`LANG-1234`、`IO-1234`，并去重。
2. `java_parser` 能识别类 JavaDoc、方法 JavaDoc、构造器 JavaDoc。
3. `java_parser` 能提取方法名、参数、返回类型、throws。
4. `classifier` 能把方法重命名归为 `method_rename` 和 `A`。
5. `classifier` 能把新增带 JavaDoc 方法归为 `method_addition` 和 `B`。
6. `classifier` 能过滤纯格式变化和只新增 `@see`。
7. `writer` 能写出 `sample_0001.json`、`summary.csv`。
8. `diff_extractor` 能过滤掉 `src/test/java` 和非 `.java` 文件。

集成测试可以创建临时 git 仓库，构造两个 commit：第一个加入 Java 类，第二个修改方法签名和 JavaDoc。这样不用联网，也能验证完整挖掘流程。

## 可扩展性

后续扩展方向：

- 增加 `--repo-list`，从文本文件批量读取多个 GitHub URL。
- 增加 Java AST parser 适配器，替换启发式 `java_parser`。
- 增加 GitHub API 适配器，补充 issue 标题、PR URL、作者、提交日期。
- 增加人工审查模式，把 `quality=C` 的样本导出为待标注清单。
- 增加并行处理，但必须先保证单仓库单进程版本稳定。

## 验收标准

第一版完成后，应满足：

1. 能从 `https://github.com/apache/commons-lang` 自动 clone 仓库。
2. 默认限量扫描 commit，并支持 `--full-history`。
3. 只处理 `src/main/java/**/*.java`。
4. 能识别 commit 中代码与 JavaDoc 同时变化。
5. 能输出实体级 JSON 样本。
6. 能生成 `dataset/summary.csv`。
7. 能区分 `A`、`B`、`C` 质量等级。
8. 默认只输出 `A` 和 `B`。
9. 单个 commit 失败不会中断整个运行。
10. 有自动化测试覆盖解析、分类、写入和集成挖掘主流程。
