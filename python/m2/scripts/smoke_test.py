#!/usr/bin/env python3
"""冒烟测试：验证 vLLM 服务链路并输出基本延迟数据。

只用 Python 标准库，服务器无需安装依赖。
用法：
  python3 smoke_test.py --base-url http://127.0.0.1:8000 \
      --model qwen2.5-1.5b --rounds 3
"""
import argparse
import json
import time
import urllib.request


def post(base_url: str, model: str, prompt: str, max_tokens: int,
         stream: bool, timeout: int = 120):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    first_token = None
    prev = None
    itls = []
    chunks = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if not stream:
            data = json.loads(resp.read())
            total = time.perf_counter() - start
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {"total_s": total, "text": text, "usage": usage}

        # SSE 流式解析
        buf = b""
        while True:
            piece = resp.read(1)
            if not piece:
                break
            buf += piece
            while b"\n\n" in buf:
                event, buf = buf.split(b"\n\n", 1)
                for line in event.decode().splitlines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload == "[DONE]":
                        break
                    now = time.perf_counter()
                    if first_token is None:
                        first_token = now
                    elif prev is not None:
                        itls.append(now - prev)
                    prev = now
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta", {})
                        if delta.get("content"):
                            chunks.append(delta["content"])
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

    total = time.perf_counter() - start
    ttft = first_token - start if first_token else None
    tpot = (sum(itls) / len(itls)) if itls else None
    return {
        "total_s": total,
        "ttft_s": ttft,
        "tpot_s": tpot,
        "output_chars": sum(len(c) for c in chunks),
        "text": "".join(chunks),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--model", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=64)
    args = ap.parse_args()

    prompt = "用三句话解释 KV Cache 是什么。"

    print(f"模型: {args.model}  轮数: {args.rounds}\n")

    # 非流式
    r = post(args.base_url, args.model, prompt, args.max_tokens, stream=False)
    print(f"[非流式] 总耗时 {r['total_s']:.3f}s  输出 {r['output_chars'] if 'output_chars' in r else len(r['text'])} 字")
    print(f"  输出预览: {r['text'][:80]}...")
    print(f"  usage: {r.get('usage')}\n")

    # 流式（多轮，第 1 轮视为预热，正式数据看后续轮）
    for i in range(1, args.rounds + 1):
        r = post(args.base_url, args.model, prompt, args.max_tokens, stream=True)
        ttft = f"{r['ttft_s']*1000:8.1f} ms" if r["ttft_s"] else "     n/a"
        tpot = f"{r['tpot_s']*1000:8.1f} ms" if r["tpot_s"] else "     n/a"
        tag = "预热" if i == 1 else f"轮{i}"
        print(f"[流式 {tag}] TTFT {ttft}  TPOT {tpot}  总 {r['total_s']:.3f}s")

    print("\n注意：首次请求含 CUDA Graph/Kernel 预热开销，不能作为正式基线。")


if __name__ == "__main__":
    main()
