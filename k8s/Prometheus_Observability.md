# Prometheus 全链路可观测性指南（面试版）

> 本文档覆盖从指标暴露、采集、存储、可视化到告警通知的完整链路，
> 与 `K8s_Advanced.md` 第十九章（安装/PromQL）和第二十八章（ServiceMonitor）互补，
> 侧重**架构原理、数据流转细节、面试高频场景和全链路串联**。

---

## 术语速查表

> 面试中需要准确使用术语。以下按数据流转顺序排列核心概念。

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **Metric** | 指标 | 带时间戳的数值数据，描述系统的某个可测量属性（如 QPS、延迟、CPU 使用率） |
| **Time Series** | 时间序列 | 同一个指标 + 同一组标签组成的数据流。如 `http_requests_total{method="GET", status="200"}` 是一条时间序列 |
| **Label** | 标签 | 键值对元数据，用于区分时间序列的维度。如 `method="GET"`, `status="200"` |
| **Sample** | 样本点 | 时间序列中的一个数据点，由 `(timestamp, value)` 组成 |
| **Cardinality** | 基数 | 时间序列的总数量。高基数（如用 user_id 做标签）会导致性能问题 |
| **Exposition Format** | 暴露格式 | Prometheus 定义的纯文本指标格式，`/metrics` 端点返回的内容，人类可读、逐行解析 |
| **Scrape** | 采集/抓取 | Prometheus 通过 HTTP GET 拉取 `/metrics` 端点的行为。上游默认 `scrape_interval` 通常为 1m，实际部署可按场景覆盖 |
| **Target** | 采集目标 | 被 Prometheus 采集的端点。K8s 中一个 Pod 的 `/metrics` 端点就是一个 Target |
| **Service Discovery (SD)** | 服务发现 | 自动发现 Target 的机制。K8s SD 通过 API Server 发现 Pod/Service/Endpoint |
| **TSDB** | Time Series Database | Prometheus 时序数据库，由 WAL、当前可变 Head 与不可变 Disk Block 组成 |
| **WAL** | Write-Ahead Log | 记录 Head 中尚未形成磁盘 Block 的数据，用于进程崩溃后的重放；不能覆盖磁盘/WAL 损坏等故障 |
| **Recording Rule** | 记录规则 | 预计算并存储聚合结果的规则，加速 Grafana 查询、降低 PromQL 计算量 |
| **Alerting Rule** | 告警规则 | 定义触发告警条件的规则，Prometheus 定时评估并将触发的告警推送给 Alertmanager |
| **Alertmanager** | 告警管理器 | 独立的告警处理服务，负责去重、分组、抑制、静默、路由告警到通知渠道 |
| **remote_write** | 远程写入 | 将样本发送给 Thanos Receive、Mimir/Cortex、VictoriaMetrics 等远端接收端的协议；Thanos Sidecar 模式不使用它上传 Block |
| **relabel** | 标签重写 | 在采集前/存储前对 Target 标签进行增删改的机制。控制"采集谁"和"叫什么名" |
| **metric_relabel** | 指标标签重写 | 在存储前对已采集的指标标签进行增删改的机制。控制"存什么"和"丢弃什么" |

---

## 第一章 全链路架构：从代码到面板的完整数据流

> **面试官最常问的开场白**："请描述一下 Prometheus 从采集到报警的完整数据流"
> 以下是从应用代码打点 → 最终在 Grafana 看到图表并在企业微信收到告警的完整过程。

### 0 端到端数据流转全景图

```
时间线：从业务代码打点到收到告警的完整流转

┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 1: 指标暴露（应用侧）                                               │
│                                                                          │
│  业务代码 ──Counter.Inc()──▶ client library ──HTTP /metrics──▶ 外部可见    │
│  (Go/Python/Java)          (promhttp/prometheus_client)   (纯文本格式)     │
│                                                                          │
│  输出示例：                                                                │
│  # HELP http_requests_total Total HTTP requests                          │
│  # TYPE http_requests_total counter                                      │
│  http_requests_total{method="GET",status="200"} 152347 1715678900000         │
│  http_requests_total{method="POST",status="201"} 89231 1715678900000         │
│                                                                          │
│  关键点：每个数据行 = 指标名 + {标签} + 值 + 时间戳（可选）                  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 2: 服务发现（Prometheus 侧）                                        │
│                                                                          │
│  Service Discovery ──API Server──▶ 发现 Pod/Service/Endpoint              │
│  (kubernetes_sd_configs)          (List & Watch)                         │
│                                                                          │
│  K8s SD 自动发现链路：                                                      │
│  ServiceMonitor.spec.selector → Service.labels → EndpointSlice            │
│  → 从 EndpointSlice 地址与端口生成 Target                                  │
│  普通 selector-backed Service 的 EndpointSlice 通常由 Pod 状态维护           │
│                                                                          │
│  对每个 Target 应用 relabel_configs：                                       │
│    原始标签：__meta_kubernetes_pod_ip, __meta_kubernetes_pod_name...       │
│    relabel 后：job="my-app", instance="10.0.1.5:8080", namespace="prod"   │
│                                                                          │
│  relabel 后的 Target 进入 Scrape 队列                                       │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 3: 数据采集（Scrape 生命周期 — 由 Retrieval 模块执行）                │
│                                                                          │
│  每 scrape_interval 秒（上游默认通常为 1m），Retrieval 模块对每个 Target：   │
│                                                                          │
│  Step 1: Retrieval ──HTTP GET──▶ http://<pod-ip>:9090/metrics            │
│  Step 2: 解析 text 格式，逐行转换为 (metric_name, labels, value, timestamp) │
│  Step 3: 样本未提供时间戳时使用抓取时间；显式时间戳由 honor_timestamps 控制    │
│  Step 4: 追加写入 WAL，并将样本加入 Head                                   │
│  Step 5: Head 数据周期性切块并持久化为 Disk Block                           │
│                                                                          │
│  时序与失效语义：                                                           │
│  - scrape 失败会将 Target 标记为 DOWN，并在当前抓取中写入 up=0               │
│  - 目标持续存在但抓取失败，与目标从服务发现中消失的 stale marker 时机不同       │
│  - 无 stale marker 时，查询引擎使用约 5m lookback 作为兜底                    │
│  - Rules 由 evaluation_interval 或 rule group interval 独立调度             │
│  - WAL 用于崩溃恢复，但仍需关注磁盘损坏、保留窗口和远程写积压边界                │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 4: 数据存储（TSDB 三层架构）                                         │
│                                                                          │
│  ┌──────────┐    ┌────────────────────┐    ┌──────────────────┐          │
│  │   WAL    │───▶│ Head（当前可变数据区）│───▶│ Disk Block      │          │
│  │ 磁盘日志  │    │ 活跃结构在内存；部分 │    │ 不可变磁盘块      │          │
│  │ 崩溃重放  │    │ chunks_head 可 mmap │    │                  │          │
│  └──────────┘    └────────────────────┘    └──────────────────┘          │
│                                                                          │
│  压缩策略：Head 通常按约 2h 生成初始 Block，Compactor 再合并相邻 Block；       │
│  合并层级和最大时间范围由实现与 retention 决定，不是固定 2h→6h→24h            │
│  目的：减少文件数 + 降低查询时需要扫描的块数量                                │
│  超出配置的 retention time/size 后删除旧块；上游常见默认时间为 15d，但 Chart 可覆盖 │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 5: 查询（PromQL → Grafana）                                         │
│                                                                          │
│  Grafana Panel ──PromQL──▶ Prometheus HTTP API ──查询──▶ TSDB             │
│                                                                          │
│  API 路径：                                                               │
│  - GET /api/v1/query?query=<promql>           # 即时查询（Instant）       │
│  - GET /api/v1/query_range?query=<promql>&start=&end=&step=  # 范围查询  │
│                                                                          │
│  Grafana 渲染：                                                            │
│  收到 JSON 数据 → 按 legendFormat 分系列 → 根据面板类型绘制图表/表格/Stat   │
│  通过 $__interval 变量自动适配 step 间隔                                   │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 6: 告警（Alerting Rule → AlertManager → 通知）                       │
│                                                                          │
│  Alerting Rule 评估 ──触发──▶ AlertManager ──路由──▶ 企业微信/钉钉/PagerDuty│
│                                                                          │
│  Alert 生命周期：                                                          │
│  Pending（满足条件但未超过 for）→ Firing（超过 for 且持续满足）→ Resolved   │
│                                                                          │
│  AlertManager 处理流程：                                                    │
│  接收 Firing Alert → 分组（group_by）→ 等待（group_wait）→ 抑制检查        │
│  → 重复间隔控制（repeat_interval）→ 路由到接收器 → 发送通知                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**面试速记口诀**：

```
六步走完一条线：
① 代码打点暴露 /metrics
② K8s SD 自动发现 Target
③ Retrieval 模块 HTTP 拉取 → 解析 → 通过 TSDB appender 写入 Head 并记录 WAL
④ Head 按时间窗口切成不可变磁盘 Block，后续由 Compactor 合并
⑤ PromQL 查询（HTTP Server）→ Grafana 可视化
⑥ Alerting 模块评估规则 → AlertManager → 通知渠道
```

**面试常被追问的"Prometheus 内部有哪些模块"**：

```
核心五件套（Prometheus Server 内部）：
  1. Service Discovery  ← 发现 Target（外部依赖，但常被算进来）
  2. Retrieval           ← 拉取 /metrics（HTTP GET + 解析 + relabel）
  3. TSDB                ← 存储（WAL + Head Block + Disk Block）
  4. Rules               ← 评估 Recording/Alerting Rule
  5. Alerting            ← 告警生成（推给 Alertmanager）

配套模块（也是 Prometheus Server 内部）：
  6. HTTP Server         ← 暴露 PromQL/UI/API
  7. Remote Read/Write   ← 远程存储交互

独立服务（不是 Prometheus 内部）：
  Alertmanager           ← 独立的告警处理服务
```

### 1 可观测性三大支柱

```
┌─────────────────────────────────────────────────────────────────────┐
│                        可观测性三大支柱                               │
│                                                                     │
│   Metrics（指标）         Logging（日志）          Tracing（追踪）    │
│   Prometheus + Grafana    Loki + Grafana          Jaeger / Tempo    │
│   ─────────────────       ─────────────           ─────────────     │
│   数值/时序                文本/上下文              请求/调用链       │
│                                                                     │
│   核心链路:                                                          │
│                                                                     │
│   ┌──────────┐    ┌──────────────┐    ┌───────────┐               │
│   │ 应用导出  │───▶│ Prometheus   │───▶│  Grafana   │  可视化       │
│   │ /metrics  │    │ 采集 + 存储   │    │  仪表盘     │              │
│   └──────────┘    └──────┬───────┘    └───────────┘               │
│                          │                                          │
│                     ┌────▼──────┐     ┌──────────────┐             │
│                     │ AlertManager│───▶│ 企业微信/钉钉 │  告警通知    │
│                     └────────────┘     │ Slack/PagerDuty│           │
│                                        └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

### 2 Prometheus 整体架构与组件详解

