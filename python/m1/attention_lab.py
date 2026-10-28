"""使用小型 PyTorch 张量演示 Scaled Dot-Product Attention 的完整计算过程。"""

import math

import torch
from torch import Tensor


# 固定打印格式，减少小数位数，方便观察每一步的结果。
torch.set_printoptions(precision=4, sci_mode=False)


def print_tensor(name: str, tensor: Tensor) -> None:
    """打印张量名称、形状和数值。"""
    print(f"\n{name}")
    print(f"形状：{tuple(tensor.shape)}")
    print(tensor)


def main() -> None:
    # 本实验只有一个 Batch、三个 Token，每个 Attention Head 的维度为 4。
    # Q、K、V 的形状均为 [batch_size, seq_len, head_dim]。
    batch_size = 1
    seq_len = 3
    head_dim = 4

    # Q：每个位置正在查询什么。
    # K：每个位置可以用什么特征与 Query 匹配。
    # V：匹配成功后，真正参与加权汇总的信息。
    # 真实模型中的 Q、K、V 通常由隐藏状态经过三个线性投影得到；
    # 这里直接构造小张量，以便专注观察 Attention 的计算过程。
    query = torch.tensor(
        [
            [
                [1.0, 0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0, 1.0],
                [1.0, 1.0, 0.0, 0.0],
            ]
        ]
    )
    key = torch.tensor(
        [
            [
                [1.0, 0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0, 1.0],
                [1.0, 1.0, 0.0, 0.0],
            ]
        ]
    )
    value = torch.tensor(
        [
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 2.0, 0.0, 0.0],
                [0.0, 0.0, 3.0, 0.0],
            ]
        ]
    )

    # 确认手工构造的维度符合实验设定。
    expected_shape = (batch_size, seq_len, head_dim)
    assert tuple(query.shape) == expected_shape
    assert tuple(key.shape) == expected_shape
    assert tuple(value.shape) == expected_shape

    print_tensor("步骤 1 - Q（Query）", query)
    print_tensor("步骤 1 - K（Key）", key)
    print_tensor("步骤 1 - V（Value）", value)

    with torch.no_grad():
        # 将 K 的最后两个维度从 [seq_len, head_dim] 转置为
        # [head_dim, seq_len]，才能计算每个 Query 与所有 Key 的点积。
        key_transposed = key.transpose(-2, -1)
        print_tensor("步骤 2 - Kᵀ", key_transposed)

        # [batch, seq_len, head_dim] @ [batch, head_dim, seq_len]
        # 得到 [batch, seq_len, seq_len]。
        # 分数矩阵的每一行代表一个 Query 对所有 Key 的匹配分数。
        attention_scores = query @ key_transposed
        print_tensor("步骤 3 - 原始分数 QKᵀ", attention_scores)

        # head_dim 越大，点积的数值通常越大。
        # 除以 sqrt(head_dim) 可以控制分数尺度，避免 Softmax 过度饱和。
        scale = math.sqrt(head_dim)
        scaled_scores = attention_scores / scale
        print(f"\n步骤 4 - 缩放因子 sqrt(head_dim)：{scale}")
        print_tensor("步骤 4 - 缩放后的分数", scaled_scores)

        # 这里模拟训练或 Prefill 时一次处理多个 Token 的 Attention。
        # Causal Mask 的上三角区域表示“未来位置”。
        # 行是当前 Query 位置，列是它准备关注的 Key 位置：
        # 第 0 行屏蔽位置 1、2；第 1 行屏蔽位置 2；第 2 行没有未来位置。
        # 单 Token Decode 时 KV Cache 只有历史 K、V，通常无需显式构造此矩阵。
        future_mask = torch.triu(
            torch.ones(seq_len, seq_len, dtype=torch.bool),
            diagonal=1,
        )
        print_tensor("步骤 5 - Causal Mask（True 表示未来位置，需要屏蔽）", future_mask)

        # 在执行 Softmax 之前，把未来位置的分数改为负无穷。
        # exp(-inf) = 0，所以这些位置经过 Softmax 后权重为 0。
        masked_scores = scaled_scores.masked_fill(future_mask, float("-inf"))
        print_tensor("步骤 6 - 应用 Causal Mask 后的分数", masked_scores)

        # dim=-1 表示对每个 Query 对应的一整行 Key 分数执行 Softmax。
        # 每行允许关注的位置权重之和应接近 1，屏蔽位置权重应接近 0。
        attention_weights = torch.softmax(masked_scores, dim=-1)
        print_tensor("步骤 7 - Softmax 后的 Attention 权重", attention_weights)

        row_sums = attention_weights.sum(dim=-1)
        print_tensor("步骤 8 - 每行 Attention 权重之和", row_sums)

        expected_sums = torch.ones_like(row_sums)
        weights_are_valid = torch.allclose(
            row_sums,
            expected_sums,
            atol=1e-6,
        )
        print(f"每行权重之和是否接近 1：{weights_are_valid}")
        assert weights_are_valid, "Softmax 后每行 Attention 权重之和应该接近 1"

        # 检查所有未来位置的权重。使用 future_mask 索引后，会取出上三角区域。
        future_weights = attention_weights[:, future_mask]
        future_weights_are_zero = torch.allclose(
            future_weights,
            torch.zeros_like(future_weights),
            atol=1e-6,
        )
        print(f"所有未来位置的权重是否接近 0：{future_weights_are_zero}")
        assert future_weights_are_zero, "Causal Mask 应使未来位置的权重接近 0"

        # 分别验证前两个 Token 的可见范围。
        first_token_only_sees_itself = torch.allclose(
            attention_weights[0, 0],
            torch.tensor([1.0, 0.0, 0.0]),
            atol=1e-6,
        )
        second_token_cannot_see_third = torch.isclose(
            attention_weights[0, 1, 2],
            torch.tensor(0.0),
            atol=1e-6,
        ).item()
        second_token_visible_weights = attention_weights[0, 1, :2]
        second_token_visible_weight_sum = second_token_visible_weights.sum()
        second_token_sees_first_two = (
            second_token_cannot_see_third
            and torch.all(second_token_visible_weights > 0).item()
            and torch.isclose(
                second_token_visible_weight_sum,
                torch.tensor(1.0),
                atol=1e-6,
            ).item()
        )

        print(f"第一个 Token 是否只能关注自己：{first_token_only_sees_itself}")
        print(f"第二个 Token 是否只能关注前两个位置：{second_token_sees_first_two}")
        assert first_token_only_sees_itself
        assert second_token_sees_first_two

        # 每个 Query 位置使用自己的一行权重，对当前及历史 Value 做加权求和。
        # [batch, seq_len, seq_len] @ [batch, seq_len, head_dim]
        # 得到 [batch, seq_len, head_dim]，所以输出仍保留原来的序列长度。
        attention_output = attention_weights @ value
        print_tensor("步骤 9 - Attention 权重乘以 V 的输出", attention_output)

    print("\n形状变化总结：")
    print(f"Q：                 {tuple(query.shape)}")
    print(f"Kᵀ：                {tuple(key_transposed.shape)}")
    print(f"QKᵀ：               {tuple(attention_scores.shape)}")
    print(f"Causal Mask：        {tuple(future_mask.shape)}")
    print(f"屏蔽后的分数：       {tuple(masked_scores.shape)}")
    print(f"Attention 权重：     {tuple(attention_weights.shape)}")
    print(f"V：                  {tuple(value.shape)}")
    print(f"Attention 输出：     {tuple(attention_output.shape)}")

    print("\n实验结论：")
    print("1. QKᵀ 产生一个 [seq_len, seq_len] 的 Token 两两匹配分数矩阵。")
    print("2. 除以 sqrt(head_dim) 用于稳定分数尺度，避免 Softmax 过度饱和。")
    print("3. Causal Mask 在 Softmax 前将未来位置的分数设为负无穷。")
    print("4. Softmax 后每行权重之和接近 1，被屏蔽的未来位置权重为 0。")
    print("5. 每个 Query 只能对当前位置及历史位置的 Value 做加权求和。")
    print("6. 每个输入位置产生一个输出，因此输出仍然保留 seq_len 维度。")


if __name__ == "__main__":
    main()
