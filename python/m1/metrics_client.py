"""对流式服务测量 TTFT、TPOT 和吞吐，并对比不同并发下的指标变化。

使用方式：
1. 先启动服务：cd python && uvicorn main:app --port 8000
2. 再运行本脚本：python3 m1/metrics_client.py --url http://127.0.0.1:8000/async-stream

实验把每个 chunk 当作一个 token。当前 main.py 每个 chunk 之间 sleep 1 秒，
因此 TPOT 基线约为 1000ms；当并发上升、服务端出现排队时，TPOT 和 TTFT 会升高。
"""

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Python 3.11+ 内置 httpx 之外的替代方案有限，这里统一使用 httpx 做异步 HTTP 客户端。
try:
    import httpx
except ImportError as error:  # pragma: no cover
    raise SystemExit(
        "缺少依赖 httpx，请先安装：python -m pip install httpx",
    ) from error


@dataclass
class RequestMetrics:
    """单个请求的全部测量结果，时间单位均为毫秒。"""

    request_id: int
    # 请求发出到收到第一个 chunk 的时间。
    ttft_ms: float
    # 相邻 chunk 到达时间的平均值（不含首 chunk）。
    tpot_ms: float
    # 相邻 chunk 到达时间的列表，可用于观察生成阶段的抖动。
    inter_token_gaps_ms: list[float] = field(default_factory=list)
    # 收到的 chunk 总数，实验中近似等于 token 数。
    chunk_count: int = 0
    # 从请求发出到最后一个 chunk 的总时间。
    total_ms: float = 0.0
    error: str | None = None

    @property
    def valid(self) -> bool:
        """请求是否成功完成，失败请求不参与延迟统计。"""
        return self.error is None


async def measure_one_request(
    client: httpx.AsyncClient,
    url: str,
    request_id: int,
) -> RequestMetrics:
    """发送一个流式请求，逐块记录到达时间。

    TTFT = 第一个 chunk 到达时间 - 请求开始时间
    TPOT = 后续相邻 chunk 到达间隔的平均值
    """
    # 使用 perf_counter 单调时钟做性能计时，不受系统时间调整影响。
    start = time.perf_counter()

    first_chunk_time: float | None = None
    last_chunk_time: float | None = None
    gaps: list[float] = []
    chunk_count = 0

    try:
        # stream=True 保证按到达顺序逐块读取，而不是等全部响应完成。
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                # 空 chunk（如心跳或结尾换行）忽略，避免干扰计时。
                if not chunk:
                    continue
                now = time.perf_counter()
                if first_chunk_time is None:
                    first_chunk_time = now
                else:
                    # 只统计相邻两个 chunk 之间的间隔。
                    gaps.append((now - last_chunk_time) * 1000)
                last_chunk_time = now
                chunk_count += 1
    except Exception as error:  # noqa: BLE001 - 实验脚本需要记录所有失败原因
        return RequestMetrics(
            request_id=request_id,
            ttft_ms=0.0,
            tpot_ms=0.0,
            total_ms=(time.perf_counter() - start) * 1000,
            error=repr(error),
        )

    total_ms = (time.perf_counter() - start) * 1000
    if first_chunk_time is None:
        # 请求成功但没有收到任何 chunk，视为异常样本。
        return RequestMetrics(
            request_id=request_id,
            ttft_ms=0.0,
            tpot_ms=0.0,
            total_ms=total_ms,
            error="no chunks received",
        )

    return RequestMetrics(
        request_id=request_id,
        ttft_ms=(first_chunk_time - start) * 1000,
        tpot_ms=statistics.mean(gaps) if gaps else 0.0,
        inter_token_gaps_ms=gaps,
        chunk_count=chunk_count,
        total_ms=total_ms,
    )