> 这是面试时被问"Prometheus 内部结构"的标准答案。

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Prometheus 整体架构                              │
│                                                                      │
│  ┌─────────────────────┐                                             │
│  │  Service Discovery  │ Kubernetes / Consul / DNS / File SD / EC2   │
│  └──────────┬──────────┘                                             │
│             │ 发现 targets                                            │
│             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Prometheus Server                            │   │
│  │                                                              │   │
│  │  ┌────────────┐ ┌────────┐ ┌────────┐ ┌────────────┐          │   │
│  │  │ Retrieval  │ │ TSDB   │ │ Rules  │ │ Alerting   │          │   │
│  │  │ (拉取模块)  │ │(时序存储)│ │(规则引擎)│ │(告警生成)   │          │   │
│  │  └─────┬──────┘ └───┬────┘ └───┬────┘ └─────┬──────┘          │   │
│  │        │             │          │             │                 │   │
│  │        ▼             ▼          ▼             ▼ 告警            │   │
│  │  ┌──────────────────────────────────────────┐                 │   │
│  │  │  WAL + Head（可变数据区）→ 不可变 Disk Block │                 │   │
│  │  └──────────────────────────────────────────┘                 │   │
│  │                                                              │   │
│  │  ┌──────────────┐  ┌─────────────────┐                       │   │
│  │  │ HTTP Server  │  │ Remote Read     │                       │   │
│  │  │ (PromQL/UI)  │  │ Remote Write    │                       │   │
│  │  └──────┬───────┘  └─────────────────┘                       │   │
│  └─────────┼────────────────────────────────────────────────────┘   │
│            │ PromQL 查询           │ 长期存储上传                    │
└────────────┼───────────────────────┼──────────────────────────────┘
             │                       │
             ▼                       ▼
   ┌─────────────────────┐    ┌────────────────────────┐
   │  Grafana / API      │    │ 长期存储: Thanos /      │
   │  (可视化查询)        │    │ Cortex / Mimir /       │
   │                     │    │ VictoriaMetrics        │
   └─────────────────────┘    └────────────────────────┘

                   ┌─────────────────────────────┐
                   │      Alertmanager            │
                   │      (告警管理)              │
                   │  - 去重 / 分组 / 抑制 / 路由  │
                   └──────────────┬──────────────┘
                                  │ 通知
                                  ▼
                Email / PagerDuty / 企业微信 / Webhook
```

#### 核心组件详解

| 组件 | 所在层 | 核心职责 | 关键实现 |
|------|--------|----------|----------|
| **Service Discovery** | 外部依赖 | 自动发现监控目标 | `kubernetes_sd_configs` 调 API Server |
| **Retrieval**（拉取模块） | Prometheus 内部 | 主动 HTTP GET 拉取 `/metrics` | scrape 池 + 协程并发 |
| **TSDB** | Prometheus 内部 | 存储样本点 | WAL + 当前可变 Head + 不可变 Disk Block |
| **Rules**（规则引擎） | Prometheus 内部 | 评估 Recording/Alerting Rule | 按全局 `evaluation_interval` 或 Rule Group 的 `interval` 独立调度 |
| **Alerting**（告警生成） | Prometheus 内部 | 将触发的告警推给 Alertmanager | 状态机：Pending → Firing |
| **HTTP Server** | Prometheus 内部 | 对外暴露 PromQL + Web UI | `/api/v1/query`, `/api/v1/query_range` |
| **Remote Read/Write** | Prometheus 内部 | 与外部存储交互 | 把数据推出去（Write）/ 拉过来（Read） |
| **Alertmanager** | **独立服务**（非 Prometheus 内部） | 告警去重、分组、抑制、路由 | 与 Prometheus Server 分开部署 |

> **重要区分**：
> - **Alerting**（Prometheus 内部模块）只负责**生成**告警并推给 Alertmanager
> - **Alertmanager**（独立服务）负责**接收 + 处理**告警（去重、分组、抑制、路由）
> - 面试时不要混淆：Alerting 是 Prometheus 的"告警生产者"，Alertmanager 是"告警管理者"

#### Retrieval 拉取模块详解（最容易忽略的组件）

```
Retrieval 是 Prometheus 最核心的模块之一，负责所有的数据采集工作：

┌─────────────────────────────────────────────────────────┐
│                  Retrieval 拉取模块                      │
│                                                         │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐     │
│  │ Scrape Pool│    │  HTTP 客户端 │    │ 解析器      │     │
│  │ (目标管理)  │───▶│ (HTTP GET)  │───▶│(text→样本)  │     │
│  └────────────┘    └────────────┘    └────────────┘     │
│         │                                     │          │
│         │          ┌──────────────┐           │          │
│         │          │ Relabel 引擎 │           │          │
│         │          │ (标签处理)    │           │          │
│         │          └──────┬───────┘           │          │
│         │                 │                   │          │
│         └─────────────────┴───────────────────┘          │
│                           │                              │
│                           ▼                              │
│                   TSDB append 队列                       │
└─────────────────────────────────────────────────────────┘

核心职责：
1. 维护 Scrape Pool：管理所有 target 及其 scrape_interval
2. 调度 Scrape Job：按 interval 触发，到时间发起 HTTP GET
3. 协议解析：解析 text exposition 格式为 sample
4. 标签处理：执行 relabel_configs 和 metric_relabel_configs
5. 健康检查：标记 target UP/DOWN
6. 异常处理：重试、限流、Stale Marker
```

**TSDB 三层存储架构**：

```
┌─────────────────────────────────────────────┐
│              TSDB (Time Series Database)     │
│                                             │
│  ┌────────┐    ┌──────────────┐   ┌──────────┐  │
│  │  WAL   │───▶│    Head      │──▶│  Disk    │  │
│  │ 磁盘日志│    │ 当前可变数据区 │   │  Block   │  │
│  │ 崩溃重放│    │ 活跃结构在内存 │   │ 不可变    │  │
│  └────────┘    └──────────────┘   └──────────┘  │
│       ↑               ↑               ↑         │
│    崩溃恢复        实时查询       持久化/压缩/删除 │
│                                                │
│  /data/                                        │
│  ├── wal/           ← 崩溃重放日志               │
│  ├── chunks_head/   ← Head 中已持久化并可 mmap 的 chunk │
│  └── 01HXXXX/       ← 不可变 Block 目录           │
└─────────────────────────────────────────────┘
```

#### HTTP Server 详解

```
HTTP Server 是 Prometheus 对外的统一接口：

┌────────────────────────────────────────────┐
│              HTTP Server                    │
│                                            │
│  /-/ready                健康检查           │
│  /-/healthy              健康状态           │
│  /-/reload               热加载配置（POST） │
│  /metrics                Prometheus 自身指标│
│                                            │
│  /api/v1/query          PromQL 即时查询     │
│  /api/v1/query_range    PromQL 范围查询     │
│  /api/v1/series         时间序列元数据      │
│  /api/v1/labels          标签名查询         │
│  /api/v1/status/config  当前运行时配置     │
│  /api/v1/targets        当前采集目标       │
│                                            │
│  /graph                  旧版 Web UI        │
└────────────────────────────────────────────┘

外部消费者：
  - Grafana: 通过 query/query_range 查询数据
  - kubectl: 通过 port-forward 调用 API
  - 第三方应用: 用 prometheus_api_client 库
```

#### Remote Read/Write 详解

```
Remote Read: Prometheus 主动从外部存储拉数据（用于查询时合并）
Remote Write: Prometheus 主动把数据推到外部存储（用于长期保存）

典型场景：Prometheus 本地保留较短时间窗口，远程存储承担更长保留期与全局查询；保留时长应按容量、查询范围和运维成本确定，不固定为 15 天。

Remote Write 流程：
  Prometheus 采集 → Append 到本地 TSDB / WAL
  → Remote Write 队列从 WAL 读取样本并分片、批量发送
  → 推送到 Thanos Receive / Cortex / Mimir / VictoriaMetrics

Remote Read 流程：
  Grafana 发起 PromQL → Prometheus 按配置把部分查询交给远端读取
  → 本地与远端结果由查询引擎合并
  注意：不是所有长期存储方案都依赖 Prometheus Remote Read；Thanos 通常由 Thanos Query 聚合 Sidecar / Store Gateway。

性能与故障边界：
  - 开销取决于 samples/s、标签量、批大小、压缩、分片和远端延迟，不能套固定百分比
  - 远端不可用时队列会退避重试并产生积压，通常不会同步阻塞本地抓取和 TSDB 写入
  - 若故障超过 WAL 可追赶窗口或磁盘容量边界，尚未发送的远端数据可能丢失
  - 重点监控 prometheus_remote_storage_* 队列、失败、重试和最高发送时间戳指标
```

### 3 数据写入路径

```
每次 Scrape (/metrics 拉取):

  Retrieval 模块 (HTTP GET)
       │
       ▼
  解析 text 格式
       │
       ▼
  relabel 引擎处理标签
       │
       ▼
  TSDB appender：样本加入 Head，并记录 WAL
       │
       ▼
  Head 达到时间窗口后切为不可变 Disk Block
       │
       ▼
  Compactor 合并相邻 Block，Retention 清理旧块

写入性能关键:
  ┌────────────────────────────────────────────────────────────┐
  │ WAL 以顺序追加为主；磁盘延迟、吞吐、容量和 fsync 稳定性都重要 │
  │ Head 内存主要受活跃 series、标签、chunk 和索引开销影响         │
  │ 不能使用固定“每 sample 若干 KB”估算内存，应以实测指标容量规划   │
  │ Compaction 合并块以减少查询扫描开销；Retention 由时间/大小配置   │
  └────────────────────────────────────────────────────────────┘
```

---

## 第二章 Prometheus CR 完整配置 (Operator 模式)

### 1 Prometheus CR 全景

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: k8s
  namespace: monitoring
spec:
  # === 版本和副本 ===
  version: v2.50.0
  replicas: 2                           # HA：两个 Prometheus 实例
  shards: 1                             # 水平分片（大规模集群用）
  
  # === 镜像和拉取策略 ===
  image: quay.io/prometheus/prometheus:v2.50.0
  imagePullPolicy: IfNotPresent
  
  # === 数据保留 ===
  retention: 15d                        # 数据保留天数
  retentionSize: 45GB                   # 或按大小限制
  
  # === 外部标签（HA 场景标识实例） ===
  externalLabels:
    cluster: prod-gz
    region: ap-guangzhou
    env: production
  
  # === ServiceMonitor / PodMonitor 选择器 ===
  serviceMonitorSelector:
    matchLabels:
      release: prometheus               # 只选择有此 label 的 ServiceMonitor
  serviceMonitorNamespaceSelector: {}   # 所有命名空间
  podMonitorSelector:
    matchLabels:
      release: prometheus
  podMonitorNamespaceSelector: {}
  
  # === 额外 scrape_configs（引用 Secret 中的配置片段） ===
  # 它不会自动给所有 Target 加标签；目标标签应在对应抓取配置的 relabelings 中设置。
  additionalScrapeConfigs:
    name: additional-scrape-configs
    key: scrape-configs.yaml
  
  # === 远程写入（长期存储） ===
  remoteWrite:
    - url: http://thanos-receive.monitoring.svc.cluster.local:19291/api/v1/receive
      queueConfig:
        capacity: 2500                  # 内存队列容量
        maxShards: 200                  # 最大并发分片
        minShards: 1
        maxSamplesPerSend: 500
        batchSendDeadline: 5s
        minBackoff: 30ms
        maxBackoff: 100ms
      writeRelabelConfigs:
        - action: keep                  # 只写特定指标到远程存储
          sourceLabels: [__name__]
          regex: 'game_.*|process_.*'
  
  # === 告警管理 ===
  alerting:
    alertmanagers:
      - namespace: monitoring
        name: alertmanager-operated
        port: web
        apiVersion: v2
        pathPrefix: /
  
  # === PrometheusRule 选择器 ===
  ruleSelector:
    matchLabels:
      release: prometheus
  
  # === 资源限制 ===
  resources:
    requests:
      cpu: "1"
      memory: 2Gi
    limits:
      cpu: "4"
      memory: 8Gi
  
  # === 存储（强烈建议 PVC） ===
  storage:
    volumeClaimTemplate:
      spec:
        storageClassName: cbs-ssd       # 使用 SSD
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 100Gi              # (retention × 样本速率) 的空闲量
  
  # === 安全 ===
  securityContext:
    fsGroup: 2000
    runAsNonRoot: true
    runAsUser: 1000
  
  # === TSDB 调优 ===
  # 默认不要开启乱序窗口；仅在确认确有乱序写入需求，并用当前 Prometheus Operator CRD
  # 校验 outOfOrderTimeWindow 字段后配置。
  
  # === 查询 ===
  # 这些是 Prometheus CLI 参数，不是嵌套 query 字段；应用前用当前 Operator CRD 校验 additionalArgs。
  additionalArgs:
    - name: query.lookback-delta
      value: 5m
    - name: query.max-samples
      value: "50000000"
    - name: query.timeout
      value: 2m
  
  # === 亲和性（HA 实例分散到不同节点） ===
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - topologyKey: kubernetes.io/hostname
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: prometheus
```

