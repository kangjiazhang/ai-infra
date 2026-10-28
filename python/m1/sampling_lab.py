"""使用固定的 logits 对比 Temperature、Top-k、Top-p 等采样策略的效果。"""

import math
from collections import Counter

# 玩具词表：Token ID 到可读名称的映射。
# 实验只关心采样分布，因此用简单标签代替真实词表。
TOY_VOCAB = {
    0: "大",
    1: "模型",
    2: "推理",
    3: "服务",
    4: "监控",
    5: "调度",
}

# 固定的一组 logits。
# 它们是模型在某个位置对每个候选 Token 的未归一化分数。
# 通过手动设置数值，可以观察不同采样策略如何改变最终分布。
BASE_LOGITS = [4.0, 3.0, 2.5, 2.0, 1.0, 0.5]

# 每种配置重复采样的次数。
# 次数越多，频率越接近真实概率；教学实验取 20 次便于快速观察。
SAMPLES_PER_CONFIG = 20


def softmax(values: list[float]) -> list[float]:
    """数值稳定的 Softmax：把任意实数转换为总和为 1 的概率。"""
    # 减去最大值不会改变结果，但能避免 exp 溢出。
    max_value = max(values)
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps)
    return [value / total for value in exps]


def apply_temperature(logits: list[float], temperature: float) -> list[float]:
    """按温度缩放 logits，再重新归一化为概率。"""
    if temperature == 0:
        # 温度为 0 通常等价于贪心：只选分数最高的 Token。
        return [1.0 if i == logits.index(max(logits)) else 0.0
                for i in range(len(logits))]
    scaled = [value / temperature for value in logits]
    return softmax(scaled)


def apply_top_k(probabilities: list[float], k: int) -> list[float]:
    """只保留概率最高的 k 个 Token，并把其余位置置 0 后重新归一化。"""
    if k <= 0:
        raise ValueError("k 必须大于 0")
    if k >= len(probabilities):
        # k 覆盖全部候选时，不产生任何过滤效果。
        return list(probabilities)

    # 按概率从高到低取出前 k 个位置的索引。
    top_indices = sorted(
        range(len(probabilities)),
        key=lambda index: probabilities[index],
        reverse=True,
    )[:k]

    filtered = [
        probabilities[index] if index in top_indices else 0.0
        for index in range(len(probabilities))
    ]
    total = sum(filtered)
    # 重新归一化，使保留候选的概率之和仍为 1。
    return [value / total for value in filtered]


def apply_top_p(probabilities: list[float], p: float) -> list[float]:
    """按累计概率截断：保留概率降序累加达到 p 的最小候选集合。"""
    if not 0 < p <= 1:
        raise ValueError("p 必须在 (0, 1] 范围内")
    if p >= 1:
        return list(probabilities)

    order = sorted(
        range(len(probabilities)),
        key=lambda index: probabilities[index],
        reverse=True,
    )

    cumulative = 0.0
    keep: set[int] = set()
    for index in order:
        keep.add(index)
        cumulative += probabilities[index]
        if cumulative >= p:
            break

    filtered = [
        probabilities[index] if index in keep else 0.0
        for index in range(len(probabilities))
    ]
    total = sum(filtered)
    return [value / total for value in filtered]


def sample_once(probabilities: list[float], seed: int) -> int:
    """确定性伪随机采样：使用线性同余生成器（LCG）选择一个 Token。

    Python 内置 random 也可以完成采样；这里实现一个固定种子的简单 LCG，
    是为了让每次运行脚本的频率统计完全可复现，便于对照学习。
    """
    state = seed
    # 归一化到 [0, 1) 的伪随机数。
    random_value = ((state * 1103515245 + 12345) % (2**31)) / (2**31)
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if random_value < cumulative:
            return index
    # 浮点误差兜底：返回最后一个概率不为 0 的位置。
    for index in range(len(probabilities) - 1, -1, -1):
        if probabilities[index] > 0:
            return index
    raise ValueError("概率全为 0，无法采样")


def run_config(
    label: str,
    probabilities: list[float],
    samples: int = SAMPLES_PER_CONFIG,
) -> None:
    """按给定概率分布采样多次，并打印每个 Token 的选中频率。"""
    counter: Counter[int] = Counter(
        sample_once(probabilities, seed) for seed in range(samples)
    )

    print(f"\n--- {label} ---")
    print(f"{'Token':<8} {'概率':>10} {'选中次数':>10} {'频率':>10} 条形图")
    for index, token in TOY_VOCAB.items():
        probability = probabilities[index]
        count = counter.get(index, 0)
        frequency = count / samples
        # 用 40 格宽度的简单条形图直观比较分布。
        bar = "█" * int(frequency * 40)
        print(
            f"{token:<8} {probability:>10.4f} {count:>10} "
            f"{frequency:>10.2f} {bar}"
        )


def main() -> None:
    """依次运行温度、Top-k、Top-p 三组对照实验。"""
    print("=" * 70)
    print("采样实验：固定 logits =", BASE_LOGITS)
    print("词表：", TOY_VOCAB)
    print(f"每种配置采样 {SAMPLES_PER_CONFIG} 次")
    print("=" * 70)

    print("\n原始概率分布（未做任何采样处理）")
    run_config("baseline（Temperature=1.0，无截断）", softmax(BASE_LOGITS))

    print("\n实验一：Temperature")
    for temperature in (0.2, 0.7, 1.5):
        label = f"temperature={temperature}"
        run_config(label, apply_temperature(BASE_LOGITS, temperature))
    print("\n观察：温度越低，概率越集中于高分 Token；温度越高，分布越平坦。")

    print("\n实验二：Top-k")
    for k in (1, 2, 3):
        label = f"top-k={k}"
        base = apply_temperature(BASE_LOGITS, 1.0)
        run_config(label, apply_top_k(base, k))
    print("\n观察：k=1 等价于贪心；k 越大，保留的候选越多，分布越接近原始分布。")

    print("\n实验三：Top-p")
    for p in (0.5, 0.8, 0.95):
        label = f"top-p={p}"
        base = apply_temperature(BASE_LOGITS, 1.0)
        run_config(label, apply_top_p(base, p))
    print("\n观察：top-p 的候选数量是动态的，取决于概率的累计分布。")

    print("\n结论：")
    print("1. Temperature 缩放 logits，改变整个分布的平坦程度。")
    print("2. Top-k 保留固定数量的候选 Token。")
    print("3. Top-p 保留累计概率达到阈值的最小候选集合，数量是动态的。")
    print("4. 这些参数影响输出的随机性与稳定性，不直接改变推理性能。")
    print("5. 采样发生在每一步 logits 之后；流式服务中会影响每个输出 Token。")


if __name__ == "__main__":
    main()
