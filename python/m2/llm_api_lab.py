#!/usr/bin/env python3
"""M2 Day 0：LLM API 使用速成实验。

用自己部署的 vLLM 服务（OpenAI 兼容）完成 6 个任务：
  1. 基础调用 + temperature=0 复现性
  2. 温度手感（0.2 / 0.7 / 1.2 对比）
  3. max_tokens 截断（finish_reason=length）
  4. 流式 SSE：数 delta 条数 ≈ completion_tokens
  5. 多轮对话：prompt_tokens 随历史增长
  6. system prompt 有/无 对比

用法（先 port-forward 或用可达地址）：
  kubectl -n llm-lab-m2 port-forward deploy/vllm-7b-fp16-tp2 8000:8000 &
  python3 llm_api_lab.py --base-url http://127.0.0.1:8000 --model qwen2.5-7b

可选只跑部分任务：
  python3 llm_api_lab.py --tasks 1,2,3
"""
import argparse
import json
import urllib.request


def chat(base_url: str, model: str, messages: list, temperature: float = 0.7,
         max_tokens: int = 256, stream: bool = False, timeout: int = 120,
         stream_usage: bool = False):
    """发一次请求。stream=True 时返回 (delta条数, usage_or_None, 文本)。"""
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream and stream_usage:
        body["stream_options"] = {"include_usage": True}

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if not stream:
            return json.loads(resp.read())

        # SSE 流式：逐事件解析
        deltas, usage, text, buf = 0, None, [], b""
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
                        continue
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):            # stream_options 返回的最终 usage
                        usage = obj["usage"]
                    # 注意：usage-only chunk 的 choices 是空数组 []，必须先判空
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if delta.get("content"):
                        deltas += 1
                        text.append(delta["content"])
        return deltas, usage, "".join(text)


def hr(title: str):
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def task1_basic(base_url, model):
    hr("任务 1：基础调用 + temperature=0 复现性")
    msgs = [
        {"role": "system", "content": "你是一个简洁的技术助手，回答不超过三句话。"},
        {"role": "user", "content": "什么是 KV Cache？"},
    ]
    out1 = chat(base_url, model, msgs, temperature=0, max_tokens=128)
    out2 = chat(base_url, model, msgs, temperature=0, max_tokens=128)
    t1, t2 = out1["choices"][0]["message"]["content"], out2["choices"][0]["message"]["content"]
    print(f"第 1 次输出:\n  {t1}\n")
    print(f"第 2 次输出:\n  {t2}\n")
    print(f"两次输出完全一致: {'✅ 是' if t1 == t2 else '❌ 否（思考：为什么？提示：批内数值顺序、引擎版本、浮点非结合性）'}")
    print(f"finish_reason: {out1['choices'][0]['finish_reason']}  usage: {out1['usage']}")


def task2_temperature(base_url, model):
    hr("任务 2：温度手感（同一问题 × 3 种温度 × 各 3 次）")
    prompt = [{"role": "user", "content": "给'大模型推理引擎性能优化'这个主题起三个技术博客标题。"}]
    for temp in (0.2, 0.7, 1.2):
        print(f"\n--- temperature = {temp} ---")
        for i in range(3):
            r = chat(base_url, model, prompt, temperature=temp, max_tokens=128)
            text = r["choices"][0]["message"]["content"].replace("\n", " / ")
            print(f"  第{i + 1}次: {text[:90]}")


def task3_truncation(base_url, model):
    hr("任务 3：max_tokens=16 截断")
    msgs = [{"role": "user", "content": "详细解释 Transformer 的 Attention 机制，至少 500 字。"}]
    r = chat(base_url, model, msgs, temperature=0.7, max_tokens=16)
    c = r["choices"][0]
    print(f"finish_reason: {c['finish_reason']}   ← 是不是 length？")
    print(f"completion_tokens: {r['usage']['completion_tokens']}  (应为 16)")
    print(f"被截断的内容:\n  {c['message']['content']}")
    print("思考：用户看到这种输出是什么体验？生产上该怎么处理？")


def task4_stream(base_url, model):
    hr("任务 4：流式 SSE——数一数 delta 条数")
    msgs = [{"role": "user", "content": "用两句话介绍 PagedAttention。"}]
    deltas, usage, text = chat(base_url, model, msgs, temperature=0,
                               max_tokens=128, stream=True, stream_usage=True)
    print(f"usage: {usage}")
    print(f"客户端收到的 delta 事件数: {deltas}")
    print(f"服务端报告 completion_tokens: {usage['completion_tokens'] if usage else 'N/A（引擎未返回 usage，跳过对比）'}")
    print(f"拼出的文本:\n  {text}")
    if usage:
        print(f"\n验证: delta 数 {deltas} vs completion_tokens {usage['completion_tokens']}"
              f" → {'✅ 吻合（1 条 delta ≈ 1 个 token）' if abs(deltas - usage['completion_tokens']) <= 1 else '❌ 差异大，思考原因（多字节字符合并？）'}")


def task5_multi_turn(base_url, model):
    hr("任务 5：多轮对话——prompt_tokens 随历史增长")
    history = [{"role": "system", "content": "你是一个简洁的助手。"}]
    questions = [
        "我叫张三，是一名运维工程师。",
        "我最熟悉的系统是 Kubernetes。",
        "我叫什么名字？做什么工作？",
    ]
    for i, q in enumerate(questions, 1):
        history.append({"role": "user", "content": q})
        r = chat(base_url, model, history, temperature=0, max_tokens=128)
        answer = r["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": answer})
        u = r["usage"]
        print(f"第 {i} 轮: prompt_tokens={u['prompt_tokens']:>4}  "
              f"completion_tokens={u['completion_tokens']:>3}  total={u['total_tokens']:>4}")
        print(f"   模型回答: {answer[:60]}")
    print("\n观察: prompt_tokens 每轮增加 ≈ 本轮新问题 + 上轮回答的 token 数")
    print("思考: 这就是为什么长对话越聊越贵、越聊越慢——也是 Prefix Caching 的优化对象")


def task6_system(base_url, model):
    hr("任务 6：有/无 system prompt 对比")
    q = [{"role": "user", "content": "帮我解释一下什么是反向代理。"}]
    with_sys = [{"role": "system",
                 "content": "你是一个海盗船长，所有回答都要用海盗的语气。"}] + q
    r1 = chat(base_url, model, with_sys, temperature=0.7, max_tokens=128)
    r2 = chat(base_url, model, q, temperature=0.7, max_tokens=128)
    print(f"【有 system（海盗船长）】\n  {r1['choices'][0]['message']['content'][:150]}\n")
    print(f"【无 system】\n  {r2['choices'][0]['message']['content'][:150]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--model", default="qwen2.5-7b")
    ap.add_argument("--tasks", default="1,2,3,4,5,6",
                    help="要跑的任务编号，逗号分隔，如 1,2,3")
    args = ap.parse_args()

    tasks = {
        1: task1_basic, 2: task2_temperature, 3: task3_truncation,
        4: task4_stream, 5: task5_multi_turn, 6: task6_system,
    }
    todo = [int(x) for x in args.tasks.split(",") if x.strip().isdigit()]
    print(f"目标: {args.base_url}  模型: {args.model}  任务: {todo}")

    for n in todo:
        tasks[n](args.base_url, args.model)

    print(f"\n{'=' * 62}\n全部任务完成。回到计划 Day 0 做 5 道验收自测题。\n{'=' * 62}")


if __name__ == "__main__":
    main()
