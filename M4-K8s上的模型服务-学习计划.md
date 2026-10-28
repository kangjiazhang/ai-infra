# M4 · Kubernetes 上的模型服务学习计划

> 学习周期：2 周（每周 6 天，共 12 天）
> 建议投入：工作日每天约 2 小时，周六 3～4 小时
> 学习目标：把已有的 K8s / Helm / ArgoCD / Prometheus 技能套到 GPU 推理负载上——重点是掌握 LLM 服务区别于普通无状态服务的运维特性（冷启动、真实推理探针、SSE 长连接、GPU 感知伸缩、发版不中断长请求）。
> 核心产出：一个完整的多环境 `vllm-inference` Helm chart（ArgoCD 管理）、一份《LLM 服务发布 SOP》。
> 大纲定位：**这是你的舒适区，别恋战**——通用 K8s 能力直接复用，时间省下来补 M6 的可观测性。

---

## 一、M3 到 M4 的能力衔接

进入 M4 前，应能不看资料解释（M2/M3 已建立）：

- `nvidia.com/gpu` 从 device plugin 注册到容器注入的完整链路
- GPU 节点的标签、污点、亲和调度模式（M3 Day 5 的 selector/toleration 模板）
- GPU Util 的欺骗性——真正的探活必须打真实推理（M2 Day 1/2 反复验证）
- 首次请求包含 CUDA Graph/JIT 预热开销，稳态与冷态差异大（M2 EXP-001/002）
- 7B FP16 需要双卡 TP=2、INT4 可单卡——不同模型的资源形状不同（M2 Day 14 对照表）
- `/health` 只探 APIServer 进程，GPU 卡死时照样 200（M2 Day 2）

M4 要建立的工程闭环：

```text
Helm chart 模板化（多环境 values）
  ↓
权重分发与冷启动治理
  ↓
探针设计（startup 给足时间 / readiness 打真实推理）
  ↓
流量层（SSE 超时 / 优雅下线 / 滚动策略）
  ↓
伸缩（GPU 感知指标，拒绝 CPU 利用率）
  ↓
发布流程（GitOps + 金丝雀 + 回滚 SOP）
```

M4 的最终目标是：

> 从"能在 K8s 里跑起一个 vLLM"（M2 的 vllm-smoke 已达到），进阶到"一个可以安全发版、优雅缩放、出事能按 SOP 处置的生产级推理服务"。

---

## 二、固定学习方法

每天按以下节奏进行：

1. **20 分钟原理**：大部分概念你已懂，只补 LLM 特有的差异点
2. **80 分钟实验**：以写 chart、跑发布演练为主
3. **20 分钟复述**：用"普通服务这么做 / LLM 服务为什么不能"的对比句式总结

### 实验纪律（延续 M2/M3）

- 所有 chart 变更走 Git 提交，ArgoCD 同步——从 Day 1 起就按生产习惯操作
- 每次发版演练记录：时间线（旧 Pod 退出 → 新 Pod 就绪 → 流量切换）、是否有请求失败
- 本机双 T4 资源有限：多副本实验用 INT4 单卡模型，TP=2 实验最多 1 副本
- 破坏性实验（杀 Pod、OOM）在 QA 环境 values 下做，实验后恢复基线
- **环境快照升级**（M2 Day 14 断连教训）：`collect_env.sh` 增加 `env | grep -E '^(VLLM|CUDA|HF)_'`

### 建议目录

```text
python/m4/
├── helm/
│   └── vllm-inference/           # 核心产出：多环境 chart
│       ├── Chart.yaml
│       ├── values.yaml           # 基线默认值
│       ├── values-qa.yaml        # QA：单卡 INT4、探针宽松、资源小
│       ├── values-staging.yaml   # 预发：贴近正式、用于发布演练
│       ├── values-prod.yaml      # 正式：严格探针、发布策略
│       └── templates/
├── argocd/
│   └── application.yaml          # Application 定义（含多环境）
├── gateway/
│   └── litellm-values.yaml       # LiteLLM 网关部署（第二周）
├── release/
│   └── 发布演练记录.md            # 每次演练的时间线与失败请求数
└── notes/
    ├── cold-start-analysis.md    # 冷启动分解与优化记录
    ├── weight-distribution.md    # 权重分发方案对比
    └── hpa-metrics.md            # 伸缩指标选型分析
```

目录仍建在本地 mac 的 study 仓库；chart 通过 Git 推送后由服务器上的 ArgoCD 拉取同步——**这本身就是 M4 要练的 GitOps 工作流**。

---

## 三、实验环境与资源规划

### 复用现有资产

| 资产 | 来源 | M4 用法 |
|---|---|---|
| k3s 集群 | M2 起 | ArgoCD 部署目标 |
| `llm-lab-m2` 命名空间的 vllm-smoke | M2 Day 1 | 迁移进 chart 管理，作为对照 |
| M3 的 GPU 节点标签/污点 | M3 Day 5 | chart 里 selector/toleration 直接引用 |
| M2 的压测脚本与客户端 | M2 Day 7 | 发版演练时打背景流量，验证优雅下线 |
| 模型缓存 `/root/leon/m2/models` | M2 | 权重分发实验的本地缓存基线 |
| Prometheus 栈 | **k3s 只自带 metrics-server，不含 Prometheus** | HPA 自定义指标的来源；Day 0 前置安装（同时为 M6 打底） |

### 双 T4 的实验边界

- **副本数**：INT4 单卡模型最多 2 副本（一卡一副本）；TP=2 FP16 只能 1 副本——正好覆盖"滚动更新时 maxSurge 的两难"这个知识点
- **金丝雀/AB**：物理上做不了真正的双版本并行（资源不够两套 7B），演练方式：QA 环境 1.5B 模型双副本做金丝雀，报告注明规模限制
- **KEDA 缩容到零**：可以完整实验（1.5B 冷启动 ~40s，适合观察）
- **存储类**：本机无现成分布式存储，PVC 用 local-path（k3s 默认）；对象存储方案做文档分析 + 最小验证

### 前置检查（Day 0，半天）

1. ArgoCD 是否已在 k3s：`kubectl get pods -n argocd`；没有则先装（helm repo add argo + install，你熟）
2. 确认 Git 仓库可被服务器访问（ArgoCD 需要拉取）：私有仓库则配 repo secret
3. `kubectl get sc` 确认 local-path 存在
4. 安装 kube-prometheus-stack：**k3s 只带 metrics-server，不含 Prometheus**——Day 7 的 HPA 和 M6 的可观测性都建在它上面，提前装好，别让装栈吃掉 Day 7 的实验时间
5. 归档当前 `llm-lab-m2` 的手写 manifest（将作为 chart 迁移的对照源）

---

# 第一周：把 vLLM 装进生产级 Chart

## Day 1：Chart 骨架与多环境 values

### 学习内容（只需补的差异点）

通用 chart 结构你已熟，LLM 推理服务的 chart 有四个先天差异：

1. **资源形状怪异**：`nvidia.com/gpu: 1` 是整数资源，不能像 CPU 那样微调；resources.limits 里 GPU 与显存预算（`gpu-memory-utilization`）要联动
2. **配置即容量**：`--max-model-len`、`--max-num-seqs`、`--gpu-memory-utilization` 不只是"应用配置"，它们直接决定服务的容量上限——多环境 values 的差异比普通应用大得多
3. **镜像巨大**：vLLM 镜像数 GB，镜像拉取时间是滚动更新的主要瓶颈之一
4. **模型 ID 是配置不是镜像**：同一个镜像 + 不同 model 参数 = 完全不同的资源形状

### 动手任务

