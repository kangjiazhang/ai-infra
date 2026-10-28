# vLLM 架构笔记（Day 2）

> 基于本机实测：vLLM v0.28.0，日志 PID 来自 7B FP16 TP=2 部署
> 所有指标行为均可通过 /metrics 和 bench JSON 在本机复现

---

## 一、架构图（真实进程映射）

```text
                    HTTP (OpenAI 兼容)
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ APIServer  (pid=1)                                      │
│  · FastAPI/uvicorn：路由、鉴权、参数校验                  │
│  · Tokenizer / Detokenizer（CPU 侧）                    │
│  · SSE 流式打包                                          │
│  无 GPU 计算。/health 只探活这一层                        │
└───────────────┬─────────────────────────────────────────┘
                │ ZMQ（进程间消息队列）
                ▼
┌─────────────────────────────────────────────────────────┐
│ EngineCore  (pid=237)                                   │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Scheduler                                         │  │
│  │  每个调度步决定：本轮跑哪些请求、分配多少 Token     │  │
│  │  Prefill 与 Decode 的混排在这里裁决                │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │ 分配/释放 Block 的指令                 │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │ KV Cache Manager / Block Pool                     │  │
│  │  PagedAttention：逻辑 Block ↔ 物理 Block 映射      │  │
│  │  Prefix Caching 的共享与引用计数也在这里            │  │
│  └───────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────┬───────────────────┘
       │ NCCL / 共享内存               │
       ▼                              ▼
┌────────────────┐          ┌────────────────┐
│ Worker_TP0     │          │ Worker_TP1     │
│ (pid=344)      │          │ (pid=345)      │
│ · Model Runner │◄─All-Red─►· Model Runner │
│ · 组装 GPU 输入│  (PHB PCIe│ · 组装 GPU 输入│
│ · 调 Attention │   每层!) │ · 调 Attention │
│   Backend      │          │   Backend      │
│   TRITON_ATTN  │          │   TRITON_ATTN  │
│ · Sampler      │          │                │
│   (TP0 兼)     │          │                │
└───────┬────────┘          └───────┬────────┘
        └────────────┬──────────────┘
                     ▼
                token → EngineCore → APIServer → SSE
```

为什么拆进程：API 层（网络 IO）与引擎核心（GPU 驱动循环）解耦——慢请求不阻塞 GPU 循环，GIL 互不干扰。

---

## 二、指标 → 组件映射

| 指标（/metrics） | 记录位置 | 对应阶段 | 实测参考 |
|---|---|---|---|
| `vllm:num_requests_waiting` | Scheduler 的等待队列 | 请求已进队未获调度 | 压测时 >0 说明容量不足 |
| `vllm:num_requests_running` | Scheduler 的活跃 Batch | 正在 Prefill/Decode | 闭环并发 8 → 应稳定在 8 |
| `vllm:time_to_first_token_seconds` | 请求完成首 Token 时打点 | 排队+Tokenize+Prefill | EXP-002: p50 1.7s |
| `vllm:time_per_output_token_seconds` | Decode 每轮 | Decode 单步耗时 | EXP-002: p50 62ms |
| ITL（客户端测） | 客户端相邻事件间隔 | 反映调度干扰 | EXP-002: p50 41ms / p99 572ms |
| `vllm:gpu_cache_usage_perc` | KV Cache Manager | 已分配 Block 占比 | 满载时观察是否逼近 1.0 |
| `vllm:prompt_tokens_total` | Sampler 之后累计 | Prefill 处理量 | EXP-002: 315,899 |
| `vllm:generation_tokens_total` | Sampler 之后累计 | Decode 产出量 | EXP-002: 38,400 |

关键区分：TTFT 包含排队（Scheduler 层的事），TPOT 反映 Decode（Worker 层的事）——**同一批请求里 TTFT 差 + TPOT 好 = 瓶颈在排队**。

---

## 三、一个请求的生命周期（日志/指标可追踪）

