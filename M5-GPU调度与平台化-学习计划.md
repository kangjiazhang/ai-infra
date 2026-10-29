# M5 · GPU 调度与平台化学习计划

> 学习周期：2 周（每周 6 天，共 12 天）
> 建议投入：工作日每天约 2 小时，周六 3～4 小时
> 学习目标：从"一个服务独占一张卡"进阶到"多个服务/多个租户共享一个 GPU 池"——掌握 GPU 共享的三条路线与隔离边界、队列与配额、批调度、推理感知路由，并能画出一张完整的推理平台架构。
> 核心产出：《一卡多服务隔离性验证报告》、一张《AI 推理平台架构图》、一个最小"负载/前缀感知路由器"及其对照实验数据。
> 大纲定位：**平台工程能力，部分可迁移**。K8s 调度概念（队列、优先级、抢占）你已熟，重点补 GPU 特有的部分：显存/算力的软隔离、碎片、推理流量的状态感知。

---

## 一、M4 到 M5 的能力衔接

进入 M5 前，应能不看资料解释（M2/M3/M4 已建立）：

- `nvidia.com/gpu` 默认是整数独占资源，为什么不能超卖（M3 Day 4）
- 本机 GPU 由 **HAMi** 管理：节点上报 `nvidia.com/gpu: 20`（2 卡 × 10 vGPU），Pod 必须走 `schedulerName: hami-scheduler`，资源用 `gpucores` / `gpumem` 扩展资源（M2 实验手册）
- 单 vGPU 给满（gpumem 15000、gpucores 100）≈ 独占整卡；HAMi 劫持 NVML，容器内 vLLM 看到的是虚拟显存
- 网关层解决什么：路由、限流、记账、fallback（M4 Day 9）；LiteLLM 目前做的是"按模型名路由"，不感知后端负载
- 7B AWQ 在 T4 单卡可跑；1.5B FP16 权重约 3 GB、冷启动约 40s（M2/M4 实测）
- 容量即配置：`gpu-memory-utilization`、`max-model-len`、`max-num-seqs` 决定一个实例吃多少显存（M1/M2）

M5 要建立的工程闭环：

```text
共享（一张卡切给多个服务）
  ↓ 隔离性是否可信？（显存 / 算力 / 故障域）
队列与配额（谁能用多少、排队、抢占）
  ↓ 多卡任务要不要 Gang？碎片怎么控制？
路由（请求该去哪个实例：负载 / 前缀缓存感知）
  ↓
平台（租户 → 队列 → 池 → 网关 → 监控的完整架构）
```

M5 的最终目标是：

> 面对"一张 80G 卡跑 7B 太浪费""一张 A100 上跑三个业务怎么隔离""多个团队抢 GPU 怎么分""为什么轮询路由让 TTFT 抖动"这类问题，能给出有实验依据的方案，而不是只说名词。

---

## 二、固定学习方法

每天按以下节奏进行：

1. **30 分钟原理**：读 HAMi / Kueue / Volcano / Gateway API 官方文档
2. **70 分钟实验**：在本机双 T4 + k3s 上验证，或明确标注"文档结论"
3. **20 分钟复述**：用"机制 → 现象 → 取舍"讲清当天内容

### 实验纪律（延续 M2/M3/M4）

- 本机结论必须有命令输出/压测数据作证据，归档到 `python/m5/results/`
- **文档结论与本机验证结论分开标注**，不混写
- 所有 `kubectl label/taint/apply` 动节点前先记录当前状态；实验后恢复
- **不修改、不重启** `llm-lab-hami` 命名空间的 HAMi 组件本身（M2 铁律沿用）；调度策略类实验通过 Pod 注解/资源声明完成
- 破坏性实验（故意 OOM、杀进程）放在专用命名空间 `llm-lab-m5`，且先把 M4 的 `vllm-qa` / `vllm-smoke` / 网关缩容，避免与邻居互相污染
- 对照实验沿用 M2 纪律：固定模型/版本/负载，每组至少 3 次，取中位数，一次只改一个变量
- 版本敏感项（HAMi 注解名、Kueue/Volcano/GAIE 的 CRD 字段）**一律以本机安装版本的官方文档为准**，本文给出的字段名是定位线索而非保证

### 建议目录

```text
python/m5/
├── hami/
│   ├── share-1.5b-x2.yaml          # 一卡两服务
│   ├── isolation/                  # 显存/算力/故障域验证用例
│   └── frag-binpack-spread.yaml    # 碎片实验
├── queueing/
│   ├── kueue/                      # ResourceFlavor / ClusterQueue / LocalQueue
│   └── volcano/                    # PodGroup / Queue 示例
├── router/
│   ├── epp_lite.py                 # 最小负载+前缀感知路由器（FastAPI）
│   ├── load_gen.py                 # 带共享前缀的负载生成器
│   └── results/
├── results/                        # 原始数据（只追加）
├── notes/
│   ├── hami-internals.md
│   ├── sharing-comparison.md       # HAMi / MPS / MIG / time-slicing 对比
│   ├── gateway-api-inference.md
│   ├── llm-d-aibrix.md
│   └── training-side-brief.md
└── report/
    ├── 一卡多服务隔离性验证报告.md
    └── AI推理平台架构图.md          # mermaid / drawio 导出
```

同样建在本地 mac 的 study 仓库（与 `python/m4/` 并列），服务器上维护运行副本，同步回路与 M4 相同。

---

## 三、实验环境与边界

### 复用现有资产

| 资产 | 来源 | M5 用法 |
|---|---|---|
| 双 T4 + k3s 单节点 | M2 起 | 全部实验的底座 |
| HAMi（`llm-lab-hami`） | 既有 | Week 1 的主角：一卡多服务、隔离性、碎片 |
| `vllm-inference` chart | M4 | 增加 HAMi 参数（schedulerName / gpumem / gpucores）后复用 |
| LiteLLM 网关 + Postgres | M4 Day 9 | 作为路由对照基线；租户 key 复用 |
| KEDA / Prometheus（`llm-lab-infer`、keda） | 既有 / M4 Day 0 | 路由器读取 vLLM `/metrics`；M6 继续复用 |
| M2 压测客户端与题集 | M2 | 隔离性验证的背景/邻居流量 |
| 节点标签 `nvidia.com/gpu.product=Tesla-T4` | M4 Day 9 手动补 | 调度 selector 继续使用 |

