"""使用小型 Hugging Face 模型在 CPU 上对比 Prefill 与 Decode 耗时。

实验设计：
1. 使用同一个模型分别处理短 Prompt 和长 Prompt。
2. 两组实验都使用贪心解码，并生成相同数量的 Token。
3. 手动拆开 Prefill 和逐 Token Decode，不直接调用 model.generate()，方便单独计时。
4. 记录 TTFT、Prefill、TPOT 和总耗时，并将结果保存为 JSON 与 CSV。

注意：这是用于建立推理直觉的 CPU 实验，不代表 GPU 生产环境的绝对性能。
"""

# 标准库分别用于：命令行参数、结果文件、环境信息、统计与高精度计时。
import argparse
import csv
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# AutoTokenizer 负责文本与 Token ID 之间的转换；
# AutoModelForCausalLM 加载带 LM Head 的 Decoder-only 因果语言模型。
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


# 0.5B 模型体积较小，更适合无 GPU 环境下完成学习实验。
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# 两组实验只改变 Prompt 长度，输出 Token 数、模型和解码策略保持一致。
SHORT_PROMPT = "请用一句话解释什么是 KV Cache。"
LONG_PROMPT = """
请从大模型推理服务的角度解释 KV Cache，包括它保存的数据、为什么能够加速自回归生成、
显存占用与模型层数、KV Head 数、Head Dimension、上下文长度、并发数和数据类型之间的关系，
并说明长上下文与高并发为什么容易造成显存不足。请结合 Prefill、Decode、TTFT、TPOT、
PagedAttention、GQA 和容量规划进行分析。不要直接给结论，要先说明一次请求的数据流。
""".strip() * 8


def parse_args() -> argparse.Namespace:
    """读取实验参数，使模型、输出长度、重复次数和 CPU 线程数可调。"""
    parser = argparse.ArgumentParser(
        description="在 CPU 上比较短、长 Prompt 的 Prefill 和 Decode 耗时",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face 模型名称")
    parser.add_argument("--new-tokens", type=int, default=12, help="固定生成的 Token 数")
    parser.add_argument("--repeats", type=int, default=2, help="每种 Prompt 重复次数")
    parser.add_argument(
        "--threads",
        type=int,
        default=min(os.cpu_count() or 1, 8),
        help="PyTorch CPU 线程数",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "results",
        help="实验结果目录",
    )
    return parser.parse_args()


def apply_chat_template(tokenizer: Any, prompt: str) -> str:
    """把用户文本转换成模型训练时使用的对话格式。"""
    try:
        return tokenizer.apply_chat_template(
            # Instruct 模型通常期望由 role 和 content 组成的消息列表。
            [{"role": "user", "content": prompt}],
            # 此处先返回格式化文本，后面才能单独统计 Tokenization 耗时。
            tokenize=False,
            # 在末尾添加 Assistant 起始标记，告诉模型接下来应该生成回答。
            add_generation_prompt=True,
        )
    except (AttributeError, ValueError, TypeError):
        # Base 模型或部分 Tokenizer 没有 Chat Template，直接使用原始文本。
        return prompt


def collect_environment(model_name: str, threads: int) -> dict[str, Any]:
    """收集复现实验所需的硬件、运行时、依赖版本和模型信息。"""
    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        "model": model_name,
        "device": "cpu",
        "dtype": "float32",
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "logical_cpu_count": os.cpu_count(),
        "pytorch_threads": threads,
        "python_version": sys.version.split()[0],
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
    }