1. 创建 `helm/vllm-inference/` 骨架，templates 至少包含：
   - `deployment.yaml`（含 selector/toleration——引用 M3 Day 5 模板）
   - `service.yaml` + `serviceaccount.yaml`
   - `configmap.yaml`（vLLM 启动参数）
   - `secret.yaml`（HF_TOKEN，可选）
   - `NOTES.txt`（部署后自检指引）
2. values 基线设计（对照 M2 实测数据写注释）：

```yaml
# values-qa.yaml 示例要点
model:
  id: Qwen/Qwen2.5-7B-Instruct-AWQ    # INT4 单卡
  tp: 1
args:
  maxModelLen: 4096        # M2 Day 8 结论：按业务 P99 定，不照搬标称
  maxNumSeqs: 8            # M2 Day 9 的 T4 保守值
  gpuMemoryUtilization: 0.85
resources:
  limits:
    nvidia.com/gpu: 1
probes:
  startupPeriodSeconds: 10
  startupFailureThreshold: 60    # 冷启动预算，Day 3 校准
```

3. `helm template` 本地渲染检查 → `helm install` 到 QA 命名空间 → 冒烟（复用 M2 smoke_test.py）
4. 把 M2 的 vllm-smoke 手写 manifest 与 chart 渲染产物 diff，确认无能力回退

### 当天验收

- [ ] chart 可一键安装/卸载，`helm upgrade` 幂等
- [ ] QA 环境 values 渲染出的参数与 M2 手写部署等价（diff 佐证）
- [ ] 能说出这个 chart 与你以往的普通服务 chart 的 4 个差异

### 验收参考答案：LLM chart 与普通服务 chart 的差异

> ① 资源维度不同：GPU 是整数扩展资源且与 `gpu-memory-utilization` 联动，容量参数（max-model-len/max-num-seqs）写进 values 就是在定义服务容量上限，多环境差异本质是容量规划差异而非开关差异；② 生命周期不同：启动分钟级（权重加载 + torch.compile + CUDA Graph），探针和滚动策略必须按这个现实设计，不能套用秒级就绪的 Web 服务模板；③ 存储策略不同：模型权重数 GB 级，分发方案（PVC/对象存储/镜像内置）是架构决策而非默认项；④ 流量语义不同：SSE 长连接让"连接断 = 请求死"，优雅下线不是可选项。

---

## Day 2：模型权重分发与存储

### 学习内容

四种方案的真实权衡（大纲 4.1 重点）：

| 方案 | 首次启动 | 换模型 | 适用 | 本机可验证 |
|---|---|---|---|---|
| 镜像内置权重 | 慢（拉 GB 级镜像层） | 需构建+推镜像 | 模型少且稳定、边缘/离线 | 部分（构建 1.5B 验证） |
| PVC 共享卷 | 快（挂载即用） | 改 PVC 内容 | 同节点多副本共享 | ✓（local-path） |
| 对象存储 + 下载 | 中（首次下载后缓存） | 改下载地址 | 云上标准做法、模型多 | 文档分析 + COS 最小验证 |
| initContainer 预热 | 并行于调度 | 灵活 | 权重与镜像解耦 | ✓ |

关键认知（M1/M2 已铺）：

- 权重下载不是一次性成本，而是**每次 Pod 重建的成本**——与 HPA 扩容、滚动更新、节点驱逐联动
- PVC 方案在**单节点 local-path** 下就是"宿主机目录挂载"，效果等价于 M2 的模型缓存；跨节点才需要真正的共享存储
- `HF_HOME` 指向 PVC + `HF_HUB_OFFLINE=1`（缓存完整时）= 生产常用的"下载一次，永久本地"

### 动手任务

1. 建一个 PVC（local-path，20Gi），把已缓存的 AWQ 模型 `models--Qwen--...` 目录放入
2. chart 增加 `persistence` 开关：Deployment 挂 PVC + env `HF_HOME` 指向挂载点 + `HF_HUB_OFFLINE=1`
3. 记录三组启动耗时对比（同模型同卡）：
   - A：无缓存冷下载（可用地域 COS 镜像或先清缓存）
   - B：PVC 挂载已缓存权重
   - C：M2 原来的宿主机路径（对照）
4. 可选：写一个 initContainer 预热模板（`huggingface-cli download` 到 emptyDir/PVC），验证其失败重试行为
5. 产出 `notes/weight-distribution.md`：四方案对比表 + 本机实测三组数据 + 选型建议

### 当天验收

1. 为什么说权重分发方案决定了 HPA 的实际响应速度？
2. `HF_HUB_OFFLINE=1` 什么时候是优化、什么时候是坑？
3. 镜像内置权重为什么与"模型迭代快"矛盾？

### 验收参考答案

#### 1. 权重分发与 HPA 的关系

> HPA 扩一个副本 = 调度 + 拉镜像 + **获得权重** + 加载 + 预热，其中权重环节在无缓存方案下是分钟级（7B INT4 约 5 GB，下载速度决定）。扩容响应时间 = 这些环节之和，所以"权重就在本地 PVC"的方案省得了下载、省不了加载；而缩容到零再扩回时，权重方案直接决定服务中断时长。这是 Day 9 KEDA 缩容到零实验会再次撞上的现实。

#### 2. HF_HUB_OFFLINE 的两面性

> 优化面：缓存完整后离线加载跳过所有 HEAD 请求，避免 HF 限流/网络抖动导致的启动失败（M2 压测时踩过 401/Repository Not Found 的坑，离线模式直接免疫）。坑面：缓存不完整或模型 revision 更新后，离线模式会加载失败或永远用旧版本——正确姿势是镜像/CI 侧预热缓存并固定 revision，运行时离线；把"缓存是否完整"纳入发布检查清单。

#### 3. 镜像内置与快速迭代的矛盾

> 每换一次模型 = 构建 GB 级镜像 + 推送 + 各节点重新拉取，迭代成本高；而生产里模型更新频率往往高于镜像更新频率。镜像内置真正的甜区是：模型固定不变（如内网专用小模型）、边缘离线环境、或把"权重即镜像"作为版本不可变性的强约束。多模型频繁切换的平台，权重必须与镜像解耦——这正是 4.4 多模型管理要解决的。

---

## Day 3：冷启动治理与探针设计

### 学习内容

LLM 服务探针是大纲点名的运维大痛点，M2 已积累了完整素材。

### 冷启动分解（基于 M2 实测）

```text
Pod 创建 → 镜像拉取（GB 级，节点无缓存时最慢）
  → 权重获得（Day 2 的方案决定）
  → 权重加载进显存（M2 实测 GPTQ 4.95s / 5.27 GiB）
  → torch.compile（首次实测 24s；缓存命中后的耗时待 Day 3 实测校准——不要预设 ≈0）
  → CUDA Graph 捕获（本机 v0.28.0 捕获 51 个 batch 形状，1～512）
  → APIServer 监听 /health 200 ←—— 这一刻 K8s 就认为"就绪"了
  → 但首个真实请求还有 JIT/缓存层级预热（M2: 冒烟 TTFT 50ms → 稳态 24ms）
```

### 探针三层设计（核心）

```yaml
startupProbe:            # 只等"进程活着"，预算 = 冷启动全程
  httpGet: {path: /health}
  periodSeconds: 10
  failureThreshold: 60   # 10 分钟预算；Day 3 实测校准
readinessProbe:          # 真实推理探活（M2 Day 2 的核心教训）
  httpGet 不够用 → 打一条 1-token 生成
livenessProbe:           # 谨慎：LLM 服务误杀代价是整个冷启动重来
```

三个必须想清楚的点：