### 2 存储容量规划公式

```
磁盘容量 = (retention 天数) × (样本吞吐量 / 天) × 安全系数 1.3

样本吞吐量:
  = sum(每秒采集样本数)
  = sum(每个 Target 的 metric 数量 / scrape interval)
  
示例:
  1000 个 target, 每个 target 2000 条 metric, scrape interval 30s
  = 1000 × 2000 / 30 = 66,666 samples/s
  = 66,666 × 86400 = 5.76B samples/day
  ≈ 每 sample 约 1.5 字节压缩后
  = 5.76B × 1.5 = 8.64 GB/day
  × 15 days × 1.3 ≈ 168 GB
```

### 3 WAL 与崩溃恢复

```
WAL (Write-Ahead Log) 的目标是降低进程崩溃后的数据丢失窗口：

scrape → 通过 TSDB appender 将样本加入 Head，并记录 WAL

崩溃恢复:
  Prometheus 重启 → 读取 WAL → 重放到 Head
  恢复时间取决于 WAL 大小、磁盘吞吐、CPU、活跃序列与损坏情况，不套固定分钟数

WAL 相关配置:
  --storage.tsdb.wal-compression    # 开启压缩以减少 WAL 空间，实际收益依数据而定
  --storage.tsdb.wal-segment-size   # 段大小；默认值和支持范围以当前版本 --help 为准

边界：WAL 不能替代备份/副本，也不能保证磁盘损坏、超出保留窗口或未成功持久化的数据绝不丢失。
```

---

## 第三章 Prometheus 四种核心指标类型（面试必问）

> 面试官大概率会问："Prometheus 有哪四种指标类型？分别用在什么场景？"
> 四种类型不仅是 API 分类，更决定了**存储方式、查询函数、性能特性**。

### 0 四种类型全景对比

| 类型 | 英文 | 行为 | 特点 | 适用场景 | 查询函数 |
|------|------|------|------|----------|----------|
| **Counter** | 计数器 | 只增不减（重启归零） | 累计值，不关心当前瞬时 | 请求数、错误数、任务完成数 | `rate()`, `increase()` |
| **Gauge** | 仪表盘 | 可增可减 | 瞬时值，上上下下 | 内存、CPU、队列长度、温度 | 直接使用 / `avg_over_time()` |
| **Histogram** | 直方图 | 分桶统计分布 | 多时间序列（_bucket/_sum/_count） | 请求延迟、响应大小分布 | `histogram_quantile()` |
| **Summary** | 摘要 | 客户端计算分位数 | 与 Histogram 类似，但客户端算 | 延迟分位数（不聚合场景） | 直接用 / `avg_over_time()` |

### 1 Counter — 只增不减的累计计数器

```
Counter 本质：一个单调递增的整数
- 每次 Inc() 加 1
- 进程重启 → 归零（Rate 函数会自动处理）
- 只能增加，不能减少（所以不能用 Counter 表示"当前在线用户数"）

正确用法：
  http_requests_total{method="GET", status="200"}  ← Counter ✅
  
错误用法：
  current_queue_size  ← 应该用 Gauge ❌

指标命名规范：后缀必须是 _total

Counter 的查询陷阱：
  # ❌ 直接查 Counter — 只能看到单调递增的累积值
  http_requests_total
  
  # ✅ 用 rate() 转换为每秒速率
  rate(http_requests_total[5m])
  
  # ✅ 用 increase() 计算区间增量
  increase(http_requests_total[1h])
  
  为什么必须用 rate/increase？
  → Counter 是累积值，今天 1 万明天 2 万，直接看没意义
  → rate() 使用范围向量内的样本估算平均每秒增长率，处理可见 Counter Reset，并对查询边界外推
  → 不能简化为固定首尾两点相减；抓取间隔内不可见的多次 Reset 仍可能导致低估
```

### 2 Gauge — 可增可减的瞬时仪表

```
Gauge 本质：一个可以任意升降的数值
- Set() 设为任意值
- Inc() / Dec() 增减
- 表示"此刻"的状态，不是"累计"的量

正确用法：
  node_memory_MemAvailable_bytes{instance="10.0.1.5"} 74700000000  ← Gauge ✅
  go_goroutines{job="api-server"} 42                               ← Gauge ✅
  
查询方式：
  # 直接查询 → 看到当前值
  go_goroutines
  
  # 区间平均
  avg_over_time(go_goroutines[5m])
  
  # 区间最大/最小
  max_over_time(node_memory_MemAvailable_bytes[1h])
  min_over_time(node_memory_MemAvailable_bytes[1h])
  
  # 变化量（Gauge 也可以算增量）
  delta(node_memory_MemAvailable_bytes[5m])  # 不适合有 Reset 的场景
```

### 3 Histogram — 服务器端分桶统计分布

**Histogram 是面试中一定会被深入追问的类型**，理解它需要知道三个子指标：

```
一次 http_request_duration_seconds 的 Histogram 会产生以下时间序列：

http_request_duration_seconds_bucket{le="0.005"} 320     ← ≤5ms 的请求数
http_request_duration_seconds_bucket{le="0.01"}  650     ← ≤10ms 的请求数
http_request_duration_seconds_bucket{le="0.025"} 1200    ← ≤25ms 的请求数
http_request_duration_seconds_bucket{le="0.05"}  2100    ← ≤50ms 的请求数
http_request_duration_seconds_bucket{le="0.1"}   2800    ← ≤100ms 的请求数
http_request_duration_seconds_bucket{le="0.25"}  3100    ← ≤250ms 的请求数
http_request_duration_seconds_bucket{le="0.5"}   3350    ← ≤500ms 的请求数
http_request_duration_seconds_bucket{le="1"}     3480    ← ≤1s 的请求数
http_request_duration_seconds_bucket{le="+Inf"}  3500    ← 所有请求数
http_request_duration_seconds_sum  234.5                  ← 所有请求延迟的求和
http_request_duration_seconds_count 3500                  ← 总请求数

理解关键：
1. bucket 是累积的！le="0.1" 包含所有 ≤0.1s 的请求，不是 0.05~0.1s 区间的
2. +Inf 这个 bucket 一定等于 _count（包含所有请求）
3. 每个 Bucket 都是一条独立的时间序列（标签 le 不同）
4. sum/count 是两个单独的 Counter

P99 如何计算？
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
  → 用 bucket 累积值反推分布，找到 99% 分位的边界值
  → 整个过程在 Prometheus Server 端完成（不是客户端算好的）

Histogram vs Summary 选择：
  Histogram → 可以用任意聚合维度（sum by namespace, by service...）
  Summary   → 客户端算好分位数，无法跨实例聚合
  结论：K8s 监控几乎只用 Histogram
```

### 4 指标暴露格式详解（Exposition Format）

**这是面试官常问的"/metrics 端点返回的是什么"**：

```
GET /metrics 返回的原始内容（text/plain 纯文本）：

# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",handler="/api",status="200"} 152347
http_requests_total{method="POST",handler="/api",status="201"} 89231

# HELP process_cpu_seconds_total Total user and system CPU time
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 234.56

# HELP http_request_duration_seconds Histogram of request duration
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005"} 320
http_request_duration_seconds_bucket{le="0.01"} 650
http_request_duration_seconds_bucket{le="+Inf"} 3500
http_request_duration_seconds_sum 234.5
http_request_duration_seconds_count 3500

格式规则（面试要记住）：
1. # HELP <name> <描述>     — 指标文档（可省略）
2. # TYPE <name> <类型>     — 指标类型声明（可省略）
3. <name>{<labels>} <value> [<timestamp_ms>] — 数据行；显式时间戳为 Unix 毫秒
4. labels 为空时可以写 <name> <value>（如 process_cpu_seconds_total）
5. 时间戳可选；未提供时使用抓取时间。显式时间戳默认由 `honor_timestamps: true` 保留，设为 `false` 时才改用抓取时间
6. 不支持嵌套 JSON，是一行一行的 KV 对

为什么用纯文本而不 JSON？
  → 流式解析（一行一解析）、人类可读、前后兼容
  → 2000 个 metric 的 /metrics 约 100KB，文本格式足够紧凑
```

### 5 Pull 模型 vs Push 模型（面试高频对比题）

```
Prometheus 是 Pull 模型（拉取），为什么这么设计？

Pull 模型的优势：
1. 健康检查内置：scrape 失败 → 直接知道 Target DOWN
2. 无需中间件：不需要消息队列缓冲（Push 模型需要 PushGateway）
3. 统一采集控制：scrape_interval 在 Prometheus 侧统一配置
4. 服务发现天然：配合 K8s SD 自动发现，不需要每个应用配置推送地址
5. 数据完整性：Prometheus 知道"最后一次成功采集是什么时候"

Push 场景需要 PushGateway：
  短生命周期任务（Job/CronJob）无法被 pull 到
  → 任务执行时 push 到 PushGateway
  → Prometheus pull PushGateway（PushGateway 作为代理）
  
PushGateway 的坑：
  - PushGateway 中的数据不会自动过期（需手动清理）
  - PushGateway 是单点瓶颈
  - 指标会被后一次 push 覆盖（不可追加）
```

---

## 第四章 ServiceMonitor 原理深入（面试场景版）

> `K8s_Advanced.md` 第二十八章已覆盖 ServiceMonitor 的完整字段和 5 个生产案例，
> 此处补充**内部工作流程**和**终极调试方法**。

### 0 ServiceMonitor 快速上手（端到端示例）

以下是一个完整的"业务暴露 metrics → Service → ServiceMonitor → Prometheus 采集"链路的自包含示例：

**Step 1：应用暴露 /metrics**

> 使用 ServiceMonitor 时，**Pod 上不需要任何 prometheus.io 注解**。
> ServiceMonitor 通过 label 链匹配：ServiceMonitor → Service → Pod，注解只在老派原生方式才需要。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: game-server
  namespace: game-prod
  labels:
    app: game-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: game-server
  template:
    metadata:
      labels:
        app: game-server            # Service 通过这个 label 匹配 Pod
    spec:
      containers:
        - name: game-server
          image: mygame:latest
          ports:
            - name: metrics
              containerPort: 9090
          # 应用代码中已启动 metrics HTTP server，监听 9090 端口
```

**Step 2：创建 Service**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: game-server-metrics
  namespace: game-prod
  labels:
    app: game-server                # ServiceMonitor 通过这个 label 匹配
spec:
  selector:
    app: game-server                # 匹配 Pod
  ports:
    - name: metrics                 # ServiceMonitor 通过 port name 匹配
      port: 9090
      targetPort: 9090
```

