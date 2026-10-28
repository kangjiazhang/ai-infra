"""观察 PyTorch MultiheadAttention 与 Transformer Block 各阶段的张量形状。"""

from typing import TypedDict

import torch
from torch import Tensor, nn


# 固定随机种子和打印格式，保证多次运行的结果便于比较。
torch.manual_seed(42)
torch.set_printoptions(precision=4, sci_mode=False)


class BlockOutputs(TypedDict):
    """保存 Transformer Block 每个阶段的中间结果。"""

    attention_output: Tensor
    attention_weights: Tensor
    first_residual: Tensor
    first_norm: Tensor
    ffn_hidden: Tensor
    ffn_activated: Tensor
    ffn_output: Tensor
    second_residual: Tensor
    block_output: Tensor


class PostNormTransformerBlock(nn.Module):
    """用于学习张量流动的简化 Post-Norm Transformer Block。"""

    def __init__(self, hidden_size: int, num_heads: int, ffn_size: int) -> None:
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            dropout=0.0,
            batch_first=True,
        )
        self.norm1 = nn.LayerNorm(hidden_size)
        self.ffn_in = nn.Linear(hidden_size, ffn_size)
        self.activation = nn.GELU()
        self.ffn_out = nn.Linear(ffn_size, hidden_size)
        self.norm2 = nn.LayerNorm(hidden_size)

    def forward(self, inputs: Tensor) -> BlockOutputs:
        # Self-Attention 的 Q、K、V 都来自同一份输入。
        attention_output, attention_weights = self.attention(
            query=inputs,
            key=inputs,
            value=inputs,
            need_weights=True,
            # 保留每个 Head 的权重，便于观察 Head 数量对应的维度。
            average_attn_weights=False,
        )

        # Post-Norm 结构：子层输出先与原输入相加，再执行 LayerNorm。
        first_residual = inputs + attention_output
        first_norm = self.norm1(first_residual)

        # FFN 先将 hidden_size 扩大到 ffn_size，再投影回 hidden_size。
        ffn_hidden = self.ffn_in(first_norm)
        ffn_activated = self.activation(ffn_hidden)
        ffn_output = self.ffn_out(ffn_activated)

        second_residual = first_norm + ffn_output
        block_output = self.norm2(second_residual)

        return {
            "attention_output": attention_output,
            "attention_weights": attention_weights,
            "first_residual": first_residual,
            "first_norm": first_norm,
            "ffn_hidden": ffn_hidden,
            "ffn_activated": ffn_activated,
            "ffn_output": ffn_output,
            "second_residual": second_residual,
            "block_output": block_output,
        }


def count_parameters(module: nn.Module) -> int:
    """统计模块中的全部可训练参数。"""
    return sum(parameter.numel() for parameter in module.parameters())


def compare_head_counts(inputs: Tensor, head_counts: list[int]) -> None:
    """改变 Head 数量，比较输出与 Attention 权重的形状。"""
    hidden_size = inputs.shape[-1]

    print("\n=== 实验 1：改变 Head 数量 ===")
    print(f"输入形状：[batch, seq_len, hidden_size] = {tuple(inputs.shape)}")

    for num_heads in head_counts:
        if hidden_size % num_heads != 0:
            print(f"跳过 num_heads={num_heads}：hidden_size 必须能被 num_heads 整除")
            continue

        attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            dropout=0.0,
            batch_first=True,
        )
        attention.eval()

        with torch.no_grad():
            output, weights = attention(
                query=inputs,
                key=inputs,
                value=inputs,
                need_weights=True,
                average_attn_weights=False,
            )

        head_dim = hidden_size // num_heads
        print(f"\nnum_heads={num_heads}，head_dim={head_dim}")
        print(f"Attention 前：{tuple(inputs.shape)}")
        print(f"Attention 后：{tuple(output.shape)}")
        print(f"权重形状：    {tuple(weights.shape)}  # [batch, heads, query_len, key_len]")
        print(f"参数量：      {count_parameters(attention)}")

        # 固定 hidden_size 时，改变 Head 数量只会改变拆分方式，整体输出形状不变。
        assert output.shape == inputs.shape
        assert weights.shape == (
            inputs.shape[0],
            num_heads,
            inputs.shape[1],
            inputs.shape[1],
        )