1. **readiness 打真实推理**：`/health` 只探 APIServer（M2 Day 2 验证 GPU 卡死时照样 200）。方案：小的自研 sidecar/endpoint，或 readiness 用命令探针打一条 `max_tokens=1` 的 completion（镜像里常没有 curl，用 python3 + urllib 稳妥）
2. **liveness 的取舍**：进程 hang 死该杀，但杀掉 = 冷启动重来 + 该副本所有在途长请求全断。预算上 liveness 阈值要远宽于 readiness
3. **就绪 ≠ 性能就绪**：探针通过后首请求仍慢（CUDA Graph/JIT 已做，但 KV 缓存层级冷）——发版后主动打预热流量（M2 Day 1 结论的落地）

### 动手任务

1. 在 QA 环境实测完整冷启动时间线：`kubectl get events` + Pod 日志时间戳，分解出镜像拉取/权重加载/compile/捕获各段耗时，写进 `notes/cold-start-analysis.md`
2. 实测一次**杀掉引擎进程**（模拟 GPU hang）的探针行为：readiness 是否翻转、Service 是否摘除端点、liveness 是否触发重启——把"探针设计错误 = 故障扩大"变成可引用的实验记录
3. chart 实现三层探针 + readiness 命令探针（打一条 `max_tokens=1` 的 completion），校准 startupFailureThreshold 到实测值 × 1.5；注意镜像里不一定有 curl——稳妥用 `python3 -c` + urllib，或极轻 sidecar
4. 在 NOTES.txt 里固化发版后预热脚本调用（打 10 条真实请求）

### 当天验收

1. 为什么 startupProbe 对 LLM 服务是必需品而不是可选项？
2. readiness 打 `/health` 会漏掉什么故障？举 M2 的实例
3. liveness 太敏感在这个场景会放大成什么事故？
4. 探针全绿之后，为什么还要打预热流量？

### 验收参考答案

#### 1. 为什么 startupProbe 必需

> 没有 startupProbe 时，readiness/liveness 从容器启动就计时——LLM 冷启动分钟级（权重加载 + compile + CUDA Graph 捕获），liveness 会在服务还没起来时就把 Pod 杀掉，进入 CrashLoop：**探针本身制造了故障**。startupProbe 的语义就是"先等启动完成，再开始健康检查"，它把"启动慢"和"启动后不健康"分开。预算按实测冷启动 × 1.5 设置（Day 3 实测校准），普通服务 10 秒就绪用不到这个机制，LLM 服务没有它基本无法上线。

#### 2. readiness 打 /health 漏掉什么

> 漏掉整个 GPU 执行层。`/health` 由 APIServer 进程应答，只证明 HTTP 门面活着；引擎卡死、NCCL 挂起、KV Cache 异常时它照样 200（M2 Day 2 的分层结论：APIServer 与 EngineCore 只靠 ZMQ 消息往来，前者不感知后者健康度）。后果：故障副本继续接流量，用户看到的是请求 hang 到超时。真实推理探针（打一条 max_tokens=1 的 completion）才能覆盖完整链路：API → 调度 → GPU forward → 返回。代价是探针本身消耗一点算力——所以用极小请求且间隔放宽（10~15s），并注意别让它进业务监控统计。

#### 3. liveness 敏感的事故放大

> 误杀一个 LLM Pod 的代价 = 完整冷启动（分钟级）+ 该副本在途长请求全部中断（长请求可能已生成几百 token）。如果是 GPU hang 之类的真故障，副本重启大概率还是坏的——于是每个周期都付出"冷启动 + 流量损失"的代价。设计原则：liveness 阈值远宽于 readiness（给 hang 判定留充分证据），并优先靠 readiness 摘流量止损，liveness 只兜底"进程真死了"的场景。GPU 类故障的正确处理是告警 + 人工/自动化隔离（M3 Day 6 的 cordon SOP），而不是指望重启治好硬件。

#### 4. 为什么还要预热

> 探针通过 = 组件就绪，不等于性能就绪：首个真实请求仍包含缓存层级未热、分支代码未编译、内存池未分配等冷态开销（M2 EXP-001：冒烟轮 TTFT 50ms → 稳态 24ms，差 2 倍多）。落到用户头上就是"发版后第一批用户体验最差"。所以发版流程的最后一步是主动打一轮真实请求把服务推到稳态——这不是玄学优化，是把 M2 学的"预热不能省"从压测纪律升级为发布 SOP 的固定动作（Day 11 的 SOP 会把它写进流程）。

---

## Day 4：Service、Ingress 与 SSE 流式流量

### 学习内容

你已熟悉 Service/Ingress/CLB 的通用部分，只补 LLM 特有的四个流量问题：

1. **SSE 长连接 vs 网关超时链**：一次生成 = 一条连接保持几十秒（TTFT + N × TPOT）。链路上每一层超时都必须大于最长请求：

```text
客户端 → Ingress/网关 → Service → Pod
每层检查：网关 read timeout / 连接 keepalive / 客户端超时
vLLM 侧：--timeout 是"排队等待超时"（在队列里等太久返回 464），不是生成中途超时
         ——引擎层没有"生成到一半掐断"的机制，掐断只会来自链路上的其他层
```

   陷阱：很多网关默认 60s read timeout，长输出请求在生成中途被掐断，客户端表现为"流式输出突然停止"——这类故障常被误报为"模型卡死"。

2. **流式响应的压缩**：逐 token 的 SSE chunk 若经 gzip，小包压缩率低还耗 CPU；一般对 SSE 路径关闭代理层压缩
3. **超时≠限制**：网关层用 max_tokens 和 token 限流控制请求时长（M1 Day 1 的 TPM/RPM 结论），比事后靠超时兜底优雅
4. **CLB 也是链路的一层**：云上 `type: LoadBalancer` 的 CLB/ELB 有自己的空闲超时（常见默认 60s，可调），k3s servicelb 是本地实现——用你已有的 CLB 经验检查它的 idle timeout 是否大于最长 SSE 连接

### 动手任务

1. Ingress（k3s 用 traefik 或装 ingress-nginx）暴露 chart 服务，配置 SSE 友好参数：read timeout ≥ 300s、禁用 buffer、关闭响应压缩
2. 复用 M2 客户端打一条长输出请求（512 token），验证全链路流式不被截断；人为把网关 timeout 调到 5s 复现"中途断流"，归档现象与排查路径
3. 给 chart 增加 `ingress` 模板（多环境开关：QA 走集群内 Service，prod 走 Ingress）
4. `notes/` 补一条 SSE 排障路径：客户端断流 → 网关超时配置 → 服务端 metrics（e2el 分布）→ 判定断在哪层

### 当天验收

1. 用户反馈"回答到一半就停"，给出分层排查顺序
2. 网关超时该按什么值设置？和什么指标挂钩？
3. 为什么按 token 限流比按请求限流更能保护这个服务？

### 验收参考答案

#### 1. 断流排查顺序

> ① 看服务端 `/metrics` 的 e2el 分布与 `finish_reason`：如果服务端请求正常完成（token 数齐、无错误），断点在服务端之外——这是最快的二分；② 查网关/Ingress 的 read timeout 与 buffer 配置（本 Day 实验的 5s 复现就是标准现场）；③ 查客户端自己的超时/断连（SSE 解析库的 idle timeout 常被忽略）；④ 都正常再回到服务端看 KV Cache 抢占/异常（ITL 尖峰后客户端主动断开的场景）。顺序的依据：**先证明"服务端完成了没有"，再往链路外层走**——服务端 metrics 是唯一权威的第一现场。

#### 2. 网关超时怎么设

> 按业务允许的最长请求设：`SLO 内最大输出 token 数 × TPOT p99 + TTFT p99 + 余量`，且必须大于客户端可接受等待。例：512 token × 62ms（M2 实测 TPOT）≈ 32s + TTFT → 正常流量的底线是 60s；再为异常长尾加余量，实操配 300s（与 Day 4 任务 1 的值一致）。关键原则：**超时是安全网不是调节手段**——正常请求永远不该撞到它，撞到说明 max_tokens/限流没管好。三层（客户端/网关/引擎）要同心圆式递增，网关 ≥ 客户端预期，引擎 ≥ 网关。