**Step 3：创建 ServiceMonitor**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: game-server-monitor
  namespace: game-prod
  labels:
    release: prometheus            # Prometheus CR 的 serviceMonitorSelector 会匹配此 label
spec:
  selector:
    matchLabels:
      app: game-server             # ① 匹配要监控的 Service
  endpoints:
    - port: metrics                # ② 匹配 Service 中 ports[].name
      interval: 30s                # ③ 采集间隔
      path: /metrics               # ④ 指标路径（默认就是 /metrics，可省略）
      scrapeTimeout: 10s           # ⑤ 采集超时
```

> **三步串联逻辑**：`ServiceMonitor.spec.selector` 匹配 Service 标签；Operator 生成基于 EndpointSlice/Endpoints 的发现配置，再从其地址与端口生成 Target。普通 selector-backed Service 的 EndpointSlice 通常由 Controller 根据 Pod 标签与就绪状态维护；selectorless Service 也可以绑定手工 EndpointSlice。
>
> **为什么不用 Pod 注解？** 两种发现方式的本质区别：
> ```
> 注解约定方式（需在原生 Prometheus 配置中自行编写 relabel 规则）：
>   Prometheus SD → 发现 Pod → 按 annotation 过滤并提取端口/路径
>   缺点：规则和注解约定容易分散
>
> ServiceMonitor（Operator）：
>   ServiceMonitor → Service → EndpointSlice/Endpoints → Target
>   优点：抓取配置集中为 CR，且由 Operator 生成 Prometheus 配置
>
>   普通 Service 场景下 Pod 只需被 Service selector 选中，不要求 scrape annotation。
> ```

**Step 4：验证采集**

```shell
# 检查 ServiceMonitor 是否被 Prometheus 识别
$ kubectl get servicemonitor -n game-prod game-server-monitor
NAME                   AGE
game-server-monitor    2m

# 在 Prometheus UI 查看 Targets
$ kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# 打开 http://localhost:9090/targets → 搜索 game-server → 状态应为 UP

# 查询指标：不要把生成配置中的 scrape job 名误当成 job 标签
$ curl -sG 'http://localhost:9090/api/v1/query' \
    --data-urlencode 'query=up{namespace="game-prod",service="game-server-metrics"}' | jq
# 若需要固定 job 标签，应设置 ServiceMonitor.spec.jobLabel，并在 Service 上提供对应标签
```

### 1 从 ServiceMonitor 到 Scrape 的完整链路

```
时刻 T: kubectl apply -f servicemonitor.yaml
  │
  ▼
时刻 T+1s: Prometheus Operator watch 到 ServiceMonitor 创建
  │  Operator 解析 ServiceMonitor 并生成 Prometheus 配置
  │  config-reloader sidecar 检测配置变化并触发 Prometheus reload
  │
  ▼
Prometheus 重载配置 → Service Discovery 开始工作
  │  K8s SD 通过 API Server 发现 Service / EndpointSlice / Pod 元数据
  │  匹配 ServiceMonitor.selector → 找到对应 Service
  │  按 Service 端口名和发现元数据生成候选 Target
  │  应用 target relabelings → 生成最终 Target Labels
  │
  ▼
Scraper 按 interval 采集 GET http://<target>:<port>/metrics
  │  scrape 成功 → 样本写入 TSDB，up=1
  │  scrape 失败 → 当前轮 up=0，通常等待下一个 scrape 周期，不固定 1s 重试
  │
  ▼
持续: 每 interval 秒重复上述 scrape 过程
```

### 2 终极调试：查看 Prometheus 运行时配置

```shell
# 1. 查看 Prometheus 当前采集配置（ServiceMonitor 转译后的结果）
$ kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
$ curl -s http://localhost:9090/api/v1/status/config | jq '.data.yaml' -r

# 2. 只查看某个 job 的配置
$ curl -s http://localhost:9090/api/v1/status/config | \
    jq '.data.yaml' -r | grep -A50 "job_name: serviceMonitor"

# 3. 查看 Service Discovery 发现了哪些 Target
$ curl -s http://localhost:9090/api/v1/targets | \
    jq '.data.activeTargets[] | {labels, scrapeUrl, health, lastError}' 

# 4. 查看某个 Target 的 Discovered Labels vs Final Labels
$ curl -s http://localhost:9090/api/v1/targets | \
    jq '.data.activeTargets[] | select(.labels.job=="gamesvr") | {discoveredLabels, labels}'

# 5. 验证 relabel 结果
# Prometheus UI → Status → Targets → 点击某个 Target
# 对比 "Before relabeling" 和 "After relabeling"
```

### 3 ServiceMonitor 未生效的终极排查流程

```
1. Prometheus CR label selector 匹配?
   kubectl get prometheus -n monitoring -o yaml | grep -A5 serviceMonitorSelector
   kubectl get servicemonitor -n game-prod --show-labels

2. Service 存在且有 label?
   kubectl get svc -n game-prod --show-labels

3. Service 有 Endpoints?
   kubectl get endpoints -n game-prod <svc-name>

4. Pod 就绪?
   kubectl get pod -n game-prod -l <service-selector-labels>

5. 网络策略阻挡?
   kubectl get networkpolicy -n game-prod
   # Prometheus Pod 的命名空间能否访问目标 Pod 的命名空间?

6. Operator 日志?
   kubectl logs -n monitoring deploy/prometheus-operator --tail=50

7. Prometheus 日志?
   kubectl logs -n monitoring prometheus-k8s-0 --tail=50 | grep -i error
```

---

## 第五章 PrometheusRule & 告警规则进阶

> `K8s_Advanced.md` 第十九章有基本告警规则，此处补充**Recording Rules、模板化、分组抑制**。

### 1 Recording Rules（记录规则）

Recording Rules 预先计算并存储聚合结果，加速 Grafana 查询：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: recording-rules
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: recording
      interval: 60s              # 每 60 秒评估一次
      rules:
        # HTTP 请求速率（预聚合，避免重复计算）
        - record: job:http_requests_total:rate5m
          expr: rate(http_requests_total[5m])
        
        # 命名空间级别 CPU 使用率
        - record: namespace:container_cpu_usage:sum
          expr: |
            sum by (namespace) (
              rate(container_cpu_usage_seconds_total{container!="", image!=""}[5m])
            )
        
        # 99 分位延迟（预计算 histogram）
        - record: job:http_request_duration_seconds:p99
          expr: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket[5m])) by (job, le)
            )
```

**Recording Rules 命名规范**：
```
<level>:<metric>:<operation>
级别: 指标: 操作

# 示例:
job:http_requests_total:rate5m       # job 级别，http_requests_total，5 分钟 rate
cluster:node_cpu_utilization:avg     # 集群级别，节点 CPU 使用率，平均值
```

### 2 告警规则模板化

使用 Go template 语法增强告警可读性：

```yaml
- alert: HighErrorRate
  expr: |
    sum(rate(http_requests_total{status=~"5.."}[5m])) by (service, namespace)
    /
    sum(rate(http_requests_total[5m])) by (service, namespace)
    > 0.05
  for: 5m                               # 持续 5 分钟才触发
  labels:
    severity: critical
    team: "{{ $labels.namespace }}"
    priority: P1
  annotations:
    summary: "{{ $labels.service }} 错误率超过 5%"
    description: |
      服务: {{ $labels.service }}
      命名空间: {{ $labels.namespace }}
      当前错误率: {{ $value | humanizePercentage }}
      评估窗口: 5m
      Runbook: https://wiki.internal/runbooks/{{ $labels.service }}-error-rate
    # 自定义标签用于 Alertmanager 路由
    dashboard_url: "https://grafana.internal/d/gamesvr-errors?var-namespace={{ $labels.namespace }}"
```

### 3 告警分组与抑制

```yaml
# AlertManager 配置（通过 AlertmanagerConfig CRD 管理）
apiVersion: monitoring.coreos.com/v1alpha1
kind: AlertmanagerConfig
metadata:
  name: game-alert-routing
  namespace: monitoring
  labels:
    release: prometheus
spec:
  # 抑制规则：高层告警触发时抑制低层告警
  inhibitRules:
    - sourceMatch:
        - name: severity
          value: critical
          matchType: "="
      targetMatch:
        - name: severity
          value: warning
          matchType: "="
      equal: ['namespace']
      # 含义：同 namespace 的 critical 告警会抑制 warning 告警
  
  # 路由树
  route:
    groupBy: ['namespace', 'severity']      # 分组键
    groupWait: 30s                           # 首次告警等待（收集同组告警）
    groupInterval: 5m                        # 同组新告警的发送间隔
    repeatInterval: 4h                       # 相同告警重复发送间隔
    receiver: default-webhook
    
    # 按 severity 分叉
    routes:
      - matchers:
          - name: severity
            value: critical
            matchType: "="
        receiver: critical-webhook
        continue: true                       # 继续匹配下一个规则
      - matchers:
          - name: severity
            value: warning
            matchType: "="
        receiver: default-webhook
      - matchers:
          - name: team
            value: game-backend
            matchType: "="
        receiver: default-webhook
  
  # 接收器定义
  receivers:
    - name: default-webhook
      webhookConfigs:
        - url: http://notification-service.monitoring:8080/alert
          sendResolved: true                  # 恢复时也通知
          httpConfig:
            authorization:
              type: Bearer
              credentials:
                name: webhook-token
                key: token
    
    - name: critical-webhook
      webhookConfigs:
        - url: http://pager.monitoring:8080/page
          sendResolved: true
```

---

## 第六章 Grafana 仪表盘即代码

### 1 通过 ConfigMap 预置仪表盘

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gamesvr-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"           # Grafana sidecar 自动识别

data:
  gamesvr-dashboard.json: |
      {
        "title": "GameServer Overview",
        "tags": ["gamesvr", "production"],
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "panels": [
          {
            "title": "Request Rate",
            "type": "graph",
            "targets": [{
              "expr": "sum(rate(http_requests_total{app=\"gamesvr\"}[5m])) by (version)",
              "legendFormat": "{{ version }}"
            }]
          },
          {
            "title": "Error Rate %",
            "type": "stat",
            "targets": [{
              "expr": "sum(rate(http_requests_total{app=\"gamesvr\",status=~\"5..\"}[5m])) / sum(rate(http_requests_total{app=\"gamesvr\"}[5m])) * 100"
            }],
            "fieldConfig": {
              "defaults": {
                "thresholds": {
                  "steps": [
                    {"value": null, "color": "green"},
                    {"value": 1, "color": "yellow"},
                    {"value": 5, "color": "red"}
                  ]
                }
              }
            }
          }
        ]
      }
```

### 2 Grafana 变量模板

在 PromQL 中使用 Grafana 变量实现交互式仪表盘：

```
# PromQL 中使用 Grafana 变量
rate(http_requests_total{
  namespace=~"$namespace",
  app=~"$app",
  version=~"$version"
}[$__rate_interval])

