"""根据模型规格、精度、上下文和并发估算推理显存需求。"""

import argparse
import math
from dataclasses import dataclass, field
from typing import Callable

# 常见精度下每个参数或元素占用的字节数。
# FP16 与 BF16 通常都按 2 字节估算显存。
DTYPE_BYTES = {
    "fp32": 4,
    "fp16": 2,
    "bf16": 2,
    "int8": 1,
    "int4": 0.5,
}

# 以 1e9 为基准的十进制 GB；显存厂商通常按这个口径标称容量。
GIGA_BYTES = 1_000_000_000

# 常见 GPU 的显存容量（GB），用于推荐卡数。
# 该列表只做教学演示，选型时还应考虑算力、带宽、精度支持和价格。
GPU_OPTIONS = {
    "T4": 16,
    "A10": 24,
    "L20": 48,
    "L40S": 48,
    "A100-40G": 40,
    "A100-80G": 80,
    "H20-96G": 96,
    "H100-80G": 80,
}

# 常见模型规格预设：参数量、层数、KV Head 数、Head Dimension。
# 参数量单位为十亿（B = 1e9）。
MODEL_PRESETS = {
    "qwen2.5-0.5b": {"params_b": 0.5, "layers": 24, "kv_heads": 2, "head_dim": 64},
    "qwen2.5-7b": {"params_b": 7, "layers": 28, "kv_heads": 4, "head_dim": 128},
    "qwen2.5-14b": {"params_b": 14, "layers": 48, "kv_heads": 8, "head_dim": 128},
    "qwen2.5-32b": {"params_b": 32, "layers": 64, "kv_heads": 8, "head_dim": 128},
    "qwen2.5-72b": {"params_b": 72, "layers": 80, "kv_heads": 8, "head_dim": 128},
}


class ValidationError(ValueError):
    """输入参数不合法时抛出的异常。"""


@dataclass
class VRAMRequest:
    """一次显存估算所需的全部输入。"""

    # 模型参数量，单位：十亿（1e9）。
    params_b: float
    # 权重精度，决定每个参数占用的字节数。
    weight_dtype: str
    # Transformer 层数；KV Cache 需要为每一层分别保存 K、V。
    layers: int
    # KV Head 数量；GQA 模型中通常小于 Query Head 数。
    kv_heads: int
    # 单个 Head 的维度。
    head_dim: int
    # 单请求上下文长度（含 Prompt 和已生成输出）。
    context_tokens: int
    # 并发序列数量。
    concurrent_sequences: int
    # KV Cache 精度，可与权重精度不同（例如 FP8 KV）。
    kv_dtype: str
    # 框架、激活值、CUDA Context 等额外开销，按总显存的比例估算。
    overhead_ratio: float
    # 使用的 GPU 型号，用于推荐卡数。
    gpu_name: str = "A100-80G"


@dataclass
class VRAMEstimate:
    """显存估算的全部输出，单位统一为 GB（十进制）。"""

    weight_gib: float
    kv_cache_per_sequence_gib: float
    kv_cache_total_gib: float
    overhead_gib: float
    total_gib: float
    recommended_gpus: int
    gpu_name: str
    # 保存输出信息，便于打印成报告。
    notes: list[str] = field(default_factory=list)


def to_gib(num_bytes: float) -> float:
    """把字节数换算成 GiB，便于和 nvidia-smi 的显示口径对照。"""
    return num_bytes / (1024**3)


def parse_dtype(name: str) -> int:
    """校验并返回精度对应的每元素字节数。"""
    normalized = name.strip().lower()
    if normalized not in DTYPE_BYTES:
        allowed = ", ".join(DTYPE_BYTES)
        raise ValidationError(f"不支持的精度：{name}。可选值：{allowed}")
    return DTYPE_BYTES[normalized]