```text
① curl 发出 → APIServer 接收、解析、Tokenize        [客户端发出时刻]
② 进 Scheduler 等待队列                              [num_requests_waiting +1]
③ 某调度步被选中，KV Manager 分配 Block
④ Worker 执行 Prefill（1024 token 一次/分块算完）     [TTFT 计时终点]
⑤ 后续每步 Decode，每 token 追加 Block                [TPOT 逐轮累计]
⑥ finish_reason 触发 → 释放 Block 回 Block Pool
   [num_requests_running -1, generation_tokens_total += 128]
⑦ Detokenizer + SSE 发完 → 客户端收到 [DONE]          [E2EL 终点]
```

E2EL = ②~⑦ 的总时长 ≈ TTFT + 127×TPOT（EXP-002 实测闭环 ✅）

---

## 四、源码索引（v0.28.0，只记职责不逐行）

| 组件 | 源码位置 | 核心类/方法 | 职责一句话 |
|---|---|---|---|
| 调度器 | `vllm/v1/core/sched/scheduler.py` | `Scheduler.schedule()` | 每步选出 Prefill/Decode 集合与 Token 预算 |
| 缓存协调 | `vllm/v1/core/kv_cache_coordinator.py` | `KVCacheCoordinator` | 统一管理分配/释放/前缀共享 |
| Block 池 | `vllm/v1/core/block_pool.py` | `BlockPool` | 物理块的分配、引用计数、free list |
| 单类型管理 | `vllm/v1/core/single_type_kv_cache_manager.py` | `SingleTypeKVCacheManager` | 某一种 KV 布局的分配策略 |
| 执行器 | `vllm/v1/worker/gpu_model_runner.py` | `GPUModelRunner.execute_model()` | 组装输入、跑 forward、选 attention backend |
| 引擎壳 | `vllm/v1/engine/llm_engine.py` | `LLMEngine` | EngineCore 进程的循环主体 |
| API 层 | `vllm/entrypoints/openai/` | `api_server.py` | FastAPI 路由、SSE |

读法：先 `Scheduler.schedule()` 看懂"这轮跑谁"，再看 `BlockPool` 的引用计数如何支撑 Prefix Caching 共享。

---

## 五、必须掌握（对照本机）

- **组件职责**：APIServer=门面（无 GPU）；Engine=决策；Scheduler=裁决每轮；KV Manager=显存账本；Worker=干活的
- **等待 ≠ 处理**：waiting 里的请求不占 GPU；EXP-002 里 `num_requests_waiting>0` 的时刻才是排队证据
- **问题可能在任一层**：分层排查路径——客户端 TTFT → 服务端指标 → 队列 → KV 水位 → GPU。E2EL 慢但 TPOT 正常 → 排队；TPOT 也慢 → GPU/带宽/通信
- **参数映射组件**：`max-num-seqs`→Scheduler 的序列上限；`max-num-batched-tokens`→Scheduler 的每步 Token 预算；`gpu-memory-utilization`→KV Manager 可管的空间；TP→Worker 数量。**记住"参数作用在哪个组件"，比背命令行值钱**

---

## 六、当天验收答案

### 1. 请求从 HTTP 到首 Token 经历哪些组件？

> APIServer（解析+Tokenize）→ 经 ZMQ 进 EngineCore → Scheduler 排队并选中 → KV Cache Manager 分配 Block → Worker 执行 Prefill → Sampler 产出首 token → 原路返回。TTFT 计的是这条链的总和。

### 2. Scheduler 为什么同时管理 Prefill 和 Decode？

> 两类任务共享同一块 GPU 和 Token 预算，且互相干扰（实测：EXP-002 的 ITL p99=572ms 尖峰就是新请求 Prefill 插队打断了别人的 Decode）。只有一个统一的裁决者才能做 Chunked Prefill 的混排权衡：每步给 Prefill 多少、给 Decode 留多少。

### 3. KV Cache Block 何时分配、何时释放？

> 分配：请求被 Scheduler 选中时，按 Prefill 需要预分配；Decode 每生成 token 按需追加（写满当前 Block 再申请新的）。释放：`finish_reason` 触发（stop/length）后整请求归还；但被 Prefix Caching 命中的共享 Block 不立即释放——引用计数归零才真正回收。

### 4. 为什么 API 正常不代表 GPU 执行正常？