# 常用 Grafana 内置变量
$__interval       # Prometheus 自动计算的采集间隔
$__rate_interval  # rate() 函数的推荐间隔（≥4× scrape_interval）
$__range          # 仪表盘选择的时间范围
$__from / $__to   # 时间范围的 Unix 时间戳
```

### 3 跨数据源仪表盘（Prometheus + Loki）

```json
{
  "panels": [
    {
      "title": "Error Rate (Prometheus)",
      "datasource": "Prometheus",
      "targets": [{"expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m]))"}]
    },
    {
      "title": "Error Logs (Loki)",
      "datasource": "Loki",
      "targets": [{
        "expr": "{app=\"gamesvr\"} |= \"ERROR\" | json | line_format \"{{.message}}\""
      }]
    }
  ]
}
```

---

## 第七章 高可用与长期存储

### 1 Prometheus HA 模式

```
┌───────────────────────────────────────────────┐
│          Prometheus HA（有状态双副本）          │
│                                               │
│   ┌──────────────┐  ┌──────────────┐          │
│   │ Prometheus-0 │  │ Prometheus-1 │          │
│   │ 独立 TSDB/PVC │  │ 独立 TSDB/PVC │          │
│   │ 独立采集全量  │  │ 独立采集全量  │          │
│   └──────┬───────┘  └──────┬───────┘          │
│          └────────┬────────┘                  │
│                   ▼                           │
│       LB / Thanos Query / 其他统一查询层        │
│                   │                           │
│                   ▼                           │
│                Grafana                        │
│                                               │
│   两副本不复制本地数据，采样值和时间戳可能略有差异 │
└───────────────────────────────────────────────┘
```

设置 `replicas: 2` 和反亲和只解决采集副本冗余；完整 HA 还需持久化存储、统一查询/故障切换、告警去重及副本标签去重设计。Grafana 不会自动随机切换两个数据源。

### 2 Thanos 长期存储架构

```
┌──────────────────────────────────────────────────────────┐
│                      Thanos 架构                          │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐                     │
│  │ Prometheus-0 │  │ Prometheus-1 │                     │
│  │   + Sidecar  │  │   + Sidecar  │                     │
│  └──────┬───────┘  └──────┬───────┘                     │
│         │ 上传 2h 块数据     │                              │
│         ▼                  ▼                              │
│  ┌──────────────────────────────────┐                    │
│  │        对象存储 (COS/S3/GCS)       │  长期存储 + 压缩    │
│  └──────────────┬───────────────────┘                    │
│                 │                                         │
│         ┌───────▼───────┐                                │
│         │ Store Gateway │  读取对象存储中的历史块          │
│         └───────┬───────┘                                │
│                 │                                         │
│         ┌───────▼───────┐                                │
│         │   Querier     │  汇聚 Sidecar + Store 的数据    │
│         └───────┬───────┘      全局去重 + 合并             │
│                 │                                         │
│         ┌───────▼───────┐                                │
│         │    Grafana    │  查询 Thanos Querier API       │
│         └───────────────┘                                │
│                                                          │
│  ┌──────────────┐                                       │
│ │  Compactor    │  压缩 + 降采样（5m/1h 粒度）            │
│ └──────────────┘                                       │
└──────────────────────────────────────────────────────────┘
```

**Prometheus Operator + Thanos 集成示例**：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: k8s
  namespace: monitoring
spec:
  replicas: 2
  retention: 6h            # 本地只保留 6h，历史数据在对象存储
  
  # Thanos Sidecar 自动注入
  thanos:
    version: v0.34.0
    objectStorageConfig:
      key: thanos-objstore.yaml
      name: thanos-objstore-config
    # Sidecar 自动将本地块上传到对象存储
    
  # 外部标签（集群标签；副本标签由 Operator/Thanos 集成机制按版本配置）
  externalLabels:
    cluster: prod-gz
  # 不要假设普通 YAML 中的 $(POD_NAME) 会按 shell 语义自动展开。
  # 请使用当前 Prometheus Operator 支持的 replica external label 配置，并核对 CRD。
  
  # 远程写入备选（如果不用 Sidecar）
  # remoteWrite:
  #   - url: http://thanos-receive.monitoring.svc.cluster.local:19291/api/v1/receive
```

### 3 Remote Write 到 VictoriaMetrics

VictoriaMetrics 是比 Thanos 更轻量的替代方案：

```yaml
spec:
  remoteWrite:
    - url: http://victoriametrics-vminsert.monitoring:8480/insert/0/prometheus
      queueConfig:
        capacity: 10000
        maxShards: 100
        maxSamplesPerSend: 1000
        batchSendDeadline: 5s
```

---

## 第八章 Prometheus 性能调优速查

### 1 常见性能瓶颈与解决

| 症状 | 原因 | 解决方案 |
|------|------|----------|
| OOM Kill | 查询返回过多数据 | 限制 `--query.max-samples`，用 Recording Rules 预聚合 |
| Scrape 超时 | Target 响应慢 | 增加 `scrapeTimeout`，减少 `/metrics` 大小 |
| WAL 损坏 | 磁盘故障或 OOM | SSD + `--storage.tsdb.wal-compression` |
| Compaction 慢 | 数据量大 | 增加 CPU，使用 SSD |
| 启动慢 | WAL 重放量大或磁盘慢 | 使用低延迟持久盘、控制活跃序列和写入量、保证优雅退出并监控 WAL checkpoint/truncation；不要手工 compact 或删除 WAL |
| 查询慢 | 未用 Recording Rules | 常用查询预聚合为 Recording Rules |

### 2 大规模集群优化清单

```
□ 使用 Recording Rules 代替高频原始查询
□ 限制 ServiceMonitor 的 sampleLimit / targetLimit
□ metricRelabelings 丢弃不必要指标（减少 60% 存储）
□ 使用 Thanos/Cortex/VictoriaMetrics 做长期存储
□ Prometheus 实例按职责分片（基础设施 / 业务分离）
□ Grafana 查询使用 $__rate_interval 而非硬编码 [5m]
□ 监控 Prometheus 自身指标（prometheus_tsdb_*）
□ 定期清理不活跃的 ServiceMonitor
```

### 3 Prometheus 自身监控指标

```promql
# WAL 损坏次数（应为 0）
prometheus_tsdb_wal_corruptions_total

# TSDB compaction 耗时
rate(prometheus_tsdb_compaction_duration_seconds_sum[1h])

# Scrape 成功率
sum(up{job!=""}) by (job) / count(up{job!=""}) by (job) < 0.99

# 内存使用
prometheus_tsdb_head_chunks
process_resident_memory_bytes

# 查询阶段耗时：该指标通常为 Summary，直接使用其 quantile 序列；先在 /metrics 核对当前版本
max by (slice) (
  prometheus_engine_query_duration_seconds{quantile="0.99"}
)
```

---

## 第九章 生产完整部署流程

### 1 部署步骤总览

```
Step 1: kube-prometheus-stack 安装（Prometheus + Grafana + Alertmanager + Operator）
Step 2: 确认基础 Target 可采集（node-exporter, kube-state-metrics, kubelet, cAdvisor）
Step 3: 为业务服务暴露 /metrics 端点
Step 4: 创建 ServiceMonitor / PodMonitor
Step 5: 验证 Target UP，指标可查询
Step 6: 创建 PrometheusRule（Recording + Alerting）
Step 7: 配置 Alertmanager 路由（Webhook → 企业微信/钉钉）
Step 8: 创建 Grafana 仪表盘
Step 9: 配置长期存储（Thanos / VictoriaMetrics）
Step 10: 压测 + 调优
```

### 2 完整 Helm 安装命令

```shell
# 先由 External Secrets/Sealed Secrets 等创建 monitoring/grafana-admin-credentials，
# 其中包含 admin-user 与 admin-password 两个 key；不要把明文密码写进命令行。
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set prometheus.prometheusSpec.retention=15d \
    --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName=cbs-ssd \
    --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=200Gi \
    --set prometheus.prometheusSpec.replicas=2 \
    --set prometheus.prometheusSpec.externalLabels.cluster=prod-gz \
    --set prometheus.prometheusSpec.serviceMonitorSelector.matchLabels.release=prometheus \
    --set prometheus.prometheusSpec.podMonitorSelector.matchLabels.release=prometheus \
    --set alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.storageClassName=cbs-premium \
    --set alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage=10Gi \
    --set grafana.admin.existingSecret=grafana-admin-credentials \
    --set grafana.admin.userKey=admin-user \
    --set grafana.admin.passwordKey=admin-password \
    --set grafana.persistence.enabled=true \
    --set grafana.persistence.size=10Gi \
    --set grafana.sidecar.dashboards.enabled=true \
    --set grafana.sidecar.datasources.enabled=true
```

### 3 验证全链路

```shell
# 1. 确认所有组件运行
$ kubectl get pods -n monitoring
NAME                                                    READY   STATUS
alertmanager-k8s-0                                      2/2     Running
prometheus-k8s-0                                        2/2     Running
prometheus-k8s-1                                        2/2     Running
prometheus-operator-xxxxx                               1/1     Running
grafana-xxxxx                                           1/1     Running

# 2. 检查 Targets（应全部 UP）
$ kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# 浏览器打开 http://localhost:9090/targets

# 3. 测试查询
$ curl -s 'http://localhost:9090/api/v1/query?query=up' | jq '.data.result[] | {job: .metric.job, status: .value[1]}'

# 4. 验证告警
$ kubectl port-forward -n monitoring svc/alertmanager-operated 9093:9093
# 浏览器打开 http://localhost:9093 → 查看 Alerts

# 5. 验证 Grafana
$ kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
# 用户名 admin，密码为安装时设置的密码
```

---

## 第十章 服务网格可观测性（Istio + Prometheus）

> Istio 内置 Prometheus 指标导出，通过 Prometheus Operator 的 ServiceMonitor 声明式采集，
> 实现服务网格级别的全链路可观测性（流量指标、延迟分布、错误率）。

### 1 Istio 标准指标

Istio 自动为所有经过 Envoy Sidecar 的流量生成以下核心指标：

| 指标 | 说明 | 标签 |
|------|------|------|
| `istio_requests_total` | 请求总数 | `reporter`, `source_workload`, `destination_workload`, `response_code` |
| `istio_request_duration_milliseconds` | 请求延迟分布 (Histogram) | 同上 + `response_flags` |
| `istio_request_bytes` | 请求体大小 | 同上 |
| `istio_response_bytes` | 响应体大小 | 同上 |
| `istio_tcp_connections_opened_total` | TCP 连接总数 | `source_*`, `destination_*` |
| `istio_tcp_connections_closed_total` | TCP 关闭连接数 | 同上 |
| `istio_tcp_sent_bytes_total` | TCP 发送字节数 | 同上 |
| `istio_tcp_received_bytes_total` | TCP 接收字节数 | 同上 |

```promql
# 服务级别错误率（5xx）
sum(rate(istio_requests_total{
  reporter="source",
  response_code=~"5.."
}[5m])) by (destination_service_name)
/
sum(rate(istio_requests_total{reporter="source"}[5m])) by (destination_service_name)
* 100

# P99 延迟（reporter=destination，使用前核对实际 Istio 指标标签）
histogram_quantile(0.99,
  sum(rate(istio_request_duration_milliseconds_bucket{reporter="destination"}[5m]))
  by (destination_service_name, le)
)

# 服务间调用流量 Top 10
topk(10,
  sum(rate(istio_requests_total{reporter="source"}[5m]))
  by (source_workload, destination_workload)
)
```

**reporter 标签说明**：
- `reporter="destination"` / 某些版本中的目标侧语义 — 由目标侧代理观察到的请求尝试，适合目标侧流量与延迟 SLI；客户端重试仍可能形成多次目标侧请求
- `reporter="source"` — 由源侧代理观察，通常包含更完整的 source 标签
- 标签名和值随 Istio 指标版本演进，使用前应检查实际 `/stats/prometheus` 输出

### 2 ServiceMonitor 采集 Istio 指标

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: istio-component-monitor
  namespace: monitoring
  labels:
    release: prometheus
spec:
  selector:
    matchExpressions:
      - key: istio
        operator: In
        values: [pilot]
  namespaceSelector:
    any: true
  endpoints:
    - port: http-monitoring
      interval: 15s
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
          action: keep
          regex: true