@dataclass
class VRAMCalculator:
    """根据输入规格计算权重、KV Cache 和总显存需求。"""

    request: VRAMRequest

    def __post_init__(self) -> None:
        """校验输入合法性，尽早发现明显错误。"""
        request = self.request
        if request.params_b <= 0:
            raise ValidationError("params_b 必须大于 0")
        if request.layers <= 0:
            raise ValidationError("layers 必须大于 0")
        if request.kv_heads <= 0:
            raise ValidationError("kv_heads 必须大于 0")
        if request.head_dim <= 0:
            raise ValidationError("head_dim 必须大于 0")
        if request.context_tokens <= 0:
            raise ValidationError("context_tokens 必须大于 0")
        if request.concurrent_sequences <= 0:
            raise ValidationError("concurrent_sequences 必须大于 0")
        if not 0 <= request.overhead_ratio < 1:
            raise ValidationError("overhead_ratio 必须在 [0, 1) 范围内")
        if request.gpu_name not in GPU_OPTIONS:
            allowed = ", ".join(GPU_OPTIONS)
            raise ValidationError(f"未知 GPU：{request.gpu_name}。可选值：{allowed}")

    def compute(self) -> VRAMEstimate:
        """执行显存估算并返回结果。"""
        request = self.request

        # 1. 权重显存 = 参数量 × 每参数字节数。
        weight_bytes = (
            request.params_b * 1e9 * parse_dtype(request.weight_dtype)
        )
        weight_gib = to_gib(weight_bytes)

        # 2. 单请求 KV Cache。
        # 每层保存一份 K 和一份 V（公式中的 2）。
        # kv_cache 与缓存 Token 数呈线性关系。
        kv_cache_per_sequence_bytes = (
            2
            * request.layers
            * request.kv_heads
            * request.head_dim
            * request.context_tokens
            * parse_dtype(request.kv_dtype)
        )
        kv_cache_per_sequence_gib = to_gib(kv_cache_per_sequence_bytes)

        # 3. 全部并发的 KV Cache。
        kv_cache_total_gib = kv_cache_per_sequence_gib * request.concurrent_sequences

        # 4. 框架、激活值与 CUDA Context 预留。
        # 这里的比例是教学估算；生产环境应以实测为准。
        model_plus_kv_gib = weight_gib + kv_cache_total_gib
        overhead_gib = model_plus_kv_gib * request.overhead_ratio

        # 5. 总显存需求。
        total_gib = model_plus_kv_gib + overhead_gib

        # 6. 推荐卡数：向上取整。
        # 多卡场景还需考虑 TP 切分后每张卡的权重与 KV 分布，
        # 这里只按总容量做最粗粒度的估算。
        gpu_capacity_gib = GPU_OPTIONS[request.gpu_name]
        recommended_gpus = math.ceil(total_gib / gpu_capacity_gib)

        notes: list[str] = []
        if request.weight_dtype in {"int8", "int4"}:
            notes.append(
                "权重量化可显著降低显存，但需要先确认模型已提供对应量化版本。",
            )
        if request.kv_dtype in {"int8", "int4"}:
            notes.append(
                "KV Cache 量化同样会引入精度损失，上线前应结合质量评估验证。",
            )
        if recommended_gpus > 1:
            notes.append(
                "多卡部署时，TP/PP 切分会改变每张卡的权重与 KV Cache 分布，"
                "本估算仅按总容量计算。",
            )
        notes.append(
            "容量估算不等于性能达标：并发与上下文还受调度参数和延迟 SLO 约束。",
        )

        return VRAMEstimate(
            weight_gib=weight_gib,
            kv_cache_per_sequence_gib=kv_cache_per_sequence_gib,
            kv_cache_total_gib=kv_cache_total_gib,
            overhead_gib=overhead_gib,
            total_gib=total_gib,
            recommended_gpus=recommended_gpus,
            gpu_name=request.gpu_name,
            notes=notes,
        )