def percentile(values: list[float], ratio: float) -> float:
    """计算分位数：ratio=0.5 为中位数，0.95 为 p95。

    这里使用最简单的"最近邻"取值方式，满足实验精度即可；
    生产监控应使用与 SLO 定义一致的分位数算法。
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * ratio), len(ordered) - 1)
    return ordered[index]


def summarize(metrics: list[RequestMetrics]) -> dict[str, Any]:
    """把并发组内的多个请求汇总成延迟与吞吐指标。"""
    valid = [item for item in metrics if item.valid]
    if not valid:
        return {
            "requests_total": len(metrics),
            "requests_failed": len(metrics) - len(valid),
        }

    ttft_values = [item.ttft_ms for item in valid]
    tpot_values = [item.tpot_ms for item in valid]
    total_values = [item.total_ms for item in valid]
    wall_seconds = max(item.total_ms for item in valid) / 1000
    total_chunks = sum(item.chunk_count for item in valid)

    return {
        "requests_total": len(metrics),
        "requests_failed": len(metrics) - len(valid),
        "ttft_avg_ms": statistics.mean(ttft_values),
        "ttft_p50_ms": percentile(ttft_values, 0.50),
        "ttft_p95_ms": percentile(ttft_values, 0.95),
        "ttft_max_ms": max(ttft_values),
        "tpot_avg_ms": statistics.mean(tpot_values),
        "tpot_p50_ms": percentile(tpot_values, 0.50),
        "tpot_p95_ms": percentile(tpot_values, 0.95),
        "e2e_avg_ms": statistics.mean(total_values),
        "e2e_p95_ms": percentile(total_values, 0.95),
        "chunk_tokens_total": total_chunks,
        # 吞吐按整组实际耗时计算，而不是把单请求延迟相加。
        "request_throughput_rps": len(valid) / wall_seconds,
        "token_throughput_tps": total_chunks / wall_seconds,
    }


def print_group_summary(concurrency: int, summary: dict[str, Any]) -> None:
    """打印单个并发组的指标。"""
    print(f"\n=== 并发 {concurrency} ===")
    if "ttft_avg_ms" not in summary:
        print(f"全部请求失败：{summary}")
        return

    print(f"成功/失败请求：        {summary['requests_total'] - summary['requests_failed']}/{summary['requests_failed']}")
    print(f"TTFT  avg/p50/p95/max：{summary['ttft_avg_ms']:7.1f} / "
          f"{summary['ttft_p50_ms']:7.1f} / "
          f"{summary['ttft_p95_ms']:7.1f} / "
          f"{summary['ttft_max_ms']:7.1f} ms")
    print(f"TPOT  avg/p50/p95：    {summary['tpot_avg_ms']:7.1f} / "
          f"{summary['tpot_p50_ms']:7.1f} / "
          f"{summary['tpot_p95_ms']:7.1f} ms")
    print(f"端到端 avg/p95：       {summary['e2e_avg_ms']:7.1f} / "
          f"{summary['e2e_p95_ms']:7.1f} ms")
    print(f"chunk 总数：           {summary['chunk_tokens_total']}")
    print(f"请求吞吐：             {summary['request_throughput_rps']:.2f} req/s")
    print(f"token 吞吐：           {summary['token_throughput_tps']:.2f} chunks/s")


async def run_scenario(
    client: httpx.AsyncClient,
    url: str,
    concurrency: int,
) -> tuple[dict[str, Any], list[RequestMetrics]]:
    """以指定并发同时发起请求，并返回汇总与明细。"""
    print(f"\n>>> 同时发起 {concurrency} 个请求……")
    # gather 会并发执行所有协程，模拟客户端同时到达的负载。
    metrics = await asyncio.gather(
        *(measure_one_request(client, url, i) for i in range(concurrency)),
    )
    metrics = list(metrics)
    summary = summarize(metrics)
    print_group_summary(concurrency, summary)
    return summary, metrics


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="测量流式服务的 TTFT / TPOT / 吞吐，并对比并发影响",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/async-stream",
        help="流式接口地址",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[1, 5, 10],
        help="依次测试的并发数，默认 1 5 10",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "results",
        help="结果 JSON 保存目录",
    )
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    """依次运行各并发组并保存结果。"""
    print("=" * 62)
    print("LLM 服务指标实验")
    print(f"目标接口：{args.url}")
    print(f"并发组：  {args.concurrency}")
    print("=" * 62)

    # timeout=None 避免长流式响应被客户端超时中断。
    async with httpx.AsyncClient(timeout=None) as client:
        # 先做一次探测请求，确认服务可用，避免把连接错误误读成指标。
        probe = await measure_one_request(client, args.url, -1)
        if not probe.valid:
            raise SystemExit(f"服务不可用，请检查 {args.url} 是否已启动：{probe.error}")
        print("\n探测请求成功，服务可用。")

        all_results: dict[str, Any] = {
            "url": args.url,
            "timestamp": datetime.now().astimezone().isoformat(),
            "scenarios": [],
        }

        for concurrency in args.concurrency:
            if concurrency < 1:
                raise SystemExit("并发数必须大于等于 1")
            summary, metrics = await run_scenario(client, args.url, concurrency)
            all_results["scenarios"].append(
                {
                    "concurrency": concurrency,
                    "summary": summary,
                    "details": [
                        {
                            "request_id": item.request_id,
                            "ttft_ms": item.ttft_ms,
                            "tpot_ms": item.tpot_ms,
                            "total_ms": item.total_ms,
                            "chunk_count": item.chunk_count,
                            "error": item.error,
                        }
                        for item in metrics
                    ],
                },
            )

    # 保存结果，便于复盘和画图。
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = args.output_dir / f"metrics-client-{timestamp}.json"
    output_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== 观察要点 ===")
    print("1. 并发升高后 TTFT 是否明显上升（排队/调度变慢）。")
    print("2. TPOT 是否随并发上升（本服务是 asyncio 串行 sleep，理论上基本不变；")
    print("   真实推理引擎中 TPOT 上升意味着 Decode 批次变重）。")
    print("3. 请求吞吐和 chunk 吞吐是否随并发提高。")
    print("4. 平均值与 p95 的差距：只看平均会掩盖长尾请求。")
    print(f"\n结果已保存：{output_path}")


def main() -> None:
    """命令行入口。"""
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