#### 3. 为什么按 token 限流

> M1 Day 1 的结论：请求成本与 token 数强相关，30 token 与 10000 token 的请求资源消耗差千倍，按请求数限流保护不了任何东西——几个长请求就能占满 KV Cache 和 Decode 算力。按 TPM 限流才对齐真实瓶颈；再配合单请求 max_tokens 上限（防单条超长）与并发数上限（防 KV Cache 打满），构成三层防护。这个设计在 4.4 LiteLLM 网关里会真正落地成配置。

---

## Day 5：优雅下线与滚动更新

### 学习内容

**大纲点名题：怎么做到发版不中断正在生成的长请求？**

Pod 收到 SIGTERM 后的时间线：

```text
Pod 标记 Terminating（Endpoints 异步摘除开始）
  ↓ preStop 钩子执行（kubelet 实现：preStop 完成后才发信号——sleep 期间主进程还没收到 TERM）
  ↓ SIGTERM 到达主进程 → shutdown 开始：APIServer 停止接新请求
     是否等待在途请求、上限由谁控制 ←—— 以本机 v0.28.0 实测为准
     （先 `vllm serve --help` 核对 shutdown 相关参数；版本间行为差异大，不要预设"一定 drain"）
  ↓ 进程退出 → 容器终止
```

机制由**两个 K8s 旋钮 + 一个引擎行为**三段组成，必须联动（注意：真正防中断的是这三段；"Connection: close"不是旋钮，是引擎行为的观察点之一）：

1. **preStop（K8s 旋钮）**：先 `sleep 10` 左右，覆盖 Endpoint 摘除的传播延迟，确保新流量进不来。没有这一步，shutdown 期间仍在接新请求，在途存量永远清不完
2. **引擎 drain 行为（应用层，不是旋钮）**：vLLM 收到 SIGTERM 后怎么对待请求——是否拒绝新流、是否等存量生成完、是否主动断连（响应头/连接行为是观察点）。版本间差异大，必须先实测确认（见任务 1）
3. **`terminationGracePeriodSeconds`（K8s 旋钮）**：兜底时限。理论下限 = preStop 睡眠 10s + 最长在途剩余生成（512 × 62ms ≈ 32s）+ 收尾 ~10s ≈ **52s**；乘安全系数 1.5~2 → **120s 起步**（完整推导见验收答案 4——注意 120s 不是 32s 直接推出的）

### GPU 资源紧张下的滚动更新两难（大纲点名题）

`maxSurge`/`maxUnavailable` 在 GPU 世界变形：

- 双卡只够 1 副本 TP=2 时：`maxSurge=1` 意味着**同时需要两套副本的 GPU**（旧 2 卡 + 新 2 卡）——根本没资源，滚动卡死
- 解法：`maxSurge=0, maxUnavailable=1`（先杀旧的起新的）→ 牺牲可用性换可行性。注意 INT4 双副本场景也救不了 surge：2 副本已占满双卡，起新 Pod 仍需第 3 张卡——**只有集群存在真正空闲卡时 surge 才可行**（Day 5 任务 6 的 Pending 现场就是证明）
- 这就是"GPU 资源紧张时 maxSurge 怎么设"的答案：**先算清集群的 GPU 余量，再定策略——LLM 发版的可用性目标是"不断长请求"，而不是"副本数不减"**

### 动手任务（发版演练第一次）

1. **实测引擎 shutdown 行为（后续所有参数的前提）**：手动起一个 vllm 实例，压一条长输出请求，生成中途 `kill -TERM`，观察并记录：是否拒绝新请求（连接行为）、在途请求是否拿到末 token、SIGTERM 到退出用了几秒；同时 `vllm serve --help | grep -i -E 'timeout|shutdown'` 查可配项
2. chart 配好：`terminationGracePeriodSeconds: 180` + preStop sleep 10 + `maxSurge/maxUnavailable` 可配（数值依据任务 1 的实测微调）
3. 背景流量：M2 压测客户端持续打长输出请求（512 token，闭环并发 2）
4. 触发 `helm upgrade`（改一个无关参数如 annotation），完整记录：
   - 旧 Pod 从 SIGTERM 到消失的时间
   - 在途长请求是否成功收到最后一个 token（客户端日志为证）
   - 新请求是否有失败/超时窗口
   - preStop 与 SIGTERM 的先后（vLLM 收到信号的日志时间戳 vs preStop 时长——验证 kubelet "先 preStop 后 SIGTERM" 的实现，作为机制证据归档）
5. 反面实验：把 gracePeriod 调到 5s 重复一次——观察长请求被硬掐（客户端 `finish_reason` 异常/连接重置），归档对比
6. 资源两难实验：QA 用 1.5B 双副本（占满两张卡）跑 `maxSurge=1` vs `maxSurge=0,maxUnavailable=1`。**预期**：surge 组新 Pod 因 `Insufficient nvidia.com/gpu` 长期 Pending、滚动卡住——这正是"没有 GPU 余量不许 surge"的真实现场，把 Pending 事件归档
7. 全部记进 `release/发布演练记录.md`

### 当天验收

1. 说出发版不中断长请求的完整机制（preStop / 引擎 drain / gracePeriod 三段各管什么）
2. 没有 preStop 会发生什么？
3. GPU 集群 maxSurge 的决策依据是什么？
4. `terminationGracePeriodSeconds` 按什么算？

### 验收参考答案

#### 1. 三段机制的分工

> **preStop** 管"不再进新请求"：sleep 等 Endpoint 传播，Service 先摘端点、进程再开始 drain，避免 drain 期间新流量继续涌入导致永远清不完；**引擎 drain 行为** 管"在途请求跑完"：是否等待、等多久由本机版本的 shutdown 参数决定（Day 5 第一项任务就是实测确认）——若该版本不提供 drain，就必须靠"发版前排空长请求"的流程补位；**terminationGracePeriodSeconds** 管"最多等多久"：宽限期到就 SIGKILL，是 drain 的deadline。三者联动 = 新流量切断 → 存量跑完 → 兜底时限。验证标准只有一个：客户端侧每条长请求都完整收到末 token + DONE（Day 5 实验的验收项）。

#### 2. 没有 preStop 会怎样

> SIGTERM 时刻与"Service 完成端点摘除"之间有传播窗口（通常几秒）。没有 preStop 时，进程立刻开始 shutdown 并可能很快退出——这个窗口内仍被路由进来的新请求会直接撞上正在关闭的进程，得到连接拒绝。现象是每次发版都有一小撮 5xx/连接重置，数量不大但稳定出现，非常难排查（因为看服务端日志一切正常）。`preStop sleep` 就是用确定性等待覆盖这个不确定窗口——LLM 服务里它是必需品。

#### 3. maxSurge 的决策依据

> 唯一依据：**发版时刻集群的空闲 GPU 数**。`maxSurge=1` 需要临时多出 1 副本的 GPU（每副本 ≥1 卡）；有空闲 → surge 保可用性（新旧并行直到新就绪）；没有空闲 → 退到 `maxSurge=0, maxUnavailable=1`，接受发版窗口内容量下降，用 preStop+drain 保住"在途请求不断"作为底线。LLM 服务的特殊性在于 GPU 是独占整数资源、无法临时借用，且副本数本来就少（1~2 个），普通服务"多起一个副本"的常规操作在这里是真实的资源决策。生产建议：把 GPU 余量检查写进发布 SOP 的前置检查项。

#### 4. gracePeriod 怎么算