### 双 T4 的实验边界

- **能实操**：HAMi 显存/算力切分、隔离性验证、Binpack/Spread、Kueue 队列配额、负载/前缀感知路由
- **只做文档分析**：MIG（T4 不支持）、NVLink 拓扑亲和（本机是 PHB、无 NVLink）、DRA 实际切分、llm-d/AIBrix 的完整部署（需多节点与 RDMA/PD 分离硬件）
- **有条件实操**：MPS（需宿主机层面操作，会影响正在被 HAMi 使用的卡，只在维护窗口、其他负载全停时做，见 Day 4）
- **关键兼容性约束（务必先理解再动手）**：HAMi 要求 Pod 走 `hami-scheduler`，**Volcano 是另一个调度器，同一个 Pod 不能同时由两者调度**。因此：
  - Kueue 只做准入/配额，不接管调度 → **与 HAMi 兼容，可用真 GPU 做实验**
  - Volcano 的 Gang 实验在本机用 **CPU / 自定义扩展资源** 模拟，不与 HAMi 争抢真 GPU；这条限制本身就是"平台选型时调度器不能随便叠加"的教学点

### 前置检查（Day 0，半天）

1. 确认 GPU 分配现状：`kubectl -n llm-qa get pod -o yaml | grep -E 'schedulerName|runtimeClassName|gpumem|gpucores'`。M4 chart 目前 `values.yaml` 没有 HAMi 字段，要确认 `vllm-qa` 是怎么拿到 GPU 的（走 HAMi？走默认 device plugin？），结论写进 `notes/hami-internals.md`
2. `kubectl -n llm-lab-hami get pods`，记录 HAMi 版本、device-plugin / scheduler 的镜像 tag；`kubectl describe node` 记录 `nvidia.com/gpu` capacity 及 `gpumem` / `gpucores` 是否出现在 allocatable
3. 记录现状快照：各命名空间 GPU 占用、两张卡的 `nvidia-smi` 显存水位、节点标签与污点
4. 预留 `llm-lab-m5` 命名空间，写清楚"实验期间谁被缩容、实验后如何恢复"的清单
5. 确认 Prometheus 能抓到 vLLM `/metrics`（M4 Day 7 的 ServiceMonitor 若未做，Day 7 前补上）

---

# 第一周：GPU 共享、隔离与队列

## Day 1：为什么要共享——HAMi 机制拆解

### 学习内容

**问题的量化**：M1 的显存公式在这里换个角度用——7B AWQ 权重约 5 GB，T4 16 GB 上跑 `max-model-len 4096 / max-num-seqs 8` 时 KV Cache 也只占几 GB；而 80 GB 卡上同样的服务，**常驻浪费 > 90%**。共享的核心动机：用显存预算的"切分"换取单卡密度，从而降低单位 token 成本（M6 的降本手段之一）。

**HAMi 的组成**（对照本机 `llm-lab-hami` 的 Pod 逆向，先读文档再验证）：

```text
MutatingWebhook      ：给请求了 vGPU 资源的 Pod 改写 schedulerName 等
hami-scheduler       ：scheduler extender，负责"挑哪张卡、切多少"，并把决策写进 Pod 注解
device-plugin        ：向 kubelet 注册 vGPU 资源，把决策翻译成容器环境/挂载
libvgpu.so（容器内） ：劫持 CUDA/NVML 调用，实现显存上限与算力时间片限制
```

关键机制：

- **显存隔离是软限制**：库拦截 `cudaMalloc` 等分配，超过 `gpumem` 就返回 OOM；容器内 `nvidia-smi` 看到的是虚拟显存
- **算力隔离是时间片限制**：`gpucores` 以百分比约束 kernel 提交占比，不是硬件分区；多服务争抢时存在抖动
- **所有隔离发生在用户态库层**：绕过该库（静态链接、直接 driver API）理论上可绕开，所以它是"协作式信任"隔离——这是与 MIG 的本质区别

### 动手任务

1. 读 `llm-lab-hami` 内各 Pod 的作用，画一张"Pod 创建 → webhook → hami-scheduler 选卡 → device-plugin 注入 → 容器内 libvgpu 生效"时序图
2. `kubectl describe pod`（任一 HAMi Pod）找到 HAMi 写入的注解（如 `hami.io/...` 的绑定/分配信息），解读它记录了什么
3. 进入一个 HAMi 容器，比较 `nvidia-smi`（虚拟显存）与宿主机 `nvidia-smi`（物理显存）；记录差异
4. 估算：本机一张 T4 理论上可同时放几个"1.5B 实例"/"7B AWQ 实例"（按实测权重+KV 预算算，不是拍脑袋）
5. 产出 `notes/hami-internals.md`

### 当天验收

- [ ] 能默画 HAMi 的组件分工与 Pod 创建链路
- [ ] 能解释"为什么不带 `hami-scheduler` 会 `no binding pod found`"（M2 实测的 165 个失败 Pod）
- [ ] 能说清显存隔离与算力隔离各自"硬/软"在哪里

### 验收参考答案

> 不带 `hami-scheduler`：Pod 由默认调度器分配节点，但 HAMi 的"选哪张卡、分多少"决策是 hami-scheduler 写进 Pod 注解的；device-plugin 在 `Allocate` 时按注解找"绑定记录"，找不到就报 `no binding pod found`，kubelet 准入失败，Deployment 控制器又不断重建 → 重建风暴。**教训：调度决策和设备分配是两段式协议，缺一段就整体失败。**
> 软硬之分：显存是"分配拦截"（超限即失败，行为确定，可靠度高）；算力是"时间片配额"（隔离度取决于调度粒度，会抖）。因此生产里**显存隔离可作为准入依据，算力隔离只能当软 QoS**。