def benchmark_once(
    model: Any,
    tokenizer: Any,
    label: str,
    prompt: str,
    new_tokens: int,
    run: int,
) -> dict[str, Any]:
    """完成一次固定输出长度的贪心生成，并分别记录 Prefill 与 Decode。

    这里不使用 ``model.generate()``，因为它会把 Prefill、Decode、采样和停止判断
    封装在一起，不便于观察各阶段的输入形态和耗时。
    """
    # perf_counter 是适合性能测量的单调高精度时钟，不受系统时间校准影响。
    # TTFT 从请求处理开始计时，所以包含模板处理、Tokenization 和 Prefill。
    request_start = time.perf_counter()

    formatted_prompt = apply_chat_template(tokenizer, prompt)

    # Tokenizer 在 CPU 上把字符串编码为 Token ID 和 Attention Mask。
    tokenization_start = time.perf_counter()
    encoded = tokenizer(
        formatted_prompt,
        # 返回 PyTorch Tensor，而不是普通 Python 列表。
        return_tensors="pt",
        # Chat Template 已经添加模型所需的特殊标记，避免再次重复添加。
        add_special_tokens=False,
    )
    tokenization_seconds = time.perf_counter() - tokenization_start

    # input_ids 形状为 [batch, prompt_len]；本实验 batch 固定为 1。
    # attention_mask 中 1 表示有效 Token，0 通常表示 Padding。
    input_ids = encoded["input_ids"].to("cpu")
    attention_mask = encoded["attention_mask"].to("cpu")
    prompt_tokens = int(input_ids.shape[1])

    # generated_ids 保存每轮选出的 Token ID；decode_step_seconds 保存每轮 Decode 耗时。
    generated_ids: list[torch.Tensor] = []
    decode_step_seconds: list[float] = []

    # 推理无需梯度；关闭 Autograd 可以减少内存占用和额外开销。
    with torch.inference_mode():
        # ==================== Prefill 阶段 ====================
        # 一次输入完整 Prompt：[batch, prompt_len]。
        # 模型会逐层并行处理 Prompt Token，并建立所有历史位置的 KV Cache。
        prefill_start = time.perf_counter()
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            # 要求模型返回每层 K、V，供后续 Decode 复用。
            use_cache=True,
        )

        # outputs.logits 逻辑形状为 [batch, prompt_len, vocab_size]。
        # 只有最后一个有效 Prompt 位置用于预测首个输出 Token。
        # argmax 是贪心解码：选择分数最高的 Token，排除随机采样对实验的影响。
        next_token = torch.argmax(outputs.logits[:, -1, :], dim=-1, keepdim=True)

        # past_key_values 保存各 Transformer 层的历史 K、V。
        past_key_values = outputs.past_key_values
        generated_ids.append(next_token)

        # 将首个 Token ID 转为文本片段，近似模拟流式服务产生首个输出。
        first_token_text = tokenizer.decode(
            next_token[0].tolist(),
            skip_special_tokens=False,
        )
        prefill_seconds = time.perf_counter() - prefill_start
        ttft_seconds = time.perf_counter() - request_start

        # ==================== Decode 阶段 ====================
        # 首个输出 Token 已由 Prefill 最后位置的 logits 产生。
        # 后续每轮只输入上轮生成的一个 Token，并复用、扩展历史 KV Cache。
        current_token = next_token
        for _ in range(1, new_tokens):
            # 上下文新增一个有效 Token，因此 Attention Mask 的长度也增加 1。
            # Mask 覆盖完整上下文，而 input_ids 只传当前新 Token。
            attention_mask = torch.cat(
                [
                    attention_mask,
                    torch.ones(
                        (attention_mask.shape[0], 1),
                        dtype=attention_mask.dtype,
                    ),
                ],
                dim=1,
            )

            decode_start = time.perf_counter()
            outputs = model(
                # 形状为 [batch, 1]，而不是重新输入完整上下文。
                input_ids=current_token,
                attention_mask=attention_mask,
                # 复用历史 K、V，避免重复计算所有历史 Token。
                past_key_values=past_key_values,
                # 返回追加当前 Token 后的新 KV Cache。
                use_cache=True,
            )

            # Decode 输出的 logits 形状为 [batch, 1, vocab_size]。
            current_token = torch.argmax(
                outputs.logits[:, -1, :],
                dim=-1,
                keepdim=True,
            )
            # 用包含当前 Token 的缓存替换旧缓存，供下一轮继续使用。
            past_key_values = outputs.past_key_values
            generated_ids.append(current_token)

            # 流式服务通常会在每轮 Decode 后增量解码当前 Token。
            # 本实验把该步骤计入 TPOT，使其更接近客户端实际感知的生成间隔。
            tokenizer.decode(
                current_token[0].tolist(),
                skip_special_tokens=False,
            )
            decode_step_seconds.append(time.perf_counter() - decode_start)

    # 将每轮形状为 [batch, 1] 的 Token 拼成 [batch, output_len]。
    generated_tensor = torch.cat(generated_ids, dim=1)
    # 将完整输出序列一次性解码，主要用于检查模型确实完成了生成。
    generated_text = tokenizer.decode(
        generated_tensor[0].tolist(),
        skip_special_tokens=True,
    )
    total_seconds = time.perf_counter() - request_start
    decode_seconds = sum(decode_step_seconds)

    # 统一转换成毫秒，便于阅读和写入 CSV。
    # TTFT 包含请求预处理和 Prefill；prefill_ms 只统计模型 Prefill 与首 Token 解码。
    # decode_tpot_ms 是首 Token 之后各轮 Decode 耗时的算术平均值。
    return {
        "case": label,
        "run": run,
        "prompt_characters": len(prompt),
        "prompt_tokens": prompt_tokens,
        "output_tokens": int(generated_tensor.shape[1]),
        "tokenization_ms": tokenization_seconds * 1000,
        "prefill_ms": prefill_seconds * 1000,
        "ttft_ms": ttft_seconds * 1000,
        "decode_ms": decode_seconds * 1000,
        "decode_tpot_ms": (
            statistics.mean(decode_step_seconds) * 1000
            if decode_step_seconds
            # 只生成一个 Token 时没有后续 Decode 轮次，TPOT 记为 0。
            else 0.0
        ),
        "total_ms": total_seconds * 1000,
        "first_token_text": first_token_text,
        "generated_text": generated_text,
    }


