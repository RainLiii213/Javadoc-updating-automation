# Final Dataset / 最终数据集

## 中文

此目录保存通过高精度筛选的 Patch-Aware Javadoc Updating 样本。
当前累计样本数：**2000**。

每个项目保存在独立子目录中，`combined_samples.json` 汇总全部项目，
`summary.csv` 保存项目来源和简单挖掘统计。样本 JSON 始终只包含六个任务字段。

## English

This directory stores high-precision Patch-Aware Javadoc Updating samples.
Current cumulative sample count: **2000**.

Each repository has its own subdirectory. `combined_samples.json` aggregates
all repositories, and `summary.csv` records source and simple mining metadata.
Sample JSON objects always contain only the six task fields.

Method-level samples contain complete methods or constructors. Class-level
samples contain a structurally complete class context. Invalid or arbitrarily
truncated code is never promoted to this directory.

Repositories whose metadata has `complete_history: false` stopped before their
full history was exhausted. Consult `stop_reason` for the exact reason.

## Sources

- `apache_commons_codec`: 41 samples
- `apache_commons_collections`: 72 samples
- `apache_commons_compress`: 181 samples
- `apache_commons_io`: 39 samples
- `apache_commons_lang`: 37 samples
- `apache_commons_math`: 561 samples
- `apache_commons_text`: 35 samples
- `apache_lucene`: 618 samples
- `google_guava`: 291 samples
- `jodaorg_joda_time`: 125 samples