---

## Day 2：HAMi 一卡多服务实战

### 学习内容

把 M4 的 chart 接上 HAMi，并想清楚 vLLM 与虚拟显存的**两层预算**：

```text
HAMi 层：gpumem = 7000 MiB            → 这个容器最多能 malloc 这么多
vLLM 层：gpu-memory-utilization = 0.8 → vLLM 以"看到的总显存"为基数预留

实际预留 = 虚拟总显存 × util。必须保证：权重 + 激活 + KV 预留 + CUDA context ≤ gpumem
```

注意点：

- vLLM 启动时做 profiling，**看到的是虚拟显存**，所以 util 的基数变了，不能沿用独占整卡的数值
- 同卡多服务时，每个进程还有各自的 CUDA context（几百 MB），预算要留余量
- M2 的 `gpu_memory_utilization` 结论（首轮 0.85）是独占口径，共享口径需重新标定

### 动手任务

1. 改 `vllm-inference` chart：增加 `gpu.share` 配置块，渲染出 `schedulerName: hami-scheduler`、`runtimeClassName: nvidia`、`nvidia.com/gpucores`、`nvidia.com/gpumem`；保持默认值渲染结果与 M4 完全一致（`helm template` diff 为证，不回退）
2. 在 `llm-lab-m5` 部署**两个 1.5B 实例共享同一张物理卡**（各 `gpumem≈7000`，`gpucores` 各 50），确认两个 vGPU 都落在同一张卡（`describe pod` 的 HAMi 分配注解 + 宿主机 `nvidia-smi` 看总显存）
3. 为共享口径标定 vLLM 参数：分别尝试 `gpu-memory-utilization` 0.7 / 0.85，记录启动成败、KV Cache 块数（日志里 `GPU KV cache size`）、可承载的 `max-model-len`
4. 冒烟：两个实例各打 M2 `smoke_test.py`，记录 TTFT/TPOT 与独占整卡的基线对比
5. 记录"单卡容量表"：同一张 T4 上能稳定放几个服务，各自的 KV 预算是多少

### 当天验收

- [ ] 两个服务稳定共享一张 T4，宿主机显存占用与 gpumem 之和吻合（含 context 开销）
- [ ] chart 默认渲染无回退（diff 佐证）
- [ ] 能解释为什么共享口径下 `gpu-memory-utilization` 要重新标定

### 验收参考答案

> `gpu-memory-utilization` 是"占所见总显存的比例"。独占整卡时所见总显存 ≈ 物理显存，0.85 就是 85% 物理显存；共享时所见总显存是 gpumem（虚拟值），0.85 变成 gpumem 的 85%，但 CUDA context、碎片、profile 峰值等固定开销不随比例缩放——**gpumem 越小，固定开销占比越大，util 能设的上限越低**。所以小切片要用更保守的 util，并以"启动后实际 KV block 数"而非公式为准。

---

## Day 3：隔离性验证——共享方案的可信度测试

### 学习内容

隔离性要拆成三个维度分别证伪，这是"一张 A100 上跑三个业务怎么隔离"的标准回答框架：

| 维度 | 要证明什么 | 验证方法 |
|---|---|---|
| **显存隔离** | 邻居超配/泄漏不会吃掉我的显存 | 邻居故意申请超过 gpumem 的显存 |
| **算力隔离** | 邻居打满时我的延迟/吞吐受影响多大 | 邻居持续高压，我方测 TTFT/TPOT 变化 |
| **故障域** | 邻居崩溃/OOM/被杀时我是否存活 | 杀邻居进程，观察我方请求与 Pod 状态 |

**对照组**：无隔离共享（不设 `gpumem` 上限，两个 vLLM 都按"整卡"视角抢，模拟 time-slicing 类的无隔离）——用它证明隔离的价值，而不是只证明"有隔离能跑"。

### 动手任务

1. **显存**：邻居 Pod 用 PyTorch 脚本循环 `torch.empty` 申请超过自己 gpumem 的显存，预期在其自身 OOM；观察我方 vLLM 的显存与请求是否不受影响。再对无隔离对照组重复，记录区别
2. **算力**：我方固定负载（M2 压测，闭环并发 2、输入 512/输出 128），邻居分别处于：空闲 / 低压 / 满压，各 3 次，记录我方 TTFT p95、TPOT p95、tokens/s
3. **算力配额生效性**：改 `gpucores`（如 30 / 50 / 80），看邻居满压时我方的性能是否随配额单调变化；记录配额的"抖动"（单次波动幅度）
4. **故障域**：`kill -9` 邻居的引擎进程/删除邻居 Pod，观察我方请求是否中断、是否出现 CUDA 错误；再触发一次邻居 OOM（显存超限），确认影响范围
5. 采集 `gpu_probe.py`（M3 产出）的 util/功耗/时钟曲线，对照三种邻居状态——**特别关注 T4 70W 功耗墙下的降频**（M3 Day 3）对共享场景结论的影响，在报告里单独标注
6. 产出 `report/一卡多服务隔离性验证报告.md`：三维度表 + 数据 + 结论 + 适用边界

### 当天验收

- [ ] 报告含显存/算力/故障域三维度各至少一组对照数据（隔离 vs 无隔离）
- [ ] 能给出一句结论："这套方案适合什么、不适合什么"
- [ ] 能区分"本机实测结论"与"MIG 等文档结论"

### 验收参考答案

> 预期（以实测为准，不预设）：显存隔离可靠，邻居超配只会让邻居自己失败；算力隔离只是"软 QoS"——邻居满压时我方 TPOT 一定会抬升，`gpucores` 的作用是限制上限而不是保证下限；故障域上，进程级崩溃通常不波及我方，但**驱动/硬件层故障（Xid）是共享卡的共同故障域**，一张卡上的所有服务一起倒——这条是多租户共享时 SLO 设计的底线。
> 因此一卡多服务适合：延迟不敏感或同租户内部的服务、测试/开发环境、小模型长尾；不适合：强 SLO 的核心在线服务与互不信任的租户混布（后者需要 MIG 级硬隔离或独占）。