> `/health` 只探 APIServer 进程，GPU 卡死/驱动异常/EngineCore 挂掉时它照样 200。真正判断要看 `/metrics` 的请求是否在推进（generation_tokens_total 是否增长）或打一次真实推理。本机验证方式：`curl /health` + 观察指标，两者结合才等于"健康"。

---

# 七、Day 3：PagedAttention 补充

## Block 映射图（Day 3 产出物）

以一个生成了 130 tokens 的请求为例（block-size=16）：

```text
请求的逻辑 KV 序列（130 个 token 的 K/V）
┌──────┬──────┬──────┬──────┬────┐
│ L0   │ L1   │ L2   │ ...  │ L8 │      ← 逻辑 Block（每块 16 token）
└──┬───┴──┬───┴──┬───┴──────┴─┬──┘
   │映射  │      │            │      ← Block Table
   ▼      ▼      ▼            ▼
┌──────┬──────┬──────┬──────┬────────┐
│P#41  │P#7   │P#203 │ ...  │P#88    │      ← GPU 物理显存块（不连续！）
└──────┴──────┴──────┴──────┴────────┘
  共享:  L0 的 P#41 同时被另一个请求引用（Prefix Caching）
        → 引用计数 = 2，两边都结束才真正释放
  尾部:  L8 只装了 130-128=2 个有效 token，浪费 14 个位置（内部碎片）
```

关键点：物理块**不连续**，Attention kernel 通过 Block Table 间接寻址；逻辑序列的连续性由映射保证。

## 验收答案

### 1. PagedAttention 解决了什么问题？

> 传统实现按"最大长度预留 + 连续显存"分配 KV Cache，造成两类浪费：**内部碎片**（为短请求预留 max_len 空间）和**外部碎片**（连续空间难找、请求结束时留下洞）。论文数据：现有系统因此浪费 60-80% 显存。PagedAttention 借鉴 OS 分页，把 KV 切成固定 Block 按需分配，浪费降到接近零，还附带解锁了跨请求**共享**（Prefix Caching 的基础）。

### 2. 为什么能提高可承载并发？

> 因为同样的物理显存能装下更多**真实数据**。分页消除了预留和碎片后，`可用显存 ÷ 单 token KV` 的商就是诚实的并发容量。本机证据：7B TP=2 下 KV cache 149,024 tokens = 36.38x @ 4096——若按传统"每请求预留 4096"的分配方式，同样的 8 GiB KV 空间要打对折以上。次要因素：请求按需增长，短请求不占长请求的空间。

### 3. 它是否让 KV Cache 公式失效？

> **不失效**。公式 `2 × layers × kv_heads × head_dim × seq_len × batch × dtype_bytes` 算的是**逻辑有效数据量**——每个 token 的 K/V 该多大还是多大。分页改变的是**存储管理方式**（怎么装），不是数据本身（装什么）。

本机实证闭环（EXP-002）：

```text
149,024 tokens × 56 KiB/token（Qwen2.5-7B）≈ 8 GiB
= 每卡预算 12.75 GiB − 权重 6.7 GiB − 预留 ≈ 4 GiB × 2 卡 ✅
```

分页只引入极小的额外开销：Block Table 元数据 + 尾部 Block 的内部碎片（上图 L8 浪费 14/16）。公式继续用，只是别忘了工程上还有这 ~2-5% 的管理开销。

### 4. Block 越小是否一定越好？

> **不是，是个权衡**：

| Block 大小 | 收益 | 代价 |
|---|---|---|
| 小（如 8） | 尾部浪费少；Prefix Cache 共享粒度细（命中边界更贴合实际前缀） | Block Table 膨胀；元数据和查找开销增加；kernel 寻址局部性变差 |
| 大（如 512） | 元数据少；寻址简单 | 退化回"预留浪费"问题；短请求/短前缀共享不了 |

vLLM 默认 `block-size=16` 是折中值。原则：**极端都不可取**——block=1 元数据爆炸等于每 token 一条记录；block=1024 等于没分页。调优时只在尾部浪费（大量短请求）或共享粒度（前缀长度集中在非 16 倍数附近）成为瓶颈时才动它。