---
# Sidecar Envoy 指标采集（作为 Pod 注解自动发现）
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: envoy-stats-monitor
  namespace: monitoring
  labels:
    release: prometheus
spec:
  selector:
    matchExpressions:
      - key: security.istio.io/tlsMode
        operator: Exists              # 有 Sidecar 注入的 Pod
  namespaceSelector:
    any: true
  podMetricsEndpoints:
    - port: http-envoy-prom
      interval: 15s
      path: /stats/prometheus
      metricRelabelings:
        # __name__ 只在样本阶段可用，因此必须放在 metricRelabelings
        - action: keep
          sourceLabels: [__name__]
          regex: 'istio_.*'
        # 丢弃高基数的标签
        - action: labeldrop
          regex: 'connection_security_policy|response_flags|grpc_response_status'
```

### 3 Istio Grafana 仪表盘

Istio 官方提供了一套预置 Grafana 仪表盘，通过 ConfigMap 挂载：

```shell
# 安装 Istio 官方仪表盘
$ kubectl apply -f samples/addons/grafana.yaml
# 或手动导入 ConfigMap：
$ kubectl create configmap istio-dashboards \
    -n monitoring \
    --from-file=istio-mesh-dashboard.json \
    --from-file=istio-service-dashboard.json \
    --from-file=istio-workload-dashboard.json \
    --from-file=istio-performance-dashboard.json
$ kubectl label configmap istio-dashboards -n monitoring grafana_dashboard=1
```

**核心仪表盘**：

| 仪表盘 | 用途 |
|--------|------|
| **Istio Mesh Dashboard** | 全局流量视图：总量/成功率/延迟/Pod 数月/各服务指标 |
| **Istio Service Dashboard** | 单服务视角：请求量/延迟/上游依赖/下游调用方 |
| **Istio Workload Dashboard** | 工作负载级：CPU/内存/网络 Io + 流量指标合并 |
| **Istio Performance Dashboard** | 控制平面：Pilot/xDS 推送延迟/内存使用/缓存命中率 |
| **Istio Wasm Extension Dashboard** | WASM 插件执行性能 |

**自定义 Golden Signals 面板**：

```json
{
  "title": "Istio Golden Signals",
  "panels": [
    {
      "title": "Request Rate",
      "expr": "sum(rate(istio_requests_total{reporter='destination'}[5m])) by (destination_service_name)"
    },
    {
      "title": "Error Rate %",
      "expr": "sum(rate(istio_requests_total{reporter='destination',response_code=~'5..'}[5m])) by (destination_service_name) / sum(rate(istio_requests_total{reporter='destination'}[5m])) by (destination_service_name) * 100"
    },
    {
      "title": "P99 Latency",
      "expr": "histogram_quantile(0.99, sum(rate(istio_request_duration_milliseconds_bucket{reporter='destination'}[5m])) by (destination_service_name, le))"
    },
    {
      "title": "Traffic Composition",
      "expr": "sum(rate(istio_requests_total{reporter='destination'}[5m])) by (destination_service_name, source_workload)"
    }
  ]
}
```

### 4 分布式追踪集成（Istio + Jaeger/Tempo）

Istio/Envoy 支持读取 W3C TraceContext、B3 等追踪头并生成代理 Span，但应用必须把入站追踪上下文传播到后续出站请求，或使用具备自动传播能力的探针；否则跨服务 Trace 会断链：

```
Pod A ── x-request-id: abc123 ──▶ Pod B ── x-request-id: abc123 ──▶ Pod C
  │                                 │                                 │
  Envoy Span A     +     Envoy Span B       +       Envoy Span C
       │                          │                                 │
       └──────────────────────────┴─────────────────────────────────┘
                    Traces 上报到 Jaeger / Tempo
```

```yaml
# IstioOperator 配置中启用分布式追踪
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
spec:
  meshConfig:
    enableTracing: true
    defaultConfig:
      tracing:
        sampling: 10.0                          # 10% 采样率
        zipkin:
          address: jaeger-collector.jaeger:9411  # Zipkin 兼容端点
```

```yaml
# 通过 Telemetry API 按命名空间/服务定制采样率
apiVersion: telemetry.istio.io/v1alpha1
kind: Telemetry
metadata:
  name: mesh-default
  namespace: istio-system
spec:
  tracing:
    - providers:
        - name: jaeger
      randomSamplingPercentage: 5.0
```

### 5 Istio + Prometheus 告警规则

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: istio-alerts
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: istio-service
      rules:
        - alert: IstioHigh5xxErrorRate
          expr: |
            sum(rate(istio_requests_total{reporter="destination",response_code=~"5.."}[5m])) by (destination_service_name)
            /
            sum(rate(istio_requests_total{reporter="destination"}[5m])) by (destination_service_name) > 0.05
          for: 5m
          labels:
            severity: critical
            component: service-mesh
          annotations:
            summary: "{{ $labels.destination_service_name }} 5xx 错误率 > 5%"
            description: "当前错误率: {{ $value | humanizePercentage }}"

        - alert: IstioHighP99Latency
          expr: |
            histogram_quantile(0.99,
              sum(rate(istio_request_duration_milliseconds_bucket{reporter="destination"}[5m]))
              by (destination_service_name, le)
            ) > 1000
          for: 5m
          labels:
            severity: warning
            component: service-mesh
          annotations:
            summary: "{{ $labels.destination_service_name }} P99 延迟 > 1000ms"

        - alert: IstioPilotHighMemory
          expr: container_memory_usage_bytes{container="discovery",namespace="istio-system"} > 3e9
          for: 5m
          labels:
            severity: warning
            component: istio-control-plane
          annotations:
            summary: "Istio Pilot 内存 > 3GB"

        - alert: IstioSidecarInjectionFailure
          expr: rate(sidecar_injection_failure_total[5m]) > 0
          for: 1m
          labels:
            severity: critical
            component: istio-control-plane
          annotations:
            summary: "Istio Sidecar 注入失败"
```

### 6 生产建议

```
□ Metadata Exchange / TCP 日志 → 用 Telemetry API 控制（不用 MeshConfig）
□ 服务端视角通常使用 reporter="destination"；使用前检查实际 istio_requests_total 标签值，避免跨版本假设
□ 高基数标签仅保留必要项（response_code / destination_service_name）
□ 使用 metricRelabelings 丢弃不需要的指标前缀
□ 采样率平衡：生产 1%~10%，灰度 50%，排障 100%
□ 控制平面监控：istio_* 指标 + Pilot 日志 + xDS 推送延迟
□ 使用 Helm、`istioctl install -f`、revision/canary 或 GitOps 管理 Istio；不再采用已弃用的集群内 Istio Operator 路线
□ Recording Rules 预聚合 istio_requests_total 的 rate()
```

**Istio 网络 + Prometheus 可观测性全景**：

```
┌──────────────────────────────────────────────────────────────┐
│              服务网格全链路可观测                              │
│                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │  Prometheus  │◀──│  Envoy      │◀──│ Envoy       │        │
│  │  metrics     │   │  Sidecar    │   │  Sidecar    │        │
│  │  + istio_*   │   │  /metrics   │   │  /metrics    │        │
│  └──────┬───────┘   └──────┬──────┘   └──────┬──────┘        │
│         │                  │                   │               │
│         │          ┌───────▼───────────────────▼──────┐       │
│         │          │        Jaeger / Tempo           │       │
│         │          │    (分布式追踪 → 调用链可视化)    │       │
│         │          └──────────────────────────────────┘       │
│         │                                                     │
│    ┌────▼─────────────────────────────────────────────────┐  │
│    │                    Grafana                            │  │
│    │  ┌───────────────┐ ┌──────────────┐ ┌─────────────┐   │  │
│    │  │ Istio Mesh    │ │ Istio Service│ │ Golden      │   │  │
│    │  │ Dashboard     │ │ Dashboard    │ │ Signals     │   │  │
│    │  └───────────────┘ └──────────────┘ └─────────────┘   │  │
│    └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 第十一章 PromQL 实战速查

> PromQL 是 Prometheus 的查询语言。本节从实际运维场景出发，覆盖最常用的查询模式。

### 1 基本数据类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **Instant Vector** | 某一时刻的所有时间序列值 | `http_requests_total` |
| **Range Vector** | 每条时间序列在一段时间内的样本集合 | `http_requests_total[5m]` |
| **Scalar** | 单个数值 | `scalar(count(up == 1))` |

> Instant Vector 可作为即时查询结果，也可在范围查询中按每个 step 评估后绘图；Range Vector 通常作为 `rate()`、`increase()`、`*_over_time()` 等函数的输入，不能直接作为普通面板的最终表达式。

### 2 最常用的四个函数

**rate() — 计算每秒增长率（Counter 专用）**

```promql
# 过去 5 分钟内，每秒 HTTP 请求数的平均增长率
rate(http_requests_total[5m])

# 在每个 PromQL 评估时刻，metric[5m] 选择该时刻之前 5 分钟内的样本
# 范围由查询评估时间锚定，而不是由最后一个样本锚定
# rate 窗口通常至少覆盖约 4 个 scrape_interval，并为抓取抖动留余量；Grafana 可使用 $__rate_interval
```

**increase() — 计算区间增长总量（Counter 专用）**

```promql
# 过去 1 小时内 HTTP 请求的总增量
increase(http_requests_total[1h])

# increase() = rate() × 区间秒数
# 例：rate()=100/s × 3600s = increase()=360,000
```

**avg_over_time() — 区间平均值（Gauge 专用）**

```promql
# 过去 30 分钟的平均内存使用量
avg_over_time(node_memory_MemAvailable_bytes[30m])
```

**histogram_quantile() — 分位数计算**

```promql
# P99 请求延迟
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
# le 标签是 histogram 的计算依据，绝对不能丢失
```

### 3 Counter 与 Gauge 的区分

| 类型 | 特点 | 适用函数 | 示例 |
|------|------|----------|------|
| **Counter** | 只增不减（重启归零） | `rate()` `increase()` | `http_requests_total`、`cpu_seconds_total` |
| **Gauge** | 可增可减 | 直接用 / `avg_over_time()` | `memory_bytes`、`goroutine_count` |

> **常见错误**：对 Counter 直接用 `http_requests_total` 画图——画出来的永远是单调递增的累积值。应该用 `rate(http_requests_total[5m])` 转换为每秒速率。

### 4 实战查询场景

**CPU 使用率**
```promql
# 容器 CPU 使用率（相对 request 的百分比）
sum by (namespace, pod) (
  rate(container_cpu_usage_seconds_total{container!="", image!=""}[5m])
)
/
sum by (namespace, pod) (
  kube_pod_container_resource_requests{resource="cpu", unit="core"}
)
  * 100
```

**内存使用率**
```promql
# Pod 内存相对于 limit 的使用比例
sum by (namespace, pod) (
  container_memory_working_set_bytes{container!="", image!=""}
)
/
sum by (namespace, pod) (
  kube_pod_container_resource_limits{resource="memory", unit="byte"} > 0
)
```

**Pod 重启次数**
```promql
# 过去 1 小时重启过的 Pod
increase(kube_pod_container_status_restarts_total[1h]) > 0
```

**服务可用性（UP/DOWN）**
```promql
# 有多少个目标不可达
count(up == 0) by (job)

# 可用性百分比
avg(up{job="api-server"}) * 100
```

**HTTP 错误率**
```promql
# 5xx 错误占比
sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
  /
sum(rate(http_requests_total[5m])) by (service)
  * 100