---

## Day 4：共享路线对比与 GPU 碎片

### 学习内容

**四种路线的对比**（大纲 5.1，面试高频）：

| 方案 | 隔离层次 | 显存隔离 | 算力隔离 | 性能损耗 | 灵活性 | 本机可验证 |
|---|---|---|---|---|---|---|
| 独占整卡 | 设备 | 强 | 强 | 无 | 低 | ✓ |
| Time-slicing | 无隔离分时 | 无 | 无 | 上下文切换 | 高 | ✓（对照组模拟） |
| MPS | 进程级共享 CUDA context | 部分（可限制）| 可配比例 | 低 | 中 | 有条件（宿主机） |
| MIG | 硬件分区（SM+显存+缓存+带宽） | 强 | 强 | 几乎无 | 低（规格固定） | ✗ T4 不支持，文档 |
| HAMi | 用户态库软隔离 | 较强（拦截） | 软 | 低~中 | 高（任意切分） | ✓ |

**GPU 碎片**：整数/切片资源在多服务混布时，调度策略决定"还能不能放下一个大的"。

- **Binpack**：优先塞满已用的卡 → 保留整卡空闲，利于后续大模型
- **Spread**：均匀分散 → 单卡争用小、故障域分散，但容易把每张卡都切得"碎"

### 动手任务

1. 写 `notes/sharing-comparison.md`：上表 + 每条路线"什么场景选它"，MIG 部分单独标注为文档结论（含 A100 7 个 slice 的规格示例，以 NVIDIA 官方文档为准）
2. **碎片实验（HAMi 调度策略）**：先查本机 HAMi 版本支持的节点/卡级调度策略注解（`hami.io/gpu-scheduler-policy` 一类，以本机文档为准）；按顺序提交若干 3000 / 6000 MiB 的小 Pod，再提交一个 12000 MiB 的"大模型" Pod：
   - Binpack：大 Pod 能否调度成功？
   - Spread：同样序列下呢？
   记录 `describe pod` 的 Pending 原因与两张卡的显存分布
3. （可选，有条件）**MPS 实验**：在维护窗口中把 `llm-lab-*` 其余负载全部停掉，在宿主机启动 MPS control daemon，起两个并发进程比较与"无 MPS 分时"的吞吐；**注意这会影响正被 HAMi 管理的卡，结束后必须关闭 daemon 并验证 HAMi 服务恢复**。时间不够直接跳过，写文档对比即可
4. 拓扑感知（文档）：解释为什么 TP=2 在本机 `PHB`（无 NVLink）比 NVLink 机器慢，并写出 NVLink 亲和调度需要的节点信息（M3 Day 1/5 的拓扑与标签）

### 当天验收

- [ ] 对比表可脱稿讲，且标清楚哪些是本机实测、哪些是文档
- [ ] 碎片实验有 Binpack vs Spread 的对照数据
- [ ] 能回答"为什么推理服务适合 Binpack，而容错要求高的多副本更偏 Spread"

### 验收参考答案

> Binpack 的收益是把空闲整块留给将来的大请求，代价是同卡密度高、争用大、故障域集中；Spread 反之。**没有标准答案，取决于瓶颈**：显存碎片是主要矛盾（有大模型要上、卡紧张）→ Binpack；同卡争用/故障域是主要矛盾（多副本同一服务、要可用性）→ Spread，且要配反亲和确保同服务副本不上同一张卡。大型平台常见做法是"池分层"：小模型共享池用 Binpack，大模型独占池不切分，用池边界而不是单个策略解决冲突。

---

## Day 5：Kueue——队列、配额与抢占

### 学习内容

问题场景：多个团队共用一个 GPU 池，谁能用多少？超配了排队，还是被抢占？

Kueue 的定位（与 Volcano 的根本区别）：

```text
Kueue   ：准入控制层（admission），决定"作业能不能开始"，不替换调度器
Volcano ：调度器本身（替换 kube-scheduler 的 Pod 调度流程）
```

核心对象：

```text
ResourceFlavor ：资源的"口味"（如 T4 池 / A100 池）
ClusterQueue   ：资源池 + 配额（nominalQuota / borrowingLimit / lendingLimit）
LocalQueue     ：命名空间内的入口，指向 ClusterQueue
Cohort         ：多个 ClusterQueue 之间的借用/出借关系（公平共享的基础）
WorkloadPriorityClass + preemption ：优先级与抢占策略
```

**GPU 池的特殊性（HAMi 下）**：`nvidia.com/gpu` 此时计量的是 vGPU 切片数，而不是物理卡；`gpumem` 也是扩展资源。**配额口径要决定**：按 vGPU 数、按显存总量，还是两者同时约束——不同口径对"一个租户切了 1 个 15000 MiB 的 vGPU"产生完全不同的计费。

### 动手任务

1. 安装 Kueue（helm 或官方 manifest，版本记录进 notes）；定义一个 `ResourceFlavor`（T4 池）
2. 建两个团队队列 `team-a` / `team-b`，同一 Cohort，各自 nominalQuota（例：各 1 张卡对应的 vGPU+显存口径），`team-a` 设置 `borrowingLimit`
3. 提交 Job（`kueue.x-k8s.io/queue-name` 标签）：
   - 在配额内：直接准入
   - 超出配额：Pending（查看 `Workload` 状态与原因）
   - team-b 空闲时 team-a 借用其额度；team-b 来了触发回收/抢占，记录被抢占 Job 的行为
4. 用 vLLM 负载（短寿命 Job 形态的批量推理，或 1.5B 服务）体验"服务也走队列"的限制：在线服务通常不适合被抢占，写出你的判断依据
5. 产出 `queueing/kueue/` 配置集 + 实验记录

### 当天验收

- [ ] 能用一句话区分 Kueue 与 Volcano，并说明为什么 Kueue 与 HAMi 兼容
- [ ] 完整演示：配额内准入 / 超额排队 / 借用 / 回收（抢占）
- [ ] 能说出 HAMi 场景下配额口径的选择及理由