def print_block_shapes(inputs: Tensor) -> None:
    """运行一个简化 Transformer Block，并打印每一步张量形状。"""
    hidden_size = inputs.shape[-1]
    num_heads = 2
    ffn_size = hidden_size * 4

    block = PostNormTransformerBlock(
        hidden_size=hidden_size,
        num_heads=num_heads,
        ffn_size=ffn_size,
    )
    block.eval()

    with torch.no_grad():
        outputs = block(inputs)

    print("\n=== 实验 2：Transformer Block 数据流 ===")
    print(f"输入 X：                 {tuple(inputs.shape)}")
    print(f"Multi-Head Attention：   {tuple(outputs['attention_output'].shape)}")
    print(f"Attention 权重：         {tuple(outputs['attention_weights'].shape)}")
    print(f"第一次残差 X + MHA(X)：  {tuple(outputs['first_residual'].shape)}")
    print(f"第一次 LayerNorm：       {tuple(outputs['first_norm'].shape)}")
    print(f"FFN 扩维：               {tuple(outputs['ffn_hidden'].shape)}")
    print(f"GELU 激活：              {tuple(outputs['ffn_activated'].shape)}")
    print(f"FFN 降回 hidden_size：   {tuple(outputs['ffn_output'].shape)}")
    print(f"第二次残差：             {tuple(outputs['second_residual'].shape)}")
    print(f"第二次 LayerNorm/输出：  {tuple(outputs['block_output'].shape)}")

    # 两次残差相加都要求相加双方形状一致，Block 最终也保持输入形状。
    assert outputs["attention_output"].shape == inputs.shape
    assert outputs["ffn_output"].shape == inputs.shape
    assert outputs["block_output"].shape == inputs.shape

    print("\nTransformer Block 数据流图（Post-Norm）：")
    print(
        f"""
X                                      {tuple(inputs.shape)}
├─────────────── 残差支路 ───────────────────────────────┐
│                                                       │
└─→ Multi-Head Attention              {tuple(outputs['attention_output'].shape)}
                    ↓                                  │
              Add：X + MHA(X)           {tuple(outputs['first_residual'].shape)} ←┘
                    ↓
                LayerNorm               {tuple(outputs['first_norm'].shape)}
                    ├──────── 残差支路 ──────────────────┐
                    ↓                                  │
           Linear：hidden → 4×hidden    {tuple(outputs['ffn_hidden'].shape)}
                    ↓                                  │
                  GELU                  {tuple(outputs['ffn_activated'].shape)}
                    ↓                                  │
           Linear：4×hidden → hidden    {tuple(outputs['ffn_output'].shape)}
                    ↓                                  │
              Add：Norm + FFN           {tuple(outputs['second_residual'].shape)} ←┘
                    ↓
                LayerNorm               {tuple(outputs['block_output'].shape)}
                    ↓
             输出到下一个 Block          {tuple(outputs['block_output'].shape)}
"""
    )


def main() -> None:
    batch_size = 2
    seq_len = 4
    hidden_size = 8

    # 模拟已经经过 Embedding 和位置编码的输入。
    inputs = torch.randn(batch_size, seq_len, hidden_size)

    compare_head_counts(inputs, head_counts=[1, 2, 4, 8])
    print_block_shapes(inputs)

    print("\n结论：")
    print("1. 本实验固定 hidden_size，只改变可整除它的 num_heads。")
    print("2. 在此前提下，head_dim = hidden_size / num_heads，Head 数增加时 head_dim 才会减小。")
    print("3. 所有 Head 拼接后的维度仍是 num_heads × head_dim = hidden_size，整体输出形状不变。")
    print("4. 权重保留各 Head 时形状为 [batch, num_heads, query_len, key_len]。")
    print("5. 如果固定 head_dim 而增加 num_heads，hidden_size 和输出维度也会随之增加。")
    print("6. PyTorch MultiheadAttention 的投影参数量在 hidden_size 固定时通常不随 Head 数变化。")
    print("7. FFN 中间层通常扩维，但会投影回 hidden_size，以满足残差相加要求。")
    print("8. Residual Connection 和 LayerNorm 都不会改变张量形状。")


if __name__ == "__main__":
    main()