```

**磁盘使用率**
```promql
# 节点磁盘使用百分比（排除 tmpfs）
(1 - node_filesystem_avail_bytes{mountpoint="/",fstype!="tmpfs"}
  / node_filesystem_size_bytes{mountpoint="/",fstype!="tmpfs"}) * 100
```

### 5 聚合操作速查

| 操作 | 作用 | 示例 |
|------|------|------|
| `sum by (label)` | 按标签求和 | `sum by (pod) (rate(http_requests_total[5m]))` |
| `avg by (label)` | 按标签求平均 | `avg(node_cpu_seconds_total) by (instance)` |
| `topk(N, expr)` | 取前 N 个最大值 | `topk(5, rate(http_requests_total[5m]))` |
| `bottomk(N, expr)` | 取前 N 个最小值 | `bottomk(5, node_memory_available)` |
| `count by (label)` | 计数 | `count(up == 1) by (job)` |
| `count_values("label", expr)` | 按值分组计数 | `count_values("status", up)` |
| `label_replace()` | 修改标签名 | `label_replace(up, "service", "$1", "job", "(.*)")` |

### 6 向量匹配（多指标联合查询）

```promql
# 默认二元向量运算要求匹配标签集一致；on/ignoring 用于显式控制匹配键。
# 场景：按 Pod 聚合的 CPU 使用量 / 按 Pod 聚合的 CPU request（一对一）
sum by (namespace, pod) (
  rate(container_cpu_usage_seconds_total{container!=""}[5m])
)
/
on(namespace, pod)
sum by (namespace, pod) (
  kube_pod_container_resource_requests{resource="cpu", unit="core"}
)
```

> 只有当一侧确实存在额外多条序列、另一侧的匹配键唯一时，才按正确方向使用 `group_left` 或 `group_right`；否则会产生 many-to-many 错误。

### 7 时间偏移

```promql
# 与 1 小时前对比（环比）
rate(http_requests_total[5m])
  /
rate(http_requests_total[5m] offset 1h)
  * 100

# 与昨天同一时刻对比（同比）
rate(http_requests_total[5m])
  /
rate(http_requests_total[5m] offset 1d)
  * 100
```

### 8 PromQL 性能优化

| 原则 | 说明 |
|------|------|
| 用 Recording Rules 预聚合 | 常用查询提前计算存储，查询时直接读聚合结果 |
| 避免高基数标签 | `user_id`、`trace_id` 等会导致时间序列爆炸 |
| 缩小时间范围 | `[5m]` 比 `[1h]` 快 10 倍以上 |
| 先聚合再计算 | `sum(rate(x[5m]))` 比 `rate(sum(x)[5m])` 更高效 |
| 用 `$__rate_interval` | Grafana 中的变量，自动适配 scrape_interval |

---

## 第十二章 Prometheus 面试高频 15 问

> 以下问题整合了真实 Prometheus 面试中反复出现的技术考察点，
> 按数据流顺序（暴露→采集→存储→查询→告警→调优）编排。

### Q1：一个 HTTP 请求从进入服务到出现在 Grafana 图表上，经历了哪些步骤？

```
完整链路：
1. 业务代码中使用 client library 打点（如 counter.Inc()）
2. client library 在内存中维护指标值
3. Prometheus HTTP handler（如 promhttp）暴露 /metrics 端点
4. Prometheus Server 通过 Service Discovery 发现该 Pod
5. 按 scrape_interval（如 30s）发起 HTTP GET /metrics
6. 解析文本格式 → 生成 (metric, labels, value, timestamp) 样本
7. 样本经 TSDB appender 加入 Head，并写入 WAL 以支持崩溃恢复
8. Head 按时间窗口切块并持久化为 Disk Block（通常约 2h，受实现与配置影响）
9. Grafana 通过 Prometheus HTTP API 发起 PromQL 查询
10. Prometheus 从 Head 与磁盘块中检索数据并返回
11. Grafana 渲染图表

面试加分项：说明 WAL 的恢复作用与边界、stale marker 的不同触发场景、retention 与 compaction
```

### Q2：Counter 重启归零后，rate() 为什么不会出现负数尖刺？

```
Counter 重启后值归零 → 下一个 scrape 的值从 0 开始
rate() 检测到"当前值 < 上一个 scrape 值" → 判定为 Counter Reset
Counter Reset 处理逻辑：
  rate()/increase() 看到值下降时会按 reset 处理，不把下降量当成负增长；
  它根据范围向量内的样本重建可观测增量，并对区间边界做外推。
  
实际例子：
  t1 时刻 scrape 到 1000
  进程重启
  t2 时刻 scrape 到 10
  → 两个观测点之间能确认的新增长主要是重启后的 10，而不是 1010
  → 具体 rate 还受查询窗口、样本数和边界外推影响，不能简化为固定两点公式
  
注意：increase() 本质上是区间 rate 的语法糖式结果；若两次 scrape 之间发生多次重启，未被观测到的增长无法恢复，会低估。可用 resets(counter[窗口]) 验证可见 reset 次数。
```

### Q3：histogram_quantile() 和 Summary 的 quantile 有什么区别？

```
histogram_quantile()（Prometheus Server 端计算）：
  - 原始数据是 bucket 累积分布
  - 可以随意聚合：sum by (namespace), sum by (service)
  - 分位数在 PromQL 查询时才计算
  - 精度受 bucket 划分影响（桶太少 → 近似误差大）
  
Summary quantile（客户端计算）：
  - 客户端在内存中维护采样，实时计算分位数
  - 直接暴露为普通指标：http_request_duration_seconds{quantile="0.99"}
  - 无法跨实例聚合！因为分位数不可加
  - 精度高（客户端可以维护更细粒度的采样）
  
面试建议：
  → "生产环境统一用 Histogram，因为可以跨实例聚合"
  → "Summary 只在无法接受 Histogram 近似误差时使用（罕见）"
```

### Q4：Prometheus 本地 TSDB 应该保留多久？

```
Prometheus 本地 TSDB 没有“超过 15 天就不适合”的硬限制，retention 可按时间和大小配置。

选型依据：
1. 活跃 series、samples/s、抓取间隔和标签基数
2. 本地磁盘容量、WAL/Compaction 开销和故障恢复时间
3. 查询跨度、并发与延迟 SLO
4. 是否需要跨集群全局视图、对象存储和长期归档

常见方案：
  → 本地 TSDB 保留满足日常排障的热数据窗口
  → Thanos / Mimir / VictoriaMetrics 等承担跨集群或长期查询
  → Remote Write 或 Thanos Sidecar 的链路与故障边界需分别设计

结论：保留期是容量与运维决策，不是固定 15 天；必须根据实测指标和查询需求计算。
```

### Q5：ServiceMonitor 创建后，Target 没有出现在 Prometheus UI 中，排查思路？

```
六级排查法（从外到内）：
① Prometheus CR 的 serviceMonitorSelector 是否匹配 ServiceMonitor 的 label？
   → kubectl get prometheus -n monitoring -o yaml | grep -A5 serviceMonitorSelector
   → kubectl get servicemonitor -n <ns> --show-labels

② ServiceMonitor 的 selector 是否匹配 Service 的 label？
   → kubectl get svc -n <ns> --show-labels

③ Service 的 selector 是否匹配 Pod 的 label？
   → kubectl get endpoints -n <ns> <svc-name>
   → 如果 Endpoints 为空 → Pod 没被 Service 选中

④ Pod 是否健康运行（Running + Readiness 通过）？
   → kubectl get pod -n <ns> -l <pod-labels>

⑤ Prometheus 命名空间的网络策略是否允许访问目标 Pod 的端口？
   → kubectl get networkpolicy -A

⑥ Prometheus Operator 日志和 Prometheus 自身日志：
   → kubectl logs -n monitoring deploy/prometheus-operator --tail=50
   → kubectl logs -n monitoring prometheus-k8s-0 --tail=50 | grep -i error
```

### Q6：什么是指标基数爆炸（Cardinality Explosion）？如何避免？

```
基数 = 某个指标的时间序列总数
基数过高 → TSDB 内存爆炸、查询超时、Compaction 停滞

反面案例（基数爆炸）：
  http_requests_total{user_id="12345", trace_id="abc123", session_id="xyz"}
  ↑ 每个 user_id 一条新序列，100 万用户 = 100 万条序列

正面案例（合理标签）：
  http_requests_total{method="GET", handler="/api/v1/users", status="200"}
  ↑ 有限的枚举值，最多几十条序列

避免方法：
  ① 绝对不用 user_id / request_id / session_id 作为标签
  ② 用 metric_relabel 丢弃高基数标签：
     metricRelabelings:
       - action: labeldrop
         regex: 'user_id|trace_id|session_id'
  ③ 监控基数趋势：
     prometheus_tsdb_head_series  ← 当前活跃的序列数
  ④ 根据 active series、samples/s、内存、WAL、查询并发与 SLO 联合决定是否分片，不使用固定序列数阈值
```

### Q7：Recording Rule 和 Alerting Rule 的执行有什么区别？

```
执行频率：
  - 两类规则都由全局 evaluation_interval 或 Rule Group 的 interval 调度
  - 规则评估与 scrape 独立，不保证每轮 scrape 完成后立即执行
  
执行顺序：
  - 同一 Rule Group 内按文件中的顺序顺序评估，可让后续规则引用前面刚生成的结果
  - 不同 Rule Group 可能并行评估，不能依赖跨组顺序
  
Recording Rule 存储的是预计算结果：
  - 存储为新的时间序列（如 job:http_requests_total:rate5m）
  - Grafana 或告警可复用结果，减少重复计算
  
Alerting Rule 维护告警状态：
  - 计算结果本身不会像 Recording Rule 一样保存为新业务时间序列
  - 状态为 Inactive → Pending（满足 expr 但未满 for）→ Firing
```

### Q8：Prometheus HA 方案中，两个实例的数据一定一致吗？

```
不一致！Prometheus HA 通常是“两个有状态实例独立采集”，而不是数据复制型主备。

两个 Prometheus 实例：
  - 各自维护本地 TSDB/PVC，并独立采集相同 Target
  - 采集时机不完全同步（scrape 时间有偏差）
  - 数据可能有微小差异（时间戳和值都可能不同）

查询时：
  - Grafana 只会查询配置的数据源，不会自动随机选择或故障切换
  - 普通负载均衡可提高查询入口可用性，但不会合并或去重两个副本的数据
  - Thanos Query 等查询层在正确配置 replica label 后，才可聚合并执行副本去重
  
为什么会不一致？
  t0: Prometheus-0 scrape GET /metrics → 返回 counter=1000
  t0+50ms: Prometheus-1 scrape GET /metrics → 返回 counter=1010
  → 两次采集值不同，时间戳也不同
  
这种不一致在大多数监控场景是可接受的（监测趋势，不要求精确值）

需要全局一致数据 → 用 Thanos Querier 做去重（基于 external_labels + replica）
```

### Q9：一个高负载 Prometheus 出现 OOM，你会怎么排查和优化？

```
排查步骤：
1. 确认 OOM 原因：
   → kubectl describe pod 查看 OOMKilled 事件和 exit code 137
   → 检查 memory limit 是否过低

2. 分析内存大户：
   → prometheus_tsdb_head_series          ← Head Block 中的序列数
   → prometheus_tsdb_head_chunks          ← Head Block 中 chunk 数
   → go_memstats_alloc_bytes              ← Go runtime 实际分配

3. 确认是采集量大还是查询量大：
   采集量大：prometheus_tsdb_head_samples_appended_total 很高
   查询量大：prometheus_engine_queries 很高 + 查询超时