> 公式：`gracePeriod = preStop 睡眠 + 最长在途请求的剩余生成时间 + 引擎收尾 + 安全余量`。
> 代入本机：10s（preStop）+ 512 × 62ms ≈ 32s（max_tokens 上限 × **本服务实测的** TPOT p99）+ ~10s（收尾）≈ **52s 理论下限**；乘安全系数 1.5~2（TPOT 高峰漂移、kubelet 对宽限期的记账差异、调度抖动）→ 80~105s，**取整 120s**。
> 三个容易算错的点：① 52s → 120s 的跳变来自安全系数——它必须写在公式里，不能藏在结论里；② preStop 期间在途请求还在继续生成（Day 5 时间线：preStop 完成前不发 SIGTERM），10s 能推进约 160 token，公式不扣减这部分是**刻意保守**；③ TPOT 必须代入本服务实测值——62ms 是 7B FP16 TP=2 并发下的数字，换模型/换负载要重测，且注意 `terminationGracePeriodSeconds` 是否把 preStop 耗时计入宽限期随 K8s 版本有差异，按"总预算"口径设计在两种实现下都安全。drain 行为和真实时长由 Day 5 任务 1 直接实测、任务 4 在完整滚动中复核。反例（任务 5 的 5s 实验）：设短了等于宣布"超时请求一律杀"。它和 Day 4 的网关超时一样，是安全网：永远不该在正常流程中被触及，但必须足够长。

---

## Day 6：第一周整合——ArgoCD 接入与多环境成形

### 动手任务

1. chart 推 Git，写 `argocd/application.yaml`：`llm-qa` Application，syncPolicy automated + selfHeal，指向 `helm/vllm-inference` + `values-qa.yaml`
2. 完整 GitOps 回路验证：本地改 values → push → ArgoCD 自动同步 → 集群变化 → `argocd app diff` 空闲
3. 演练一次"配置漂移"：直接 `kubectl edit` 改镜像 tag，看 selfHeal 是否拉回——记录恢复时间
4. 多环境成形：staging Application（1.5B 或 AWQ + 严格探针），确认两环境互不干扰
5. **第一周复盘**：vllm-smoke 是否已迁移入 chart 管理（或保留为 M2 存档、明确标注）；两环境基线快照归档

### 第一周验收

- [ ] GitOps 全回路可用：push 即发布，漂移自动纠正
- [ ] 冷启动时间线有实测分解，探针预算有依据
- [ ] 发版演练：在途长请求在滚动更新中零中断（正面实验；注意 maxSurge=0 时新请求仍会有短暂失败窗口——这正是无 GPU 余量的代价）
- [ ] 反面实验数据归档（gracePeriod 不足、探针缺失的故障现场）
- [ ] 能脱稿讲清：探针三层、优雅下线三段机制（preStop / 引擎 drain / gracePeriod）、maxSurge 决策、权重分发四方案

---

# 第二周：伸缩、网关与发布体系

## Day 7：HPA 的正确姿势——为什么 CPU 利用率是无效指标

### 学习内容

大纲点名题：**为什么 CPU 利用率对 LLM 服务是无效指标？该用什么？**

CPU 利用率失效的原因链：

```text
LLM 推理的瓶颈在 GPU（KV Cache / 显存带宽 / 算力）
  ↓ CPU 只做 Tokenization / HTTP / 调度
  ↓ 单请求重 → GPU 已经过载排队（TTFT 爆炸）→ CPU 仍然闲着
  ↓ 按 CPU 扩容 = GPU 雪崩时无动于衷，流量低谷时瞎扩
```

候选指标对比（全部来自 M2 的指标体系）：

| 指标 | 来源 | 优点 | 缺点 |
|---|---|---|---|
| CPU 利用率 | kubelet | 现成 | **无效**，与推理负载基本不相关 |
| GPU 利用率 | DCGM | 现成（M6 部署） | 有欺骗性（M1/M2 反复证明），高≠过载低≠空闲 |
| **排队深度** `vllm:num_requests_waiting` | vLLM /metrics | **最直接**：有排队=过载 | 需 vLLM 暴露 + Prometheus 适配 |
| KV Cache 使用率 `gpu_cache_usage_perc` | vLLM /metrics | 容量视角，防 OOM | 高不一定是负载高（长上下文也推高） |
| TTFT p95 | vLLM /metrics | 用户视角 SLO 直读 | 采集聚合稍复杂 |

**推荐组合**：waiting 排队深度为主（触发扩容）+ KV Cache 水位为辅（容量保护）——两个都是 vLLM 原生 Prometheus 指标，M6 的监控体系正好复用。

### 动手任务

1. ServiceMonitor/PodMonitor 把 vLLM `/metrics` 接入 Day 0 装好的 kube-prometheus-stack（chart 增加 ServiceMonitor 模板）
2. 验证两条关键指标能查到：`vllm:num_requests_waiting`、`vllm:gpu_cache_usage_perc`（PromQL 手查）
3. 部署 HPA v2：基于 waiting 的 Pods 自定义指标（需要 Prometheus Adapter 或直接用 Prometheus 的 custom metrics 管道——按你集群现状选最小路径）
4. 压测验证：背景流量逐渐加压 → waiting 上升 → HPA 扩容 → 观察从"指标越线"到"新副本就绪接流量"的**总延迟**（这等于 HPA 的真实响应时间，冷启动在其中的占比会让你重新思考扩容策略）
5. 反面实验（可选）：同流量下换成 CPU 利用率 HPA，观察它毫无反应
6. 产出 `notes/hpa-metrics.md`：指标选型分析 + 实测扩容时延分解

### 当天验收

1. 为什么 CPU 利用率在这里是无效指标？故障场景推演一遍
2. 为什么 waiting 排队深度是最直接的扩容信号？
3. HPA 扩容的真实延迟由哪几段组成？这个事实怎么影响容量规划？

### 验收参考答案

#### 1. CPU 无效指标的推演

> 场景：流量洪峰，20 个并发长请求涌入。GPU 侧：KV Cache 打满、Decode 排队、TTFT 从 1s 涨到 30s——服务事实上已过载。CPU 侧：Tokenization 和 HTTP 收发是轻活，Tokenized 完就交给 GPU 队列，CPU 利用率可能只有 20%。基于 CPU 的 HPA 结论：负载健康，无需扩容。**指标测量的子系统（CPU）与发生拥塞的子系统（GPU 显存/带宽）完全脱节**，扩容决策自然失效。反过来 CPU 高 GPU 闲（比如客户端大量并发小 prompt，Tokenization 成为瓶颈）才是它唯一能捕获的场景——而这可以用更直接的指标（waiting/TTFT）覆盖。原则：HPA 指标必须测量"系统真正的稀缺资源"。

#### 2. waiting 为什么最直接

> 它直接就是过载的定义：调度器因为资源不足把请求放进等待队列，`vllm:num_requests_waiting > 0` = "当前副本数接不住当前流量"，语义上不需要任何换算。对比之下 GPU Util 高可能只是带宽等待（M1/M2），KV Cache 高可能只是长上下文请求占比高——都需要二次解释，唯独 waiting 是因果直连"流量 vs 容量"。配 SLO 化用法更好：waiting p95 持续 > 0 超过 N 分钟才扩，避免毛刺误扩。它还天然防误缩：waiting=0 且持续一段时间才缩，缩早了立刻有新请求排队。

#### 3. 扩容真实延迟的构成

> 指标越线（含采集/计算间隔，~30s+）→ HPA 决策 + Pod 创建（~10s）→ 镜像拉取（有缓存则秒级）→ **权重加载 + compile + CUDA Graph（分钟级，Day 3 实测）**→ 探针通过 → Endpoints 就绪接流量。总延迟以分钟计，其中冷启动占大头。影响：① HPA 对突发洪峰的缓冲能力有限——洪峰持续 1 分钟，扩容 3 分钟后才到，白扩；② 容量规划必须预留 headroom（在扩容生效前靠存量副本扛），HPA 是"追赶"不是"即时"；③ 要缩短响应，优化的重心在冷启动（Day 2/3 的权重分发与 compile 缓存），不在 HPA 参数本身。这也为 Day 8 KEDA 的预测式/事件驱动方案提供了动机。

