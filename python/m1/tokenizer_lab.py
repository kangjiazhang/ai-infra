"""比较中文、英文和 Python 代码经过 Qwen Tokenizer 后的切分结果。"""

from typing import Any, cast

from transformers import AutoTokenizer, PreTrainedTokenizerBase


# Hugging Face 上的模型仓库名称。这里只加载 Tokenizer，不会加载模型权重。
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

# 使用三种不同类型的文本，观察自然语言和代码的 Token 切分差异。
SAMPLES = {
    "中文": "大语言模型通过预测下一个词元来生成文本。",
    "英文": "Large language models generate text by predicting the next token.",
    "Python代码": '''def greet(name: str) -> str:
    return f"Hello, {name}!"
''',
}


def encode_with_offsets(
    tokenizer: PreTrainedTokenizerBase,
    text: str,
) -> tuple[list[int], list[tuple[int, int]] | None]:
    """编码文本，并尽量返回每个 Token 在原文中的起止位置。"""
    try:
        encoded = tokenizer(
            text,
            # 不添加 BOS、EOS 等特殊 Token，避免影响三类文本的数量对比。
            add_special_tokens=False,
            # offset_mapping 中的每个 (start, end) 对应 Token 在原文中的位置。
            return_offsets_mapping=True,
        )
        print(f"encoded: {encoded}")
        # Hugging Face 的返回类型较宽泛，这里显式转换成程序声明的 int 类型。
        input_ids = [int(token_id) for token_id in encoded["input_ids"]]
        offsets = [
            (int(start), int(end))
            for start, end in encoded["offset_mapping"]
        ]
        return input_ids, offsets
    except (NotImplementedError, TypeError, KeyError):
        # 部分慢速 Tokenizer 不支持 offset_mapping，此时退化为普通编码。
        encoded = tokenizer(text, add_special_tokens=False)
        input_ids = [int(token_id) for token_id in encoded["input_ids"]]
        return input_ids, None


def analyze_text(
    tokenizer: PreTrainedTokenizerBase,
    label: str,
    text: str,
) -> dict[str, Any]:
    """打印单个样本的编码详情，并返回后续对比所需的统计数据。"""
    # input_ids 是模型真正接收的整数；internal_tokens 是便于人观察的内部表示。
    input_ids, offsets = encode_with_offsets(tokenizer, text)
    print(f"offsets: {offsets}")
    print(f"input_ids: {input_ids}")
    internal_tokens = tokenizer.convert_ids_to_tokens(input_ids)
    print(f"internal_tokens: {internal_tokens}")

    # 将完整 ID 序列一次性解码，用来检查编码和解码能否正确还原原文。
    decoded_text = tokenizer.decode(
        input_ids,
        skip_special_tokens=False,
        # 禁止自动清理空格，避免代码缩进或原始空格被修改。
        clean_up_tokenization_spaces=False,
    )

    print(f"\n{'=' * 72}")
    print(f"类型：{label}")
    # !r 使用 repr 形式显示字符串，让空格、换行符等不可见字符可被观察。
    print(f"原始文本：{text!r}")
    print(f"token ID：{input_ids}")
    print(f"token 数量：{len(input_ids)}")
    print("\n序号 | token ID | Tokenizer 内部表示 | 原文片段")
    print("-" * 72)

    # zip 将每个 token ID 与对应的内部 Token 字符串配对。
    for index, (token_id, internal_token) in enumerate(
        zip(input_ids, internal_tokens),
        start=1,
    ):
        if offsets is not None:
            # 使用字符偏移从原文截取片段，比单独 decode 一个 ID 更可靠。
            start, end = offsets[index - 1]
            text_piece = text[start:end]
        else:
            # 不支持偏移映射时，尝试单独解码当前 Token 作为备用方案。
            text_piece = tokenizer.decode(
                [token_id],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )

        print(
            f"{index:>4} | {token_id:>8} | "
            f"{internal_token!r:<22} | {text_piece!r}"
        )

    print(f"\n解码后的文本：{decoded_text!r}")
    print(f"是否与原文一致：{decoded_text == text}")

    token_count = len(input_ids)
    # 返回结构化统计数据，供最后的三类文本汇总表使用。
    return {
        "label": label,
        "character_count": len(text),
        "byte_count": len(text.encode("utf-8")),
        "token_count": token_count,
        "characters_per_token": len(text) / token_count if token_count else 0,
    }


def print_comparison(results: list[dict[str, Any]]) -> None:
    """将所有样本的字符数、字节数和 Token 数汇总成对比表。"""
    print(f"\n{'=' * 72}")
    print("Token 数量对比（本次样本文本长度不同，结果仅用于观察切分差异）")
    print("-" * 72)
    print(f"{'类型':<12} {'字符数':>8} {'UTF-8字节数':>14} {'Token数':>10} {'字符/Token':>14}")
    print("-" * 72)

    # 字符数、UTF-8 字节数和 Token 数是三个不同概念，不能互相替代。
    for result in results:
        print(
            f"{result['label']:<12} "
            f"{result['character_count']:>8} "
            f"{result['byte_count']:>14} "
            f"{result['token_count']:>10} "
            f"{result['characters_per_token']:>14.2f}"
        )

    print("\n观察重点：")
    print("1. Token 不等于字符，也不等于英文单词。")
    print("2. 空格、标点、换行和代码符号都可能单独或组合成为 Token。")
    print("3. Tokenizer 不同，同一段文本得到的 Token 数也可能不同。")
    print("4. 比较语言效率时，应使用语义和长度接近的样本，不能只看本表总数。")


def main() -> None:
    """加载 Tokenizer，依次分析样本并打印最终对比结果。"""
    print(f"正在加载 Tokenizer：{MODEL_NAME}")
    tokenizer = cast(
        PreTrainedTokenizerBase,
        AutoTokenizer.from_pretrained(
            MODEL_NAME,
            # Fast Tokenizer 由 Rust tokenizers 库实现，并支持 offset_mapping。
            use_fast=True,
        ),
    )

    # 对字典中的每个样本执行相同分析，并收集统计结果。
    results = [
        analyze_text(tokenizer, label, text)
        for label, text in SAMPLES.items()
    ]
    print_comparison(results)


# 只有直接运行当前文件时才执行 main；被其他模块导入时不会自动执行。
if __name__ == "__main__":
    main()