### 验收参考答案

> Kueue 管"准不准开工"，调度仍由 hami-scheduler 完成，两者是上下游关系，所以兼容；Volcano 自己就是调度器，会和 hami-scheduler 争夺 Pod 的调度权，同一集群上要么分池（不同节点/不同 schedulerName 的工作负载），要么用 Volcano 自带的 vGPU 方案替代 HAMi。
> 配额口径：只限 vGPU 数，租户可以通过"开很大的 gpumem"绕过；只限显存，则算力占比无约束。**生产建议至少两项同时约束（vGPU 数 + 显存），并把"按显存 × 时间"作为 M6 成本归因的计量基础。**

---

## Day 6：Volcano Gang Scheduling 与第一周整合

### 学习内容

**Gang Scheduling**：多卡/多 Pod 任务"要么全给，要么不给"。没有 Gang 的死锁场景：

```text
集群 4 卡。Job A 需要 4 个 Pod（每个 1 卡），Job B 同。
默认调度器：A 先拿到 2 卡、B 先拿到 2 卡，都在等对方释放 → 永久死锁，GPU 空转
Gang：A 凑不齐 4 个就一个都不调度，B 同理 → 至少一个 Job 能完整跑起来
```

推理场景的对应：**多节点 TP/PP 的一个模型实例**（多个 Pod 缺一个就起不来），以及 PD 分离的 Prefill/Decode 成套部署，都有 Gang 需求。

Volcano 核心对象：`Queue`（队列与权重）、`PodGroup`（minMember 即 Gang 阈值）、`vcjob`；调度插件（gang / priority / drf / binpack / predicates）。

**本机边界（再次强调）**：Volcano 与 HAMi 的调度器冲突，本机用 **CPU 资源或自定义扩展资源** 模拟 GPU 稀缺来验证 Gang 语义，不碰真 GPU 池。

### 动手任务

1. 在**隔离的命名空间**安装 Volcano；给节点增加一个自定义扩展资源（如 `example.com/fake-gpu: 4`，仅用于模拟），避免动真 GPU
2. 复现死锁：用默认调度器提交两个各需 3 个 Pod 的 Job（总量超过 4），观察互相占着不放
3. 换 Volcano + `PodGroup(minMember=3)`，对比同一场景：至少一个 Job 完整调度，另一个整体 Pending
4. 体验 Volcano `Queue` 的权重与 `reclaimable`，与 Day 5 的 Kueue 配额对照：**两者在"队列/优先级/抢占/公平共享"上各自的语义差别**
5. 写 `notes/` 选型结论：什么场景选 Kueue、什么场景选 Volcano、什么场景两者都不需要（本机在线推理现状）

### 第一周验收

- [ ] 两个服务稳定共享一张 T4，隔离性报告完成（显存/算力/故障域）
- [ ] Binpack/Spread 碎片对照数据归档
- [ ] Kueue 配额/借用/抢占演练完成
- [ ] Gang 死锁复现 + Volcano 解决，附清晰的"HAMi 兼容性"说明
- [ ] 能脱稿讲清：HAMi 机制、四种共享路线对比、Kueue vs Volcano、碎片与调度策略

---

# 第二周：推理路由、平台架构与训练侧了解

## Day 7：负载感知路由的动机与基线

### 学习内容

大纲 5.3：**为什么轮询路由对 LLM 推理不够用？**

```text
普通 Web 服务：请求成本相近 → 轮询/最少连接 ≈ 公平
LLM 推理   ：请求成本方差极大（10 token vs 10000 token）、有状态（KV Cache）
  ↓
轮询可能把两个长请求送到同一实例 → 它 KV Cache 打满、排队、TTFT 爆炸，另一实例闲着
```

可用于路由决策的信号（全部来自 M4/M2 已熟悉的 vLLM 指标）：

| 信号 | 含义 | 路由用法 |
|---|---|---|
| `vllm:num_requests_waiting` | 排队深度 | 过载的直接信号，优先避开 |
| `vllm:num_requests_running` | 在跑请求数 | 粗粒度负载 |
| `vllm:gpu_cache_usage_perc` | KV Cache 水位 | 容量视角，避免打满触发抢占 |
| 前缀命中情况 | 是否有该前缀的缓存 | 缓存亲和，命中则省 prefill |

### 动手任务

1. 在 `llm-lab-m5` 部署**同一个 1.5B 模型的 2~3 个实例**（可一卡一个，也可借 HAMi 一卡两个），确保 `/metrics` 可采集
2. 写 `router/load_gen.py`：生成**请求成本方差大**的负载（输出长度混合 32 / 512 token）和**共享前缀**负载（同一 system prompt + 不同问题），可调比例
3. 基线：用 LiteLLM 现有路由策略（轮询/最少繁忙/按延迟，以本机版本支持为准）跑两种负载，记录 TTFT p50/p95/p99、各实例 waiting 的时间曲线、总吞吐
4. 确认 `prefixCaching` 开关：前缀实验必须 `--enable-prefix-caching`，并在 notes 里说明 M2 里"v0.28 V1 默认开启"与 chart 默认关闭之间的统一口径

### 当天验收

- [ ] 基线数据能说明"轮询下实例间负载不均"（waiting 曲线佐证）
- [ ] 能说清为什么 LLM 请求成本方差使轮询失效

### 验收参考答案

> 轮询假设请求同质；LLM 请求的 prefill 成本与输出长度各自相差几个数量级，实例的"忙闲"不由请求数决定，而由在途 token 量和 KV 占用决定。基线数据上的表现是：同样的请求数，某个实例 waiting 持续 > 0 而另一实例空转，p99 TTFT 被最倒霉的实例拉高。**路由必须看到后端状态，才能从"均分请求"变成"均衡负载"。**

---

## Day 8：最小 EPP——负载 + 前缀感知路由器

### 学习内容