---

## Day 8：KEDA 与缩容到零的两难

### 学习内容

大纲点名题：**缩容到零与冷启动的矛盾。**

KEDA 的定位：用外部事件/指标（而非 CPU 这种内置指标）驱动伸缩，支持 scale-to-zero：

```text
KEDA ScaledObject：监控指标源（如 Prometheus 查询 waiting）
  → minReplicaCount=0, maxReplicas=N
  → 无流量 → 副本缩到 0（GPU 释放，成本归零）
  → 新请求 → KEDA 先激活（0→1），再由 HPA 接管 1→N
```

矛盾的本质：

```text
缩容到零省的钱 = 空闲时段全部 GPU 成本
代价 = 冷启动时延直接转嫁给第一批用户（分钟级首请求）
```

解法光谱（面试答题框架）：

| 策略 | 延迟 | 成本 | 适用 |
|---|---|---|---|
| 永不缩到零（min=1） | 最优 | 最高 | 在线核心服务 |
| 缩到零 + 客户端重试排队 | 差 | 最优 | 异步/批处理 |
| 缩到零 + 常驻"预热代理"回 200 等待 | 可接受 | 极低 | 低频内部服务 |
| 定时伸缩（闲时 min=1 深夜 min=0） | 折中 | 折中 | 流量周期明显的业务 |

### 动手任务

1. 装 KEDA（helm，资源占用小），配 Prometheus scaler 监控一条合成指标（如 vLLM 请求速率或干脆用 cron scaler）
2. **scale-to-zero 完整实验**（用 1.5B，冷启动 ~40s 便于观察）：
   - 压测 → 扩到 2 副本 → 停流量 → 观察缩容时间线（stabilization window）
   - 副本归零后再打请求 → 记录"从请求发出到首 token"的总冷启动（秒表级数据进报告）
3. 实验缩容参数：`stabilizationWindowSeconds`（缩容稳定窗口）设太短的后果——用压测的间歇流量复现"扩缩振荡"（flapping）
4. 结论写进 `notes/hpa-metrics.md`：什么业务形态适合缩到零、KEDA 与 HPA 的分工

### 当天验收

1. KEDA 相比 HPA 多解决了什么？
2. 缩到零的完整代价链是什么？什么业务能接受？
3. 扩缩振荡怎么发生、怎么防？

### 验收参考答案

#### 1. KEDA 相比 HPA 多了什么

> 三件事：① 指标源从 K8s 内置（CPU/内存）扩展到任意外部系统（Prometheus、Kafka、队列长度），LLM 场景里 waiting/TTFT 这类业务指标才能成为伸缩依据（HPA 原生只认 metrics-server 和自定义指标管道，接外部源很别扭）；② 原生 scale-to-zero：HPA 的 0 副本是无法从指标激活的死状态，KEDA 的 ScaledObject 负责 0→1 激活再移交 HPA 逻辑管 1→N；③ ScaledObject 的伸缩策略更丰富（稳定窗口、缩容策略、定时），对"缩容要慢、扩容要快"的不对称性支持更好。分工总结：**KEDA 管边界（0↔1 和指标接入），HPA 管中间（1→N）**，两者不是替代关系。

#### 2. 缩到零的代价链

> 请求到达 → KEDA 检测激活（一个 scaler 轮询周期）→ Pod 调度 + 镜像拉取 + 权重加载 + compile + CUDA Graph + 探针通过（Day 3 实测的分钟级冷启动）→ 首 token。等于把"服务器冷启动"原样暴露给用户，而且 GPU 释放后重建无任何状态可复用。能接受的业务形态：内部工具、低频批处理、开发测试环境——用户预期宽松或本身就是异步的；不能接受的：任何 SLA 承诺首响的在线服务。中间态解法是"常驻轻代理"：网关层接住请求返回排队语义，后台触发激活——用户等但不是无响应地等。

#### 3. 扩缩振荡

> 成因：缩容稳定窗口 < 流量波动周期。流量间歇（比如每 2 分钟一波）：副本缩下来 → 下一波到 → 又扩上去 → 无限循环。每次振荡都付出一次冷启动 + 一次 drain 的代价，GPU 反而更忙、用户体验更差，比不伸缩还糟。防线：① `stabilizationWindowSeconds` 覆盖业务流量的自然波动周期（观察历史再定，宁长勿短，300s 起步）；② 缩容步长限制（一次只缩 1 个）；③ 扩容快缩容慢的不对称策略；④ 定性判断：如果流量本身是持续小幅波动的，干脆 min=1 不折腾——**伸缩系统的第一原则是别制造比不伸缩更糟的状态**。

---

## Day 9：多模型管理与 LiteLLM 网关

### 学习内容

单模型服务的运维已经解决（第一周），平台化第一步是把"多模型"管起来——4.4 的三件事：

1. **LiteLLM**：统一 OpenAI 兼容网关
   - 一个入口路由到多个后端（chart 部署的 vLLM、外部 API、不同模型）
   - 按 token 限流/配额（M1 Day 1 + Day 4 的三层防护在这里落地）
   - 虚拟模型名映射（业务见 `gpt-4o-proxy`，后端实际是自部署 qwen——解耦业务与模型实现）
   - 成本归因：per-key/per-team 的 token 用量记账（M6 成本治理的地基）
2. **KServe / Seldon 的 InferenceService 抽象**：KServe（predictor / transformer / explainer、canaryRollout）与 Seldon 的对应概念，判断"chart 直部署 vs 推理平台"的适用边界——多副本单模型的在线服务 chart 更直接可控；异构多模型平台化才需要 KServe 这类抽象
3. **金丝雀/A-B**：KServe 的 canary 按流量百分比切分；chart 路线的等价做法 = 两个 Deployment + 网关按权重或模型别名路由
4. **多租户隔离**：K8s 层是 namespace + ResourceQuota + NetworkPolicy；模型服务还要多一层业务隔离——网关 per-key 的 token 配额。另需评估 Prefix Caching 跨租户共享前缀的隔离风险（M2 Day 6 已提，生产必须明确策略）

### 动手任务

1. helm 部署 LiteLLM，config 映射两个后端（注意：虚拟 key / per-key 配额 / spend 记账都依赖数据库，最小路径是带 Postgres；只验证路由行为可先用 master key）：
   - `qwen-7b-int4` → 本集群 chart 服务
   - `qwen-1.5b` → vllm-smoke（或另一个命名空间的实例）
2. 验证：同一网关地址下按 model 字段路由到不同后端；一个后端下线时网关的错误行为与 fallback 配置
3. 配置 per-key 限流（TPM/RPM）与虚拟模型映射，压测触发限流验证 429 行为
4. 可选进阶：LiteLLM 的 fallback 配置实现"自部署模型超时 → 降级到小模型"的最小演示
5. `notes/` 写选型结论：什么规模之前 chart+LiteLLM 够用，什么时候需要 KServe——结合 M5 的平台化方向

### 当天验收

1. 网关层解决了哪些"单模型服务解决不了"的问题？
2. 为什么限流必须在网关层做而不是各模型服务自己做？
3. KServe 什么时候才值得引入？

### 验收参考答案

#### 1. 网关层解决什么