优化方案（从易到难）：
  ① 用 metricRelabelings 丢弃不必要指标（如只保留 game_ 前缀的指标）
     → 通常能减少 50-70% 数据量
  ② 用 Recording Rules 代替高频原始查询
  ③ 增加 memory limit 或使用更大的 VM
  ④ Prometheus 分片（shards: 2~4）
  ⑤ 按职责拆分 Prometheus 实例（基础设施 / 业务 / GPU 各一个）
```

### Q10：alert 的 for: 5m 到底起什么作用？

```
for 的作用：防止告警抖动（Alert Flapping）

没有 for：
  t0: expr 满足 → 立即 Firing
  t0+30s: scrape 失败 → expr 不满足 → 立即 Resolved
  t0+60s: scrape 恢复 → expr 满足 → 立即 Firing
  → 告警在 2 分钟内 3 次状态变更，微信消息轰炸

有 for: 5m：
  t0: expr 满足 → 进入 Pending（不告警）
  t0+30s: expr 不满足 → 下一次评估退出 Pending
  expr 连续满足约 5 分钟 → Firing（告警）
  Firing 后下一次评估不再满足 → 默认退出 Firing 并发送 Resolved

如果希望短暂恢复时仍保持 Firing，应显式配置 keep_firing_for。for 应按故障容忍时间和 SLO 设计，不套固定“评估周期 × 3”公式。
```

### Q11：Prometheus 的 pull 模型在 K8s 网络隔离场景下有什么问题？

```
K8s NetworkPolicy 或 Calico/Cilium 网络策略可能导致：

场景：Prometheus 在 ns=monitoring，业务 Pod 在 ns=prod

如果 prod 命名空间有严格的 Ingress NetworkPolicy：
  → Prometheus 的 Pod 无法访问 prod 命名空间中 Pod 的 9090 端口
  → scrape 失败，Target 标记为 DOWN

解决方案：
  ① 为 Prometheus 的命名空间授权访问目标命名空间
     → NetworkPolicy ingress 规则允许 monitoring namespace
  
  ② 使用 PodMonitor（跨命名空间时需 PodMonitorNamespaceSelector）
  
  ③ Prometheus 与业务 Pod 部署在同一命名空间（不推荐，破坏隔离）
  
  ④ 使用 Prometheus Agent 模式（每个 namespace 一个 Agent，汇总到中心 Prometheus）
```

### Q12：多个 Prometheus 实例采集同一个 Target，如何区分数据来源？

```
方法：设置 externalLabels

Prometheus CR 配置示意：
  externalLabels:
    cluster: prod-gz
    prometheus: k8s

作用：
  → 在联邦、Remote Write、告警和 Thanos 等外部通信场景标识数据来源
  → Thanos 可结合 cluster 标签和专用 replica 标签进行副本去重
  → 统一查询层可按 cluster 区分数据来源

注意：
  externalLabels 不是 scrape 阶段写入本地 TSDB 的普通采集标签；本地直接查询时不要假设它一定存在。
  外部标签不会覆盖同名原始标签。副本标签的注入方式应以当前 Prometheus Operator/Thanos 版本和 CRD 为准，不要假设 $(POD_NAME) 会自动展开。
```

### Q13：Prometheus 的 scrape_timeout 和 scrape_interval 应该怎么设置？

```
scrape_interval：两次采集之间的间隔
scrape_timeout：单次采集等待响应的超时时间

约束：Prometheus 要求 `scrape_timeout <= scrape_interval`；生产通常设置为严格小于，以给调度、网络抖动和处理留出余量。同一 Target 的慢抓取不会简单无限并发堆积，但会造成超时、采样空洞和资源压力。

典型起点（必须结合目标响应时间与 SLO 调整）：
  ┌──────────────┬──────────────────┐
  │ 场景          │ interval / timeout│
  ├──────────────┼──────────────────┤
  │ 普通服务      │ 30s / 10s        │
  │ 高优先级服务  │ 15s / 10s        │
  │ 基础设施      │ 60s / 30s        │
  │ 慢速目标      │ 120s / 60s       │
  │ 联邦/级联     │ 300s / 240s      │
  └──────────────┴──────────────────┘

timeout 太小 → 频繁超时，Target 标记 DOWN
timeout 太大 → 堆积 scrapes，影响整体采集节奏

生产建议：
  先测量 Exporter 响应时间和失败模式，再设置 timeout；应小于 interval 并留有余量，但不存在通用的 1/2 或 1/3 固定公式
```

### Q14：Grafana 图表中突然出现"断崖"现象，可能是什么原因？

```
断崖 = 图表中一段时间的值为 0 或缺失

原因排查：
1. 目标服务重启 → Counter 归零 → rate/increase 自动处理，但 Gauge 会跳变
2. scrape 失败 → 那段时间没有数据点 → Grafana 连线断开
3. 查询使用了 offset（时间漂移导致 gap）
4. 数据超出 retention → 被删除 → 查询这个时间范围返回空
5. WAL 损坏后重放 → 部分数据丢失

排查方法：
  Grafana → 点击图表 → Inspect → Data → 查看原始数据点的时间分布
  Prometheus UI → /targets → 确认对应时间段 scrape 是否成功
  kubectl logs prometheus-k8s-0 → 搜索对应时间段的错误日志
```

### Q15：为什么说 Prometheus 不适合做精确计费统计？

```
原因：
1. Pull 模型无法记录区间内每个事件的精确发生时间
   → 持续存在的 Counter 增量会累计到下一次成功抓取，不会仅因 scrape interval 而丢失
   → 但进程在两次抓取之间重启、发生多次 Reset、目标短暂消失或抓取失败时，未观测增量可能丢失

2. Counter Reset 处理不精确
   → 进程在两次 scrape 之间重启 2 次 → rate() 只能推算出一次 Reset
   → 中间有部分请求计数会丢失

3. 标签丢失问题
   → /metrics 暴露后，标签变更（如 Pod 重启后 IP 变了）
   → 前后数据无法关联

4. Staleness 与目标消失
   → 抓取失败时会处理本轮消失的旧系列；目标从服务发现消失时会延迟写 stale marker
   → 只有缺少 stale marker 时，即时查询才使用默认约 5 分钟 lookback 作为兜底

替代方案（精确计费）：
  - 应用直接写数据库（每个事件一条记录）
  - 用 Kafka/消息队列缓冲后入库
  - Prometheus 只用做趋势分析和告警，不用做计费
```

---

## 第十三章 数据采集深度解析（Scrape 生命周期）

> 理解 Scrape 的内部机制是从"会用 Prometheus"到"精通 Prometheus"的分水岭。

### 1 单次 Scrape 的完整过程

```
对于一个 Target 的单次 scrape 过程：

Step 1: 连接建立
  Prometheus → 从 SD 获取 Target 的地址与抓取参数
  → 在 scrape_timeout 约束内完成 DNS、连接、TLS、响应读取与解析
  → 发送 GET /metrics（HTTP 版本与连接复用由客户端和目标共同决定）

Step 2: 响应解析
  → 读取 HTTP Response Body（text/plain）
  → 逐行扫描（Scanner），解析格式：
    metric_name{label1="v1",label2="v2"} value [timestamp]
  → 每解析完一个样本就交给 Append Queue

Step 3: 时间戳处理
  → honor_timestamps=true 时，Exporter 显式时间戳可被采用；未提供时使用抓取时间
  → 过旧、过新或超出允许乱序窗口的样本可能被拒绝，具体受 TSDB 配置和版本影响
  → 默认要求同一时间序列近似按时间递增；可配置有限 out-of-order window

Step 4: 追加到存储
  → 样本经 appender 写入 Head，并追加到 WAL 用于崩溃恢复
  → Head 中形成 chunk，随后切块并持久化为不可变 Block
  → 不要把内部时序简化成每个样本严格“先落盘完成、再写内存”的同步事务

Step 5: 健康检查
  → scrape 成功 → 当前轮 up=1
  → scrape 失败 → 当前轮 up=0，通常等待下一个 scrape 周期
  → 抓取失败和 Target 从服务发现消失会触发不同的 stale 处理路径

Rules 独立调度：
  → Rules 不属于单次 scrape 的固定 Step 6
  → 由 evaluation_interval 或 Rule Group interval 触发
  → 同一 Group 内顺序评估；跨 Group 不保证顺序
  → Firing 告警由 Prometheus 发送给 Alertmanager
```

### 2 数据保鲜与 Stale Marker

```
Stale Marker（过期标记）机制需要区分三类场景：

1. Target 仍在服务发现中，但本轮 scrape 失败：
   → `up` 变为 0，并为本轮缺失的旧系列写入 stale marker，使即时查询不继续沿用旧值。
2. Target 从服务发现中消失：
   → Prometheus 会延迟写入 stale marker，以容忍短暂发现抖动；若 Prometheus 在此期间重启，该延迟标记可能无法写入。
3. 没有 stale marker 可用：
   → 即时查询使用约 5 分钟 lookback 作为兜底，超过窗口后不再返回旧样本。

作用：避免目标或某条系列消失后，查询长期沿用最后一个旧值。具体时机应通过“抓取失败、目标消失、Prometheus 重启”三组实验验证。
```

### 3 乱序数据处理

```
正常情况：每个 scrape 的时间戳是单调递增的

乱序场景：
  - 应用在 /metrics 中人为暴露了时间戳（某些 IoT/边缘场景）
  - Prometheus 时钟回调（NTP 导致）
  - 网络延迟导致旧数据晚到达

处理方式：
  Prometheus 2.39+ 支持 outOfOrderTimeWindow：
    tsdb:
      outOfOrderTimeWindow: 10m    # 允许 10 分钟内乱序
  
  超过窗口 → 丢弃并计数 prometheus_tsdb_out_of_order_samples_total

  生产建议：
  - 默认保持乱序窗口关闭；只有 Remote Write Receiver、边缘补传等确有乱序需求时再启用
  - 窗口越大会增加 Head 内存与查询复杂度，应按实际迟到分布选择
  - 监控 out-of-order 接收/拒绝指标；异常可能来自显式时间戳、时钟、补传或链路问题
```

---


> - `K8s_Advanced.md` 第十九章 — Prometheus + Grafana + Loki 部署
> - `K8s_Advanced.md` 第二十七章 — CNI 内部原理 / Istio Helm、Revision 与 GitOps 安装
> - `K8s_Advanced.md` 第二十八章 — ServiceMonitor / PodMonitor 全部字段与生产案例
> - `K8s_Advanced.md` 第二十九章 §8 — 蓝鲸监控 (bkmonitor) 与 TKE 集成
>
> **文档版本**: v2.0（面试强化版）  
> **定位**：Prometheus 全链路可观测性 — 面试专项（数据流 → 指标类型 → 采集细节 → 查询 → 告警 → 调优 → 高频问答）  
> **v2.0 新增**：术语速查表；端到端数据流转全景图（六阶段详细拆解）；四种核心指标类型深度解析（Counter/Gauge/Histogram/Summary 原理 + 面试陷阱）；指标暴露格式详解（Exposition Format + Pull vs Push 对比）；面试高频 15 问（含 Counter Reset、基数爆炸、HA 一致性、OOM 排查、Stale Marker 等）；第十二章 Scrape 生命周期深度解析  
> **v1.2 新增**：第三章 ServiceMonitor 端到端快速上手示例；第十章 PromQL 实战速查  
> **v1.1 新增**：第九章 服务网格可观测性（Istio + Prometheus 集成 / 标准指标 / ServiceMonitor 采集 / 仪表盘 / 分布式追踪 / 告警规则）  
> **适合**：准备面试的中高级 SRE / 需要深入理解 Prometheus 内部原理的运维工程师
