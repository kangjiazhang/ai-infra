"""使用一个小型 PyTorch Embedding 层观察 Token ID 到向量的查表过程。"""

import torch
from torch import Tensor, nn


# 固定随机种子，使每次运行时初始化出的 Embedding 权重相同，便于对照实验。
torch.manual_seed(42)

# 这是一个玩具词表，仅用于帮助理解 Token、Token ID 和 Embedding 的关系。
# 真实模型的词表可能包含十几万个 Token，Embedding 维度也可能达到几千。
TOY_VOCAB = {
    "<pad>": 0,
    "我": 1,
    "喜欢": 2,
    "学习": 3,
    "大模型": 4,
    "Python": 5,
}


def print_vectors(title: str, token_ids: Tensor, vectors: Tensor) -> None:
    """按位置打印 Token ID 及其对应的 Embedding 向量。"""
    print(f"\n{title}")
    print(f"Token ID：{token_ids.tolist()}")
    print(f"输入形状：{tuple(token_ids.shape)}")
    print(f"输出形状：{tuple(vectors.shape)}")

    for index, token_id in enumerate(token_ids.tolist()):
        print(f"位置 {index}：ID={token_id}，向量={vectors[index].tolist()}")


def main() -> None:
    # num_embeddings 是词表大小，即 Embedding 表的行数。
    # embedding_dim 是每个 Token 向量的维度，即 Embedding 表的列数。
    embedding = nn.Embedding(
        num_embeddings=len(TOY_VOCAB),
        embedding_dim=4,
    )

    print("玩具词表：", TOY_VOCAB)
    print("Embedding 权重形状：", tuple(embedding.weight.shape))
    print("每一行对应一个 Token ID，每一列是该 Token 向量的一个维度。")
    print("\n完整 Embedding 表：")
    print(embedding.weight.detach())

    # 第一组 Token ID 对应：我、喜欢、学习、大模型。
    original_ids = torch.tensor([1, 2, 3, 4], dtype=torch.long)
    original_vectors = embedding(original_ids)
    print("original_vectors：" ,original_vectors)
    print_vectors("实验 1：原始顺序", original_ids, original_vectors)

    # 只改变 ID 顺序，不修改 Embedding 表。
    # 输出向量也会按照新 ID 的顺序重新排列。
    reordered_ids = torch.tensor([4, 1, 3, 2], dtype=torch.long)
    reordered_vectors = embedding(reordered_ids)
    print_vectors("实验 2：修改 Token ID 顺序", reordered_ids, reordered_vectors)

    # 新顺序 [4, 1, 3, 2] 对应原顺序 [1, 2, 3, 4] 的索引 [3, 0, 2, 1]。
    expected_reordered_vectors = original_vectors[[3, 0, 2, 1]]
    print(
        "顺序改变后，向量是否只是跟随 Token ID 重新排列：",
        torch.allclose(reordered_vectors, expected_reordered_vectors),
    )

    # 同一个 Token ID 连续出现三次，相当于查 Embedding 表中的同一行三次。
    repeated_ids = torch.tensor([2, 2, 2], dtype=torch.long)
    repeated_vectors = embedding(repeated_ids)
    print_vectors("实验 3：重复输入相同 Token ID", repeated_ids, repeated_vectors)

    same_vector = torch.allclose(repeated_vectors[0], repeated_vectors[1]) and torch.allclose(
        repeated_vectors[1], repeated_vectors[2]
    )
    print("相同 Token ID 的初始 Embedding 向量是否相同：", same_vector)

    print("\n结论：")
    print("1. Embedding 的输入是 Token ID，不是 Token 字符串。")
    print("2. Embedding 的输出是浮点数向量，不是 internal_tokens。")
    print("3. 输入形状为 [seq_len] 时，输出形状为 [seq_len, embedding_dim]。")
    print("4. 修改 Token ID 的顺序，输出向量会按相同方式重新排列。")
    print("5. Embedding 权重不变时，相同 Token ID 查到的初始向量相同。")
    print("6. 初始向量经过 Attention 和 FFN 后，会变成与上下文相关的隐藏状态。")


if __name__ == "__main__":
    main()