> ① 统一入口与模型路由：客户端不感知后端拓扑，模型增删/换实现不动业务代码（虚拟模型名解耦）；② 跨模型的统一治理：限流、配额、鉴权在唯一入口执行，而不是 N 个服务各配一套还会配漏；③ 成本归因：所有流量过网关，per-key/per-team 的 token 记账天然完整——这是 M6 成本治理的数据来源；④ 高级行为：fallback 降级（主力模型超时切备选）、A/B 路由（双模型别名或部署权重切版本）、语义缓存的接入点。一句话：**网关是"把 N 个模型服务变成 1 个平台"的那层抽象**，M5 的推理路由（prefix-cache 感知、负载感知）也是在这层上演进。

#### 2. 限流为什么在网关层

> 三个理由：① 完整性——限流要按"调用方"计而不是按"服务"计，同一个租户可能打多个模型，只有网关看得见全量流量；② 一致性——TPM/RPM 语义、429 响应格式、超配行为全平台统一，客户端实现一次到处能用；③ 防护位置——限流的意义是在流量打到 GPU 之前拒绝，网关是流量入口的最后一道闸；各服务自己限，过载的排队/显存压力已经发生了。补充：网关限流与单服务内的 `max-num-seqs`/`max-model-len` 是两层不同的防线——网关管"谁准进来多少"，服务参数管"进来的怎么被消化"，缺一不可。

#### 3. KServe 的引入时机

> KServe 的价值在 InferenceService 抽象 + 标准化 rollout + 自动缩放，代价是一层抽象的学习/调试成本和灵活性的损失。单模型或少量模型的在线推理：chart 直部署更简单、可控性强（探针/滚动/参数全是你的）——本机场景就是。值得引入的信号：① 模型数量多且异构（不同框架、批处理/在线混合）；② 数据科学团队需要自助发布模型而平台要管标准；③ 需要 KServe 生态的 transformer/explainer 或 canary 等原生能力。判断句式（面试用）：**KServe 是"平台规模化后降低 N 个模型的边际运维成本"的工具——N 还小、形态还单一时，它的抽象成本大于收益**。与 M5 的衔接：真到平台化阶段，llm-d/AIBrix 这类推理原生方案也是候选。

---

## Day 10：金丝雀发布与版本管理

### 学习内容

模型发布的特殊性：**"版本"不只是镜像/参数，还包括权重本身**——一次模型更新可能同时变：镜像（vLLM 版本）、权重（Qwen2.5 → Qwen3）、参数（max-model-len 调整）。回滚语义因此复杂：Git 回滚 chart 只回滚了编排，权重如果是 initContainer 下载的还要确认缓存命中旧版本。

金丝雀的实现选择（资源受限现实下）：

```text
标准做法（KServe canary / Argo Rollouts）：
  两个版本并行 → 按流量比例切分 → 观察指标 → 全量 or 回滚

本机可行做法（双副本 1.5B）：
  v1 Deployment + v2 Deployment（各占一卡）
  LiteLLM 网关按部署权重（9:1）或双模型别名切流（金丝雀组 10% 流量）
  观察窗口：TTFT/TPOT/错误率/输出质量抽检
```

### 动手任务

1. 准备两个"版本"：同一 chart，不同 values（如 1.5B FP16 vs 1.5B AWQ——正好把 M2 的量化对照变成发布演练素材）
2. 切流方案二选一，先搞清 LiteLLM 的能力边界：
   - **比例切流（内置）**：v1/v2 注册为同一模型组下的两个 deployment，配 `weight`（9:1）做加权随机——最接近"10% 金丝雀"
   - **精确切流（需两个模型名）**：`qwen-1.5b` 与 `qwen-1.5b-canary` 两个别名，由调用方或轻量 wrapper 按 header/租户选择——LiteLLM 没有内置的 header→deployment 映射
3. 压测同时打两组，对比金丝雀窗口内的：TTFT/TPOT p95、错误率、（质量抽检用 M2 的固定题集）
4. 演练一次"金丝雀指标不合格 → 回滚 v2"：Git revert → ArgoCD 同步 → 确认 v2 资源释放
5. 发布记录进 `release/`：含决策点（观察几分钟、看什么指标、谁拍板）

### 当天验收

1. 模型发布的回滚和普通应用回滚差在哪？
2. 金丝雀观察窗口该看什么指标？质量指标为什么不能省？
3. 金丝雀比例切流的两个实现层次（实例级 vs 网关级）各适合什么？

### 验收参考答案

#### 1. 模型回滚的特殊性

> 普通应用回滚 = 回滚镜像/配置，秒级完成且行为确定。模型回滚多一个维度：**权重版本**。chart 在 Git 里回滚了，但权重获取路径（PVC 内容/initContainer 下载的 revision）可能仍是新版——出现"编排是 v1、权重是 v2"的撕裂状态，比单纯的失败更危险（表现为难以解释的输出质量漂移）。防线：① 权重版本显式化——model revision 写进 values 并随 Git 管理，回滚即同时回滚权重引用；② 权重不可变策略——PVC/缓存按 revision 目录隔离，不用"同名覆盖"；③ 回滚演练必须验证"输出内容回到旧行为"（打固定题集比对），而不是只看 Pod 版本号。这是 LLM 发布 SOP 与普通 SOP 的最大差异点。

#### 2. 观察窗口的指标集

> 四类缺一不可：① 性能——TTFT/TPOT p95 对比基线（性能回退的量化版本 M2 已练熟）；② 稳定性——错误率、重启、探针翻转、KV Cache 抢占；③ **质量——固定题集抽检**（M2 Day 13 的题集直接复用）：新版本可能有质量回退但性能指标全绿（尤其量化/新版本模型），没有质量抽检的金丝雀是盲的；④ 成本——tokens/请求、显存占用是否漂移。窗口时长：至少覆盖一个完整流量周期（含波峰），几分钟的窗口只能抓崩溃级故障，抓不住质量漂移。这也是"质量门槛前置"原则（M2 Day 13）在发布流程中的落地。

#### 3. 两级切流的适用

> **实例级**（两个 Service/Ingress 权重、Argo Rollouts）：切流粒度是连接/请求的百分比，无需改造应用，适合所有流量同质、按比例抽样即可的场景——但 SSE 长连接下"按连接切"可能整条长会话进金丝雀，样本有偏。**网关级**（LiteLLM 按模型别名 / 部署权重路由）：用两个模型名 + 权重，可以按"调用方/租户/业务"精确切或按比例切——特定团队自愿尝鲜、特定低风险业务先上，样本语义清晰可控，还能让金丝雀组自带标记便于对比分析。实践建议：小规模用网关级（本 Day 实验做法），流量大且同质时用实例级自动比例切分；两者都能满足时优先网关级，因为它给了你"谁参与灰度"的控制权，而不只是"多少流量参与"。

---

## Day 11：发布 SOP 定稿

### 动手任务

把两周的所有实践沉淀为《LLM 服务发布 SOP》，结构：

```text
1. 前置检查
   - GPU 余量（决定 maxSurge 策略）
   - 权重缓存命中确认（revision 校验）
   - 镜像 digest 固定
   - ArgoCD 无 in-progress 同步
2. 发布顺序
   - Git merge → ArgoCD 同步 QA → 冒烟（含预热流量）
   → 指标观察窗口 → staging 演练（含金丝雀，必要时）
   → 生产 values → 同步 → 预热 → 观察
3. 观察清单（每个环境的检查项与时长）
   - TTFT/TPOT p95、错误率、waiting、KV 水位、输出质量抽检
4. 回滚流程
   - 触发条件（哪些指标越线即回滚）
   - Git revert → 同步 → 权重版本验证 → 题集比对
   - 回滚后的根因记录流程
5. 禁止事项
   - 严禁绕过 GitOps 直接 kubectl 改生产
   - 严禁在无 GPU 余量时使用 surge 策略
   - 严禁不带质量抽检的金丝雀全量
```