Gateway API Inference Extension 的核心组件叫 **EPP（Endpoint Picker）**：网关收到请求后，把"选哪个后端 Pod"的决策外包给它，它基于后端指标做挑选。今天自己写一个最小版本，把机制吃透。

路由器设计（够用即可）：

```text
请求 → 路由器
  1. 取请求前缀（如 prompt 前 N 个字符/token 的哈希）
  2. 前缀亲和：若某实例近期处理过该前缀 → 候选优先
  3. 负载过滤：候选实例的 waiting / kv_cache_usage 超阈值 → 剔除
  4. 在剩余实例中选最低负载；全超载时退化为最低负载
  5. 转发（支持 SSE 流式透传）
后台：每 1~2s 拉取各实例 /metrics 更新状态
```

**关键权衡**：前缀亲和 vs 负载均衡会冲突——热点前缀会把某一实例压垮。阈值（"亲和最多容忍多高的负载"）是核心旋钮。

### 动手任务

1. 用 FastAPI + httpx 实现 `router/epp_lite.py`：后端列表可配、metrics 拉取、三种策略可切换（`round_robin` / `least_load` / `prefix_aware`）、SSE 透传、暴露自己的 `/metrics`（路由决策计数）
2. 用 Day 7 的两种负载，对三种策略各跑 3 次，记录：
   - 共享前缀负载：**前缀缓存命中率**（vLLM `prefix_cache` 相关指标，名称以本机 `/metrics` 为准）、TTFT p50/p95
   - 方差大负载：各实例 waiting 曲线、p99 TTFT、总吞吐
3. 调阈值：前缀亲和的负载容忍度从严到松，画 TTFT p95 随阈值变化的曲线，找到拐点
4. 构造"热点前缀"：90% 请求共享同一前缀，观察 `prefix_aware` 是否让某实例过载，验证需要负载兜底
5. 将结果写入 `router/results/` 与 `notes/gateway-api-inference.md` 的"自研验证"一节

### 当天验收

- [ ] 路由器三种策略可切换且流式不被破坏
- [ ] 对照数据显示：前缀感知提升命中率/降低 TTFT，负载感知降低尾延迟
- [ ] 热点前缀实验证明了两种目标的冲突与兜底机制

### 验收参考答案

> 前缀感知把相同前缀的请求送到同一实例，复用其 KV Cache，省掉重复 prefill，TTFT 明显下降（尤其是长 system prompt 场景）；但它是"有偏"路由，热点前缀会让单实例过载。负载感知是"无偏"的兜底。工程上的做法是**打分合并或分层决策（先过滤过载实例，再在剩余里做亲和）**，并用阈值/权重暴露成可调参数，用线上命中率与尾延迟共同标定。自研版本不能替代生产实现（缺少 prefix 指纹的精确追踪、故障摘除、多网关一致性等），它的价值是**让你读 GAIE / llm-d 的调度插件时，每一个设计点都有对应的实验直觉**。

---

## Day 9：Gateway API Inference Extension 与推理平台项目

### 学习内容

**Gateway API Inference Extension（GAIE）**：把"推理感知路由"标准化到 K8s 生态。需要读懂四层结构（具体 CRD 名称、版本以官方文档为准，该项目迭代快）：

```text
Gateway（Envoy Gateway / kgateway / Istio 等实现）
  ↓ ext-proc / 外部处理
EPP（Endpoint Picker）：基于指标 + 缓存感知 + 优先级选后端
  ↓
InferencePool：一组共享同一基础模型的推理 Pod（后端池）
  ↓
模型/优先级对象：区分模型名、关键性（critical / sheddable）、LoRA 适配器等
```

EPP 的调度思路（与你 Day 8 的自研对照）：过滤（健康/容量）→ 打分（队列深度、KV 水位、前缀命中、LoRA 亲和）→ 选择；还支持**按请求优先级在过载时丢弃低优先级**。

**推理平台类项目**（了解定位，不求全部部署）：

| 项目 | 定位 | 关键词 |
|---|---|---|
| llm-d | K8s 原生分布式推理栈，围绕 vLLM + GAIE | PD 分离、前缀缓存感知、分层 KV 缓存 |
| AIBrix | 云原生推理控制平面 | 高密度 LoRA 管理、分布式 KV 缓存、负载感知网关、自动扩缩 |
| KServe | 通用模型服务抽象（M4 已提） | InferenceService、canary |

### 动手任务

1. 读 GAIE 官方文档与 EPP 源码的调度插件部分（filter / scorer），整理一张"Day 8 自研路由器 vs EPP 插件"的对照表：哪些你已实现，哪些是生产必备但你没做
2. （可选）在 k3s 安装 GAIE 的 CRD，创建一个 `InferencePool` 指向 Day 7 的实例，观察资源状态；完整 Gateway 数据面（Envoy 等）本机资源有限，按文档分析即可
3. 写 `notes/llm-d-aibrix.md`：两个项目的架构要点、解决的问题、适用规模；**回答"本机现状（单节点、2 卡）该不该上这些项目"**
4. 把 M4 Day 9 的"chart + LiteLLM 够用/需要 KServe"选型结论扩展一层：**需要推理感知路由的信号是什么（实例数 ≥ ?、前缀复用率 ≥ ?）**

### 当天验收

- [ ] 能讲清 GAIE 里 Gateway / EPP / InferencePool 各自的职责
- [ ] 完成"自研 vs EPP"对照表
- [ ] 能给出推理感知路由的引入信号，而不是"别人都在用"

### 验收参考答案

> 引入信号（经验性判断，需结合自己的数据标定）：① 同一模型有多个副本，且 waiting 在实例间长期不均；② 请求有大量共享前缀（长 system prompt、RAG 模板、多轮对话），前缀缓存命中率有明显提升空间；③ 多 LoRA 服务，需要适配器亲和。三项都不满足（单副本、前缀各异）则轮询加简单 least-busy 已足够。**平台化的节奏应该是"指标先暴露出问题，再引入机制"，而不是先上平台。**

---

## Day 10：训练侧了解——只为和算法团队对话