def median_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按短、长 Prompt 分组计算主要指标的中位数。"""
    # 性能实验可能受到操作系统调度和后台任务影响；中位数比平均数更不易受偶发尖峰干扰。
    metrics = [
        "prompt_tokens",
        "output_tokens",
        "tokenization_ms",
        "prefill_ms",
        "ttft_ms",
        "decode_ms",
        "decode_tpot_ms",
        "total_ms",
    ]
    summaries: list[dict[str, Any]] = []

    for label in ("short", "long"):
        group = [result for result in results if result["case"] == label]
        summary: dict[str, Any] = {"case": label}
        for metric in metrics:
            summary[metric] = statistics.median(
                float(result[metric]) for result in group
            )
        summaries.append(summary)

    return summaries


def print_summary(summaries: list[dict[str, Any]]) -> None:
    """打印对照结果和结论提示。"""
    print("\n=== 中位数结果 ===")
    print(
        f"{'类型':<8} {'Prompt Token':>13} {'Output Token':>13} "
        f"{'Prefill(ms)':>12} {'TTFT(ms)':>10} {'TPOT(ms)':>10} {'Total(ms)':>11}"
    )
    print("-" * 86)

    for item in summaries:
        print(
            f"{item['case']:<8} "
            f"{item['prompt_tokens']:>13.0f} "
            f"{item['output_tokens']:>13.0f} "
            f"{item['prefill_ms']:>12.2f} "
            f"{item['ttft_ms']:>10.2f} "
            f"{item['decode_tpot_ms']:>10.2f} "
            f"{item['total_ms']:>11.2f}"
        )

    short = next(item for item in summaries if item["case"] == "short")
    long = next(item for item in summaries if item["case"] == "long")
    ratio = long["prefill_ms"] / short["prefill_ms"] if short["prefill_ms"] else 0

    print(f"\n长/短 Prompt 的 Prefill 耗时比：{ratio:.2f} 倍")
    print("固定输出 Token 数后，重点比较 Prefill、TTFT 与 Decode TPOT。")
    print("预期：长 Prompt 主要增加 Prefill 和 TTFT；Decode TPOT 也可能因 KV Cache 变长而上升。")
    print("注意：这是 CPU 直觉实验，不能据此验证 GPU 的 Compute-bound/Memory-bound 程度。")


def save_results(
    output_dir: Path,
    environment: dict[str, Any],
    results: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> tuple[Path, Path]:
    """将环境、逐次结果和汇总结果保存为 JSON 与 CSV。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"prefill-decode-cpu-{timestamp}.json"
    csv_path = output_dir / f"prefill-decode-cpu-{timestamp}.csv"

    json_path.write_text(
        json.dumps(
            {
                "environment": environment,
                "results": results,
                "median_summary": summaries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    fieldnames = [
        "case",
        "run",
        "prompt_characters",
        "prompt_tokens",
        "output_tokens",
        "tokenization_ms",
        "prefill_ms",
        "ttft_ms",
        "decode_ms",
        "decode_tpot_ms",
        "total_ms",
        "first_token_text",
        "generated_text",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    return json_path, csv_path


def main() -> None:
    """初始化实验环境，加载一次模型，执行对照测试并保存结果。"""
    args = parse_args()

    # 尽早拒绝无意义参数，避免模型下载和加载完成后才报错。
    if args.new_tokens < 1:
        raise ValueError("--new-tokens 必须大于等于 1")
    if args.repeats < 1:
        raise ValueError("--repeats 必须大于等于 1")

    # 固定 PyTorch 使用的 CPU 线程数，减少不同实验之间的资源配置差异。
    torch.set_num_threads(args.threads)
    environment = collect_environment(args.model, args.threads)

    print("=== 实验环境 ===")
    print(json.dumps(environment, ensure_ascii=False, indent=2))
    print(f"\n正在加载模型：{args.model}")

    # Fast Tokenizer 通常由 Rust tokenizers 库实现，编码速度更快。
    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)

    # CausalLM 表示模型带有将隐藏状态投影到词表 logits 的 LM Head。
    # CPU 使用 float32 以获得最通用的算子支持；模型只加载一次，供所有实验复用。
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float32,
    )
    model.to("cpu")
    # eval() 关闭 Dropout 等训练行为，使多次推理更稳定。
    model.eval()

    # 首次前向可能触发内存分配、算子初始化和缓存建立。
    # 先用独立样本预热，避免这些一次性开销只污染短 Prompt 的第一组数据。
    print("正在预热模型……")
    benchmark_once(
        model=model,
        tokenizer=tokenizer,
        label="warmup",
        prompt="你好",
        new_tokens=min(args.new_tokens, 2),
        run=0,
    )

    cases = [("short", SHORT_PROMPT), ("long", LONG_PROMPT)]
    results: list[dict[str, Any]] = []

    for run in range(1, args.repeats + 1):
        for label, prompt in cases:
            print(f"正在运行：case={label}，run={run}/{args.repeats}")
            result = benchmark_once(
                model=model,
                tokenizer=tokenizer,
                label=label,
                prompt=prompt,
                new_tokens=args.new_tokens,
                run=run,
            )
            results.append(result)

    summaries = median_summary(results)
    print_summary(summaries)
    json_path, csv_path = save_results(
        args.output_dir,
        environment,
        results,
        summaries,
    )

    print(f"\nJSON 结果：{json_path}")
    print(f"CSV 结果： {csv_path}")


if __name__ == "__main__":
    main()