1. 用这套 SOP 完整走一次"模拟生产发布"（staging 环境当生产）：全流程计时，记录每步耗时
2. 请自己扮演"值班同学"：拿着 SOP 只看文档执行一遍——文档里写不清的地方就是 SOP 的缺陷，迭代
3. SOP 里补一节"故障联动"：发布过程中发现 Xid / 掉卡（M3 排查手册）时的暂停与升级路径

### 当天验收

- [ ] SOP 可被不了解细节的人照做
- [ ] 回滚演练完整跑通（含权重版本验证）
- [ ] 前置检查、观察清单、禁止事项三节都有本机实验数据支撑（标注出自哪一天的哪个实验）

---

## Day 12：M4 总验收

### 综合演练（一次完整故障注入）

模拟值班最糟的一天，全链路处置：

1. 背景流量运行中，注入故障：kill 掉一个副本的引擎进程（模拟 GPU hang）
2. 验证全链条：真实推理 readiness 摘流量 → 存活副本承接流量（waiting 上升）→ HPA/KEDA 尝试扩容（GPU 不足时分两步观察：Pending 事件 + 告警）→ 进程/容器退出触发重启（**由 liveness 与 Deployment 控制器负责，不是 ArgoCD**）→ 冷启动 + 预热 → 恢复
3. 记录从注入到完全恢复的时间线，与 SOP 对照找差距
4. 复盘：哪一层如果配置错了，故障会扩大而不是自愈（探针、gracePeriod、发布策略三处各举一例——第一周的反面实验数据在这里用）。同时明确职责边界：**ArgoCD 修的是配置漂移，liveness/Deployment 修的是进程死亡，两者不能互相替代**

### 最终自测题（脱稿回答）

- [ ] LLM 服务的 chart 与普通服务 chart 有哪四个先天差异？
- [ ] 四种权重分发方案怎么选？和 HPA 响应速度什么关系？
- [ ] startupProbe / readinessProbe / livenessProbe 在 LLM 场景各自的预算依据和设计原则？
- [ ] readiness 为什么必须打真实推理？/health 会漏什么？
- [ ] 发版不中断长请求的三段机制（preStop / 引擎 drain / gracePeriod）各管什么？
- [ ] GPU 集群滚动更新时 maxSurge 的决策依据？
- [ ] terminationGracePeriodSeconds 按什么公式估算？
- [ ] SSE 流式流量对网关的要求？用户"答到一半停了"怎么分层排查？
- [ ] 为什么 CPU 利用率是无效伸缩指标？推荐什么指标组合？
- [ ] HPA 扩容的真实延迟构成？对容量规划的含义？
- [ ] 缩容到零的代价链？什么业务能接受？扩缩振荡怎么防？
- [ ] KEDA 和 HPA 的分工边界？
- [ ] 模型网关层解决哪些单服务解决不了的问题？
- [ ] 限流为什么必须在网关层？TPM/RPM 怎么落地？
- [ ] 模型回滚与普通应用回滚的本质差异？（权重维度）
- [ ] 金丝雀观察窗口的四类指标？质量抽检为什么不能省？
- [ ] 什么时候该引入 KServe 而不是继续用 chart？

---

# 四、最终产出物

## 1. `helm/vllm-inference/` 多环境 chart

- [ ] templates：Deployment（探针三层 + preStop + gracePeriod）/ Service / ConfigMap / Ingress / HPA 可选模板
- [ ] values 四件套（base/qa/staging/prod），容量参数带 M2 实测注释
- [ ] 权重分发可切换（PVC / initContainer 预热）
- [ ] ArgoCD Application 管理，selfHeal 验证过
- [ ] `helm template` 渲染 diff 与 M2 手写 manifest 对比无回退

## 2. 《LLM 服务发布 SOP》

- [ ] 前置检查 / 发布顺序 / 观察清单 / 回滚流程 / 禁止事项五节
- [ ] 金丝雀与回滚有完整演练记录
- [ ] 故障联动（M3 排查手册的引用）
- [ ] "陌生值班同学可照做"验证通过

## 3. 实验记录（`release/` + `notes/`）

- [ ] 冷启动时间线分解（实测）
- [ ] 权重分发三方案启动耗时对比
- [ ] 优雅下线正反面实验（零中断 vs 硬掐）
- [ ] maxSurge 两难对照
- [ ] HPA 指标选型分析 + 扩容时延分解
- [ ] scale-to-zero 冷启动实测 + 振荡复现
- [ ] LiteLLM 路由/限流/fallback 验证记录
- [ ] 金丝雀按权重/双模型别名切流实验

---

# 五、学习资源

| 资源 | 用法 | 优先级 |
|---|---|---|
| vLLM 官方文档 · Serving（探针/生产部署建议） | 探针与部署参数核对 | 最高 |
| Kubernetes Probe 官方文档 | startup/readiness/liveness 语义 | 最高 |
| Kubernetes HPA 官方文档（含自定义指标） | HPA v2 语义与行为 | 高 |
| KEDA 官方文档 | ScaledObject/scale-to-zero | 高 |
| LiteLLM 官方文档（proxy/router/config） | 网关配置与限流 | 高 |
| ArgoCD 官方文档（你已熟，按需查） | selfHeal/sync 策略 | 中 |
| KServe 官方文档 | InferenceService 抽象、canary | 中 |
| Argo Rollouts 文档（概念了解） | 高级渐进交付的工业做法 | 低 |
| jimmysong.io kubernetes-handbook · AI Native | 中文实践参考 | 中 |

---

# 六、明确取舍与避坑

M4 必须深入（LLM 特有的部分）：

- 探针三层设计与真实推理探活
- 冷启动分解与治理
- 优雅下线三段机制（preStop / 引擎 drain / gracePeriod）、GPU 约束下的滚动策略
- SSE 流量的网关要求与排障
- GPU 感知的伸缩指标、scale-to-zero 取舍
- 模型发布的回滚语义（权重维度）、金丝雀质量门槛

M4 直接复用、不重新学（你的存量能力）：

- Helm 模板语法、values 组织
- ArgoCD Application/syncPolicy/selfHeal
- Service/Ingress 基础接线
- Prometheus 基础（只补 vLLM 指标接入）

M4 只做概念了解：

- KServe 完整功能面（选型判断即可，M5 再评估）
- Argo Rollouts（知道工业方案存在，资源内用 LiteLLM 实现）
- 语义缓存/GPTCache（M6 成本治理再碰）

常见误区：

1. **readiness 用 /health 就上线**——GPU 卡死时故障副本继续接流量（M2 Day 2 实证的直接后果）
2. **liveness 套普通服务的阈值**——误杀 = 冷启动重来 + 长请求全断，故障放大器
3. **terminationGracePeriodSeconds 默认 30s 不改**——32s 的长输出请求必被硬掐
4. **maxSurge 想当然设 1**——没有 GPU 余量时滚动直接卡死
5. **HPA 用 CPU**——测量不到真实瓶颈，扩缩全靠运气
6. **stabilization window 随手设短**——扩缩振荡比不伸缩更糟
7. **金丝雀只看性能指标**——质量回退在性能面板上是隐形的
8. **回滚只回滚 chart 不管权重**——"编排 v1 + 权重 v2"的撕裂状态
9. **把 M4 恋战成四周**——通用部分对你不是新知识，纪律：两周必须收官，富余时间投给 M6

判断标准：

> 每个实践都问一句：这件事普通无状态服务也要做吗？——是，就快速过；只有 LLM 特有的才值得花你的两小时。

---

M4 完成后进入 M5（GPU 调度与平台化）：本机的独占分配实验、标签污点体系、LiteLLM 网关全部直接复用——HAMi 一卡多服务、Volcano 批调度、负载感知路由都建在这套地基上。
