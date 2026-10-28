# quality/

量化质量评估目录：

- `prompts.jsonl` — 20～50 条固定质量题集（事实问答/中文摘要/JSON/代码/长上下文抽取）
- `compare_outputs.py` — 对比 FP16 基线与量化模型输出（exact match / JSON 合法率 / 关键词覆盖）

规范：温度固定为 0；先保存 FP16 基线输出，量化模型与之对比；不能只看"显存减半"。