### 学习内容

大纲 5.4 明确：**不深入，只需能对话**。三个主题各用一句话和一张图讲清：

| 主题 | 定位 | 你需要知道的 |
|---|---|---|
| Ray / Ray Serve | 分布式计算框架 / 其上的在线服务层 | Head + Worker 架构；KubeRay 在 K8s 上管理集群；Ray Serve 做模型编排与多模型 pipeline；vLLM 的多机 TP/PP 常借 Ray 做进程编排 |
| Kubeflow / Training Operator | K8s 上跑分布式训练的 CRD 集合 | `PyTorchJob` 等，管 master/worker 拓扑与重试；背后依赖 Gang 调度（回扣 Day 6） |
| Checkpoint 与故障恢复 | 训练容错的核心 | 定期保存状态；故障后从最近 checkpoint 续训；频率 vs 存储开销的权衡；存储带宽是瓶颈 |

与你的职责边界：**平台提供 GPU 池、队列、存储、网络与监控；算法同学提交 Job**。运维视角的关键问题是：Gang 调度、故障后自动重启、checkpoint 存储可用性、GPU 掉卡时任务如何迁移（回扣 M3 Xid 处置）。

### 动手任务

1. 写 `notes/training-side-brief.md`：上述三块 + "一次训练任务在平台上的生命周期"（提交 → 排队 → Gang 调度 → 运行 → 掉卡/抢占 → checkpoint 恢复 → 完成）
2. （可选，轻量）用 KubeRay 在 k3s 起一个最小 Ray 集群（CPU 即可），跑通一个 Ray Serve hello world，观察 Head/Worker Pod 结构；不做 GPU 训练
3. 整理"与算法团队沟通的 10 个问题"清单（模型大小/并发/上下文/SLO/量化容忍度/checkpoint 频率等），这是你上线任何模型前的需求模板

### 当天验收

- [ ] 能用不到 3 分钟讲清 Ray、Training Operator、checkpoint 各自的作用
- [ ] 能说出训练任务与在线推理对调度系统的需求差异（Gang/长时间运行/可抢占 vs 低延迟/不可抢占）

### 验收参考答案

> 训练任务：长时间运行、多 Pod 必须成套（Gang）、可被抢占但必须能从 checkpoint 恢复、对吞吐和互联敏感、对单次延迟不敏感；在线推理：副本相对独立、请求级延迟敏感、不可随意抢占、对启动时间和流量切换敏感。**同一个 GPU 池服务两类负载时，需要靠队列/优先级/分池策略把它们的冲突表达清楚**，这就是平台化的核心工作之一。

---

## Day 11：多租户端到端与平台架构图

### 学习内容

把前十天的零件串成一个"租户视角"的闭环，这是 M5 的整合日：

```text
租户（团队 A）
  ├─ 身份与计费：LiteLLM 虚拟 key（M4 Day 9）→ token 限流 / 预算
  ├─ 入口：网关 → 路由（Day 7/8 的感知路由）→ 后端池
  ├─ 命名空间：namespace + ResourceQuota + NetworkPolicy（M4 Day 9）
  ├─ 队列与配额：Kueue LocalQueue（Day 5）
  ├─ GPU 切片：HAMi gpumem/gpucores（Day 2/3）
  └─ 监控：vLLM /metrics + GPU 指标（M6 展开）
```

### 动手任务

1. 搭建两个模拟租户 `team-a` / `team-b`：各自命名空间、Kueue 队列、LiteLLM 虚拟 key（模型白名单 + TPM），后端是共享一张 T4 的两个 1.5B 实例
2. 端到端演练：
   - 正常流量：两租户并行使用，记录各自的 token 用量与延迟
   - `team-a` 超 TPM：被网关 429，`team-b` 不受影响
   - `team-a` 申请超配额的 GPU 资源：Kueue 排队
   - `team-a` 的服务压满：确认对 `team-b` 的影响（回扣 Day 3 的算力软隔离结论）
3. **画架构图** `report/AI推理平台架构图.md`（mermaid 或 drawio 导出），分层：
   - 接入层：网关、鉴权、限流、路由（含推理感知路由）
   - 调度层：Kueue / Volcano / hami-scheduler
   - 资源层：GPU 池（独占池/共享池）、存储（权重 PVC/对象存储）
   - 服务层：vLLM 实例、LoRA、PD 分离（规划）
   - 可观测层：DCGM / vLLM metrics / Langfuse（规划，M6 补全）
   - 成本层：用量记账与归因（规划，M6 补全）
4. 图上标注每个组件"**本机已实操 / 文档了解 / 规划**"，不混写

### 当天验收

- [ ] 双租户端到端演练的现象记录完整（限流、配额、干扰三种）
- [ ] 架构图分层清晰，已实操与规划区分明确
- [ ] 能讲一遍"一个请求从租户到 GPU"的完整路径，并指出每一层的隔离/治理手段

### 验收参考答案

> 一条完整路径：租户携带虚拟 key → 网关鉴权/限流/预算 → 推理感知路由选后端实例 → 后端 Pod 在租户命名空间，其 GPU 资源由 Kueue 准入（配额）、hami-scheduler 选卡、libvgpu 限显存/算力 → vLLM 内部再由 `max-num-seqs`/`max-model-len` 约束并发。**五层治理各管一件事：谁能进（鉴权）→ 进来多少（token 限流）→ 去哪里（路由）→ 能占多少资源（队列+切片）→ 进来怎么消化（引擎参数）**，缺任何一层都会在某个故障场景里暴露出来。

---

## Day 12：M5 总验收

### 综合演练

模拟一次"资源紧张的一天"：

1. 池中同时存在：共享池的两个小模型服务、一个 7B AWQ 在线服务、一个批量推理 Job
2. 注入：批量 Job 提交 → 触发 Kueue 排队/抢占；同时某租户流量激增 → 路由与限流生效；邻居满压 → 观察 Day 3 预测的干扰
3. 记录从注入到稳定的时间线，对照架构图找出：哪一层先饱和、哪一层成为第一故障点
4. 复盘：如果要把这个池扩展到 8 卡 A100 多节点，哪些设计需要变（MIG 取代 HAMi？Volcano 取代 Kueue？NVLink 亲和？PD 分离？）