def print_report(request: VRAMRequest, result: VRAMEstimate) -> None:
    """打印估算报告，包含输入、输出和关键结论。"""
    print("=" * 62)
    print("输入规格")
    print("=" * 62)
    print(f"模型参数量：          {request.params_b} B")
    print(f"权重精度：            {request.weight_dtype}")
    print(f"Transformer 层数：    {request.layers}")
    print(f"KV Head 数：          {request.kv_heads}")
    print(f"Head Dimension：      {request.head_dim}")
    print(f"上下文长度：          {request.context_tokens} tokens/请求")
    print(f"并发数：              {request.concurrent_sequences}")
    print(f"KV Cache 精度：       {request.kv_dtype}")
    print(f"框架预留比例：        {request.overhead_ratio:.0%}")
    print(f"目标 GPU：            {request.gpu_name}")

    print("=" * 62)
    print("估算结果（GiB）")
    print("=" * 62)
    print(f"模型权重显存：        {result.weight_gib:.2f} GiB")
    print(f"单请求 KV Cache：     {result.kv_cache_per_sequence_gib:.2f} GiB")
    print(f"全部并发 KV Cache：   {result.kv_cache_total_gib:.2f} GiB")
    print(f"框架预留显存：        {result.overhead_gib:.2f} GiB")
    print(f"总显存需求：          {result.total_gib:.2f} GiB")
    print(
        f"推荐 GPU 数量：       {result.recommended_gpus} 张 "
        f"({result.gpu_name}, {GPU_OPTIONS[result.gpu_name]} GB/张)",
    )

    print("=" * 62)
    print("说明")
    print("=" * 62)
    for note in result.notes:
        print(f"- {note}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数，未指定时使用 Qwen2.5-7B 的默认示例。"""
    parser = argparse.ArgumentParser(
        description="估算 LLM 推理的权重与 KV Cache 显存需求",
    )
    parser.add_argument(
        "--preset",
        choices=sorted(MODEL_PRESETS),
        default="qwen2.5-7b",
        help="使用预设模型规格；可再用其他参数覆盖",
    )
    parser.add_argument("--params-b", type=float, help="模型参数量（单位：十亿）")
    parser.add_argument("--layers", type=int, help="Transformer 层数")
    parser.add_argument("--kv-heads", type=int, help="KV Head 数量")
    parser.add_argument("--head-dim", type=int, help="单个 Head 的维度")
    parser.add_argument(
        "--weight-dtype",
        choices=sorted(DTYPE_BYTES),
        default="fp16",
        help="权重精度，默认 fp16",
    )
    parser.add_argument(
        "--kv-dtype",
        choices=sorted(DTYPE_BYTES),
        default="fp16",
        help="KV Cache 精度，默认 fp16",
    )
    parser.add_argument(
        "--context-tokens",
        type=int,
        default=4096,
        help="单请求上下文长度，默认 4096",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="并发序列数，默认 8",
    )
    parser.add_argument(
        "--overhead-ratio",
        type=float,
        default=0.15,
        help="框架/激活/CUDA 预留比例，默认 0.15",
    )
    parser.add_argument(
        "--gpu",
        choices=sorted(GPU_OPTIONS),
        default="A100-80G",
        help="用于推荐卡数的 GPU 型号，默认 A100-80G",
    )
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> VRAMRequest:
    """把命令行参数合并进预设规格，构造一次估算输入。"""
    preset = MODEL_PRESETS[args.preset]
    return VRAMRequest(
        params_b=args.params_b if args.params_b is not None else preset["params_b"],
        weight_dtype=args.weight_dtype,
        layers=args.layers if args.layers is not None else preset["layers"],
        kv_heads=args.kv_heads if args.kv_heads is not None else preset["kv_heads"],
        head_dim=args.head_dim if args.head_dim is not None else preset["head_dim"],
        context_tokens=args.context_tokens,
        concurrent_sequences=args.concurrency,
        kv_dtype=args.kv_dtype,
        overhead_ratio=args.overhead_ratio,
        gpu_name=args.gpu,
    )


def run_demo_scenarios() -> None:
    """运行几组对照场景，验证关键变量对显存的影响方向。"""
    scenarios: list[tuple[str, Callable[[], VRAMRequest], str]] = [
        (
            "基线：Qwen2.5-7B / FP16 / 4K 上下文 / 并发 8",
            lambda: VRAMRequest(
                params_b=7,
                weight_dtype="fp16",
                layers=28,
                kv_heads=4,
                head_dim=128,
                context_tokens=4096,
                concurrent_sequences=8,
                kv_dtype="fp16",
                overhead_ratio=0.15,
            ),
            "作为后续场景的对照基线。",
        ),
        (
            "上下文翻倍：8K",
            lambda: VRAMRequest(
                params_b=7,
                weight_dtype="fp16",
                layers=28,
                kv_heads=4,
                head_dim=128,
                context_tokens=8192,
                concurrent_sequences=8,
                kv_dtype="fp16",
                overhead_ratio=0.15,
            ),
            "其他条件不变时，单请求 KV Cache 约为基线的 2 倍。",
        ),
        (
            "并发翻倍：16",
            lambda: VRAMRequest(
                params_b=7,
                weight_dtype="fp16",
                layers=28,
                kv_heads=4,
                head_dim=128,
                context_tokens=4096,
                concurrent_sequences=16,
                kv_dtype="fp16",
                overhead_ratio=0.15,
            ),
            "单请求 KV 不变，总 KV Cache 约为基线的 2 倍。",
        ),
        (
            "INT4 权重量化",
            lambda: VRAMRequest(
                params_b=7,
                weight_dtype="int4",
                layers=28,
                kv_heads=4,
                head_dim=128,
                context_tokens=4096,
                concurrent_sequences=8,
                kv_dtype="fp16",
                overhead_ratio=0.15,
            ),
                "权重显存约为 FP16 的 1/4，KV Cache 不变。",
        ),
        (
            "GQA：kv_heads 从 4 变为 1（对照用）",
            lambda: VRAMRequest(
                params_b=7,
                weight_dtype="fp16",
                layers=28,
                kv_heads=1,
                head_dim=128,
                context_tokens=4096,
                concurrent_sequences=8,
                kv_dtype="fp16",
                overhead_ratio=0.15,
            ),
            "仅当真实模型确为此配置时成立；KV Head 减少 4 倍，KV Cache 约降为 1/4。",
        ),
    ]

    print("=" * 62)
    print("对照实验")
    print("=" * 62)
    for title, build, expectation in scenarios:
        result = VRAMCalculator(request=build()).compute()
        print(f"\n{title}")
        print(f"  权重：{result.weight_gib:.2f} GiB，"
              f"单请求 KV：{result.kv_cache_per_sequence_gib:.2f} GiB，"
              f"总 KV：{result.kv_cache_total_gib:.2f} GiB，"
              f"总需求：{result.total_gib:.2f} GiB")
        print(f"  预期：{expectation}")


def main() -> None:
    """命令行入口：先输出指定场景报告，再运行对照实验。"""
    args = parse_args()

    try:
        request = build_request(args)
        result = VRAMCalculator(request=request).compute()
    except ValidationError as error:
        raise SystemExit(f"输入错误：{error}") from error

    print_report(request, result)
    run_demo_scenarios()


if __name__ == "__main__":
    main()