### 最终自测题（脱稿回答）

- [ ] 为什么需要 GPU 共享？一张 80G 卡跑 7B 的浪费怎么量化？
- [ ] HAMi 的组件分工与 Pod 创建链路？显存隔离与算力隔离各是什么级别？
- [ ] 为什么不带 `hami-scheduler` 会失败？这反映了什么协议设计？
- [ ] 一张 A100 上跑三个业务，怎么做隔离？（显存/算力/故障域三维度，MIG 与 HAMi 的取舍）
- [ ] time-slicing / MPS / MIG / HAMi 四种路线的差异与适用场景？
- [ ] Binpack vs Spread 对 GPU 碎片的影响？怎么选？
- [ ] Kueue 与 Volcano 的根本区别？为什么 Kueue 能与 HAMi 共存而 Volcano 不能直接叠加？
- [ ] Gang Scheduling 解决什么死锁？推理场景哪里需要？
- [ ] HAMi 场景下 Kueue 配额口径怎么选？
- [ ] 为什么轮询对 LLM 推理不够用？有哪些路由信号？
- [ ] 前缀感知路由与负载均衡的冲突是什么？怎么兜底？
- [ ] GAIE 里 EPP / InferencePool / Gateway 的分工？
- [ ] llm-d / AIBrix 分别解决什么？什么规模才值得引入？
- [ ] Ray、Training Operator、checkpoint 各自作用？训练与在线推理对调度的需求差异？
- [ ] 一个请求从租户到 GPU 的完整治理路径？

---

# 四、最终产出物

## 1. 《一卡多服务隔离性验证报告》

- [ ] 显存 / 算力 / 故障域三维度，隔离与无隔离对照
- [ ] T4 功耗墙对结论影响的标注
- [ ] 适用/不适用边界结论

## 2. 《AI 推理平台架构图》

- [ ] 接入 / 调度 / 资源 / 服务 / 可观测 / 成本 六层
- [ ] 每个组件标注"已实操/文档/规划"
- [ ] 配套"一个请求的完整路径"说明

## 3. 路由器与对照实验（`router/`）

- [ ] `epp_lite.py`：三种策略、SSE 透传、自带指标
- [ ] 前缀命中率、TTFT、尾延迟的对照数据
- [ ] 阈值拐点曲线与热点前缀实验

## 4. 调度与队列实验（`hami/` + `queueing/`）

- [ ] chart 增加 HAMi 参数且默认无回退
- [ ] Binpack/Spread 碎片对照
- [ ] Kueue 配额/借用/抢占演练
- [ ] Volcano Gang 死锁复现与解决（模拟资源，已标注与 HAMi 的冲突）

## 5. 笔记

- [ ] `hami-internals.md` / `sharing-comparison.md` / `gateway-api-inference.md` / `llm-d-aibrix.md` / `training-side-brief.md`

---

# 五、学习资源

| 资源 | 用法 | 优先级 |
|---|---|---|
| HAMi 官方文档（project-hami.io） | 资源声明、调度策略、版本差异 | 最高 |
| Kueue 官方文档 | ClusterQueue / Cohort / 抢占 | 高 |
| Volcano 官方文档 | PodGroup / Queue / 调度插件 | 高 |
| Gateway API Inference Extension 官方文档与仓库 | InferencePool / EPP 调度插件 | 高 |
| vLLM 文档 · Metrics / Prefix Caching | 路由信号与前缀缓存口径 | 高 |
| NVIDIA 官方文档（MIG / MPS） | 文档结论来源 | 中 |
| llm-d、AIBrix 项目文档 | 平台项目定位 | 中 |
| KubeRay / Kubeflow Training Operator 文档 | 训练侧了解 | 低 |
| jimmysong.io kubernetes-handbook · AI Native | 中文参考 | 中 |

---

# 六、明确取舍与避坑

M5 必须深入：

- HAMi 机制与隔离性验证（显存/算力/故障域三维度）
- 共享路线对比（HAMi / MPS / MIG / time-slicing）与碎片
- Kueue 队列与配额；Gang 调度的语义
- 推理感知路由的信号与取舍

M5 只做概念了解：

- MIG 实际切分（本机 T4 不支持）
- GAIE 数据面完整部署、llm-d / AIBrix 全量部署
- Ray / Kubeflow / 分布式训练（只为对话，不自建训练平台）
- DRA（知道趋势：用 ResourceClaim 取代 device plugin 描述复杂设备，当前主流仍是 device plugin / HAMi / GPU Operator）

常见误区：

1. **把 HAMi 当 MIG 用**——它是软隔离，驱动/硬件故障域仍共享，强 SLO 与互不信任租户不能混布
2. **共享后沿用独占口径的 `gpu-memory-utilization`**——所见总显存变了，固定开销占比上升
3. **只测显存隔离就宣布"隔离完成"**——算力干扰和故障域才是共享方案的真问题
4. **Volcano 与 hami-scheduler 叠加到同一批 GPU Pod 上**——调度权冲突，直接失败
5. **Kueue 配额只限 vGPU 个数**——租户可用超大 gpumem 绕过
6. **所有服务一律 Binpack**——高可用副本会被塞进同一张卡，单点故障
7. **不看数据先上推理网关项目**——指标没暴露出问题就上平台，运维复杂度先于收益
8. **把自研路由器直接推生产**——它是学习工具，不替代 EPP

判断标准：

> 每个实践都问一句：它解决的是"服务挂了、成本高了、卡不够了"中的哪一个？如果说不出，就先别引入。

---

M5 完成后进入 M6（可观测性与成本治理）：本周搭建的"共享池 + 租户 + 路由"正好是 M6 的观测对象——按租户/模型拆账、共享卡上的单位 token 成本、GPU 利用率提升前后的量化对比，都建立在这套平台之上。
