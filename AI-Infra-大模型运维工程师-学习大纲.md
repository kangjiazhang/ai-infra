# AI Infra / 大模型运维工程师 学习大纲

> 适用对象：已有 K8s / Helm / ArgoCD / Prometheus / Linux 运维经验的 DevOps、SRE 工程师
> 目标岗位：大模型运维工程师、AI Infra 工程师、LLM 平台工程师
> 总周期：13 周（约 90 天），建议每天 2 小时、每周 6 天
> 使用方式：每个条目前的 `[ ]` 学完后改成 `[x]`，产出物统一放进一个 Git 仓库

---

## 零、整体结构

| 模块 | 周次 | 定位 | 你的起点 |
|---|---|---|---|
| M0 前置能力对齐 | 第 0 周 | 盘点已有能力、补 Python 短板 | 大部分已具备 |
| M1 大模型基础原理 | 第 1-2 周 | 建立 LLM 推理直觉 | 全新，需硬啃 |
| M2 推理引擎与性能 | 第 3-5 周 | 核心技术护城河 | 全新，重点投入 |
| M3 GPU 与硬件基建 | 第 6 周 | 从「通用运维」跨到「AI 运维」的分水岭 | 全新 |
| M4 K8s 上的模型服务 | 第 7-8 周 | 你的舒适区，快速通过 | 已有 80% 能力 |
| M5 GPU 调度与平台化 | 第 9-10 周 | 平台工程能力 | 部分可迁移 |
| M6 可观测性与成本治理 | 第 11-12 周 | 差异化卖点 | 监控经验可迁移 |
| M7 作品集与面试 | 第 13 周 | 转化为求职资本 | — |

**核心取舍原则：**
- 必学：LLM 推理原理、GPU 显存、推理引擎、GPU 调度、可观测性
- 会用：PyTorch 基础、向量库、LoRA 概念、RAG 链路
- 跳过：手推反向传播、优化器细节、分布式训练通信原语、论文复现

---

## M0 · 前置能力对齐（第 0 周）

### 已具备（确认即可，不重复学）
- [x] Linux / Shell / 系统排查
- [x] Docker / 容器镜像 / 镜像仓库
- [x] Kubernetes 核心对象（Deployment / StatefulSet / Service / ConfigMap / Secret）
- [x] Helm chart 编写与多环境 values 管理
- [x] ArgoCD GitOps 同步
- [x] Prometheus + Grafana 监控告警
- [x] Python 脚本能力（运维脚本、CAS、备份等）

### 需要补齐
- [ ] Python `async` / `await` 异步编程（推理服务几乎全异步）
- [ ] FastAPI 基础：路由、依赖注入、pydantic 数据校验、流式响应 SSE
- [ ] Python 类型标注与 `pydantic v2`
- [ ] 能读懂第三方库源码（后续要读 vLLM）
- [ ] NVIDIA 驱动 / CUDA / cuDNN / NCCL 各自是什么、版本兼容关系

**产出物**：一个 FastAPI 小服务，支持 SSE 流式返回，作为后续模型网关的骨架。

---

## M1 · 大模型基础原理（第 1-2 周）

### 1.1 语言模型是怎么工作的
- [ ] Tokenizer：BPE / SentencePiece，一个中文字≈多少 token
- [ ] Embedding 与词向量
- [ ] Attention 机制（QKV 三矩阵在干什么，为什么复杂度是 O(n²)）
- [ ] Multi-Head Attention、FFN、LayerNorm、残差连接
- [ ] Decoder-only 架构与自回归生成
- [ ] 位置编码：绝对位置 / RoPE / 长上下文外推

### 1.2 推理过程（运维最关键的一节）
- [ ] Prefill 阶段 vs Decode 阶段的本质差异
  - Prefill：计算密集（compute-bound），一次处理全部 prompt
  - Decode：显存带宽密集（memory-bound），逐 token 生成
- [ ] KV Cache 是什么、为什么它是显存杀手
- [ ] 采样策略：greedy / temperature / top-k / top-p / repetition penalty
- [ ] 上下文窗口（context window）与其对显存的影响
- [ ] 结构化输出、function calling 的底层实现

### 1.3 关键指标定义（面试必问）
- [ ] TTFT（Time To First Token）——受 prefill 影响
- [ ] TPOT / ITL（每 token 输出时间）——受 decode 影响
- [ ] Throughput：请求级 QPS vs token 级 tokens/s
- [ ] 吞吐与延迟的权衡关系（batch 越大吞吐越高但延迟越差）
- [ ] Goodput 概念（满足 SLO 前提下的有效吞吐）

### 1.4 显存计算（务必手算一遍）
- [ ] 模型权重显存 = 参数量 × 每参数字节数（FP16=2B, INT8=1B, INT4=0.5B）
- [ ] KV Cache 显存 = 2 × layers × kv_heads × head_dim × seq_len × batch × dtype_bytes
- [ ] 激活值与框架开销（预留 10-20%）
- [ ] GQA / MQA 如何大幅降低 KV Cache
- [ ] 实战：7B / 14B / 32B / 72B 模型分别需要什么卡

**学习资源**
| 资源 | 类型 | 备注 |
|---|---|---|
| Karpathy《Intro to Large Language Models》 | 视频 1h | 第一天就看，建立全局直觉 |
| Karpathy《Let's build GPT from scratch》 | 视频 2h | 看懂数据流动，不必手敲 |
| Jay Alammar《The Illustrated Transformer》 | 图解文章 | 配合视频看 |
| Chip Huyen《AI Engineering》第 2、9 章 | 书 | 中文版《AI工程：大模型应用开发实战》 |
| Hugging Face NLP Course 第 1-2 章 | 在线课 | 免费 |

**产出物**
- [ ] `vram_calculator.py`：输入模型规格 + 并发 + 上下文长度，输出显存需求
- [ ] 一篇笔记《一次 LLM 推理请求的完整生命周期》

---

## M2 · 推理引擎与性能优化（第 3-5 周）

### 2.1 vLLM 核心机制
- [ ] PagedAttention：像 OS 分页一样管理 KV Cache，解决内存碎片
- [ ] Continuous Batching（连续批处理）vs 静态 batching
- [ ] Chunked Prefill：把长 prompt 切块，避免长请求卡住整个服务
- [ ] Prefix Caching：多请求共享相同前缀的 KV Cache
- [ ] CUDA Graph 与算子融合
- [ ] 部署方式：pip 直装 / Docker / OpenAI 兼容 API server

### 2.2 关键启动参数（逐个做对照实验）
- [ ] `--gpu-memory-utilization`：显存占用比例上限
- [ ] `--max-model-len`：最大上下文长度
- [ ] `--max-num-seqs`：最大并发序列数
- [ ] `--max-num-batched-tokens`：单 batch token 上限
- [ ] `--tensor-parallel-size`（TP）：单机多卡切分
- [ ] `--pipeline-parallel-size`（PP）：跨机切分
- [ ] `--block-size`、`--swap-space`、`--cpu-offload-gb`
- [ ] `--enable-prefix-caching`、`--enable-chunked-prefill`

### 2.3 量化
- [ ] 量化基本原理：FP16 / BF16 / FP8 / INT8 / INT4
- [ ] AWQ（激活感知权重量化）
- [ ] GPTQ（逐层量化）
- [ ] FP8（Hopper 及以后架构原生支持）
- [ ] KV Cache 量化
- [ ] 权衡：显存 ↓ / 吞吐 ↑ / 精度 ↓，什么场景可接受

### 2.4 进阶推理优化
- [ ] PD 分离（Prefill / Decode Disaggregation）：两阶段特性不同，分开部署提升利用率
- [ ] 投机解码（Speculative Decoding）：小模型草稿 + 大模型验证
- [ ] Multi-LoRA Serving：一个基座 + 多个 LoRA 适配器服务多业务
- [ ] 分布式 KV Cache（LMCache 等）
- [ ] Flash Attention / Flash Decoding

### 2.5 引擎横向对比
- [ ] vLLM —— 生态最全，事实标准
- [ ] SGLang —— RadixAttention，复杂 prompt 结构场景更强
- [ ] TensorRT-LLM —— NVIDIA 官方，极致性能但编译门槛高
- [ ] Hugging Face TGI
- [ ] Ollama / llama.cpp —— 本地与边缘场景
- [ ] 选型决策：什么场景用哪个

### 2.6 压测方法论
- [ ] `vllm bench serve` 用法
- [ ] 其他工具：`genai-perf`、`locust`
- [ ] 压测变量控制：输入长度、输出长度、并发数
- [ ] 报告要素：TTFT p50/p95/p99、TPOT、tokens/s、GPU 利用率

**学习资源**
| 资源 | 类型 |
|---|---|
| vLLM 官方文档（Docs + Design 部分） | 文档，必读 |
| vLLM GitHub 源码（engine / scheduler / worker） | 源码 |
| PagedAttention 论文（Efficient Memory Management for LLM Serving） | 论文，读摘要+图即可 |
| 李孟轩 vLLM Meetup《你的算力用的好么》 | 视频分享 |
| jimmysong.io kubernetes-handbook · AI Native 章节 | 中文文档 |

**产出物**
- [ ] `benchmark/` 目录：参数对照实验脚本 + 结果 CSV + Grafana 截图
- [ ] 一份《vLLM 参数调优实验报告》，含至少 3 组对照数据
- [ ] 一份《FP16 vs AWQ vs GPTQ-Int4 量化对比表》

---

## M3 · GPU 与硬件基建（第 6 周）

### 3.1 GPU 硬件常识
- [ ] 显存（HBM）容量与带宽为什么比算力更常成为瓶颈
- [ ] 主流卡对比：T4 / A10 / L20 / L40S / A100 / H20 / H100 / H800
- [ ] 算力单位：FP16/BF16/FP8 TFLOPS，稀疏算力的水分
- [ ] 卡间互联：PCIe vs NVLink vs NVSwitch，对 TP 性能的影响
- [ ] 多机互联：RDMA / RoCE / InfiniBand 基础
- [ ] MIG（Multi-Instance GPU）硬件级切分

### 3.2 软件栈
- [ ] NVIDIA Driver / CUDA Toolkit / cuDNN / NCCL 各层职责
- [ ] 版本兼容矩阵：驱动版本 ↔ CUDA 版本 ↔ vLLM/PyTorch 版本
- [ ] `nvidia-container-toolkit` 与容器 GPU 直通原理
- [ ] `nvidia-smi` 全字段解读：Util / Memory / Power / ECC / Xid
- [ ] NVML 与 `pynvml` 编程接口
- [ ] Xid 错误码排查（掉卡、ECC 错误、显存故障）

### 3.3 K8s GPU 接入
- [ ] NVIDIA device plugin 工作原理
- [ ] NVIDIA GPU Operator（一站式部署驱动/toolkit/plugin/dcgm）
- [ ] `nvidia.com/gpu` 资源如何被 kubelet 分配
- [ ] Node Feature Discovery 与 GPU 节点打标
- [ ] GPU 节点污点/容忍与亲和调度

**产出物**
- [ ] 一份《GPU 机型选型与成本对照表》（含云上按量/包月/抢占式价格）
- [ ] 一份《GPU 故障排查手册》（Xid 码、OOM、掉卡、驱动不匹配）

---

## M4 · Kubernetes 上的模型服务（第 7-8 周）

> 这块你已有 80% 能力，重点是「把已有技能套到 GPU 工作负载上」，快速通过。

### 4.1 部署与编排
- [ ] 编写 vLLM 的 Helm chart（复用你现有的 chart 结构习惯）
- [ ] 多环境 values 拆分（QA / 压测 / 预发 / 正式）
- [ ] 接入 ArgoCD，实现 GitOps 同步
- [ ] 模型权重分发方案：PVC / 对象存储 / initContainer 预热 / 镜像内置
- [ ] 冷启动优化（模型加载动辄几分钟，这是运维大痛点）
- [ ] 探针设计：`startupProbe` 必须给足时间，`readinessProbe` 打真实推理

### 4.2 服务暴露与流量
- [ ] Service / Ingress / CLB 接入（复用你已有的 CLB 经验）
- [ ] 长连接与 SSE 流式响应对网关超时的要求
- [ ] 长请求的优雅下线（`terminationGracePeriodSeconds` + preStop）
- [ ] 滚动更新策略：GPU 资源紧张时 `maxSurge` 怎么设

### 4.3 弹性伸缩
- [ ] HPA 基于自定义指标（GPU 利用率 / 排队请求数 / TTFT）
- [ ] KEDA 事件驱动扩缩容
- [ ] 为什么 CPU 利用率对 LLM 服务是无效指标
- [ ] 缩容到零与冷启动的矛盾

### 4.4 多模型管理
- [ ] LiteLLM 做统一 OpenAI 兼容网关与模型路由
- [ ] KServe / Seldon 的 InferenceService 抽象
- [ ] 模型版本管理与灰度（金丝雀发布、A/B 测试）
- [ ] 多租户隔离与限流（按 token 数而非请求数限流）

**产出物**
- [ ] 一个完整的 `helm/vllm-inference/` chart，支持多环境
- [ ] 一份《LLM 服务发布 SOP》（含发版顺序、回滚步骤、检查清单）

---

## M5 · GPU 调度与平台化（第 9-10 周）

### 5.1 GPU 共享与虚拟化
- [ ] 为什么需要 GPU 共享（一张 80G 卡跑 7B 模型极度浪费）
- [ ] HAMi：显存与算力软隔离，K8s 原生
- [ ] NVIDIA MPS（Multi-Process Service）
- [ ] MIG 硬件切分（A100/H100 支持）
- [ ] 三种方案对比：隔离性 / 灵活性 / 性能损耗

### 5.2 批调度器
- [ ] Volcano：Gang Scheduling（多卡任务要么全给要么不给）
- [ ] Kueue：队列化与配额管理
- [ ] 队列 / 优先级 / 抢占 / 公平共享
- [ ] Binpack vs Spread 调度策略对 GPU 碎片的影响
- [ ] 拓扑感知调度（NVLink 亲和）

### 5.3 推理网关与路由（新兴热点）
- [ ] K8s Gateway API Inference Extension
- [ ] Prefix-cache 感知路由（把相同前缀的请求路由到同一实例）
- [ ] 负载感知路由（按 KV Cache 使用率而非轮询）
- [ ] llm-d / AIBrix 等推理平台项目

### 5.4 训练侧了解（不深入）
- [ ] Ray / Ray Serve 基本概念
- [ ] Kubeflow / Training Operator 是干什么的
- [ ] 分布式训练的检查点（checkpoint）与故障恢复
- [ ] 只需能和算法团队对话，不必自己搭训练平台

**产出物**
- [ ] 在测试集群实现「一卡多服务」并出一份隔离性验证报告
- [ ] 一张《AI 推理平台架构图》（含网关、调度、监控、存储各层）

---

## M6 · 可观测性与成本治理（第 11-12 周）

> 这是大模型运维区别于普通 SRE 的核心价值，也是你监控经验能直接迁移的地方。

### 6.1 GPU 层监控
- [ ] `dcgm-exporter` 部署与关键指标
  - `DCGM_FI_DEV_GPU_UTIL`（利用率，注意它有欺骗性）
  - `DCGM_FI_PROF_SM_ACTIVE` / `PIPE_TENSOR_ACTIVE`（真实算力占用）
  - `DCGM_FI_DEV_FB_USED` / `FB_FREE`（显存）
  - `DCGM_FI_DEV_POWER_USAGE`、`GPU_TEMP`
  - `DCGM_FI_DEV_XID_ERRORS`（硬件故障）
- [ ] Grafana GPU 面板搭建
- [ ] 告警规则：显存打满、掉卡、温度过高、利用率长期为 0（资源闲置）

### 6.2 推理服务层监控
- [ ] vLLM 原生 `/metrics` 指标（Prometheus 格式）
  - `vllm:num_requests_running` / `waiting`（排队深度）
  - `vllm:gpu_cache_usage_perc`（KV Cache 使用率，最重要的容量指标）
  - `vllm:time_to_first_token_seconds`
  - `vllm:time_per_output_token_seconds`
  - `vllm:prompt_tokens_total` / `generation_tokens_total`
- [ ] SLO 定义：TTFT p95 < ?s，可用性 99.x%
- [ ] 容量规划：从 KV Cache 使用率推算还能承载多少并发

### 6.3 应用层可观测（LLM 特有）
- [ ] Langfuse：trace 每次请求的 prompt / completion / token / 耗时 / 成本
- [ ] OpenTelemetry GenAI 语义约定
- [ ] 幻觉与质量回归监控（evals 概念，了解即可）
- [ ] 敏感信息（PII）与内容安全审计日志

### 6.4 成本治理
- [ ] 单位成本计算：¥ / 百万 token、¥ / 请求
- [ ] 成本归因：按业务方 / 租户 / 模型拆账
- [ ] 降本手段清单
  - 量化（显存降一半，同卡跑更大模型）
  - Prefix caching（重复前缀不重复计算）
  - 语义缓存（GPTCache）
  - 模型路由（简单请求走小模型）
  - 抢占式实例 / 闲时缩容
  - GPU 共享提升单卡密度
- [ ] GPU 利用率提升前后的量化对比（这是最有说服力的简历数据）

**产出物**
- [ ] 一套完整 Grafana Dashboard JSON（GPU 层 + 服务层）
- [ ] 一份 Prometheus 告警规则 YAML
- [ ] 一份《推理成本分析报告》：优化前后单位 token 成本对比

---

## M7 · 作品集与求职（第 13 周）

### 7.1 作品集整理
- [ ] 建一个 GitHub 仓库，包含：
  - 架构图（整体推理平台设计）
  - Helm chart（可直接部署）
  - 显存估算工具
  - 压测脚本 + 完整实验数据
  - Grafana Dashboard JSON + 告警规则
  - README：问题背景 → 方案 → 量化收益
- [ ] 把关键数据提炼成 3 条简历要点（必须带数字）
  - 例：「通过 AWQ 量化 + prefix caching，单卡并发从 X 提升至 Y，单位 token 成本下降 Z%」

### 7.2 面试高频问题自测
- [ ] 讲一遍 LLM 推理的 prefill 和 decode 有什么不同，各自瓶颈在哪
- [ ] KV Cache 怎么算显存？为什么它限制了并发？
- [ ] PagedAttention 解决了什么问题？
- [ ] 一个 32B 模型要用什么卡？为什么？
- [ ] 为什么不能用 CPU 利用率给 LLM 服务做 HPA？该用什么指标？
- [ ] GPU 利用率 100% 但吞吐很低，怎么排查？
- [ ] 怎么做到发版不中断正在生成的长请求？
- [ ] 量化会带来什么代价？怎么验证质量没退化？
- [ ] 一张 A100 上跑三个业务的模型，怎么做隔离？
- [ ] 老板说推理成本太高，你有哪些降本手段？按收益排序
- [ ] Xid 错误、掉卡怎么处理？
- [ ] PD 分离为什么能提升利用率？什么规模才值得做？

### 7.3 长期跟进渠道
- [ ] 订阅 vLLM / SGLang GitHub Release
- [ ] 关注 KubeCon / vLLM Meetup 相关分享
- [ ] 定期读 Chip Huyen、Eugene Yan、Hamel Husain 的博客
- [ ] 中文：宋净超（云原生+AI Native）、宝玉（AI 工程）、何文斯（大模型中间件）、HAMi 社区

---

## 附录 A · 资源总清单

### 书
| 书名 | 优先级 | 用法 |
|---|---|---|
| Chip Huyen《AI Engineering》/ 中文《AI工程：大模型应用开发实战》 | 必读 | 通读，重点第 2、3、4、9、10 章 |
| Chip Huyen《Designing Machine Learning Systems》/《机器学习系统设计》 | 推荐 | 补 MLOps 方法论 |
| 《Designing Data-Intensive Applications》(DDIA) | 参考 | 当工具书查 |

### 视频 / 课程
| 资源 | 时长 | 优先级 |
|---|---|---|
| Karpathy《Intro to Large Language Models》 | 1h | 第一优先，Day 1 |
| Karpathy《Let's build GPT from scratch》 | 2h | 高 |
| DeepLearning.AI《LLMOps》（Google Cloud） | 1-2h | 高，免费 |
| 杜克大学 LLMOps Specialization（Coursera） | 38h+ | 中，可旁听 |
| Hugging Face NLP Course | — | 中，免费 |

### 网站 / 仓库
| 资源 | 内容 |
|---|---|
| `github.com/chiphuyen/aie-book` | AI Engineering 配套实战仓库，免费 |
| vLLM 官方文档 | 必读，尤其 Design 与 Optimization 部分 |
| `jimmysong.io` kubernetes-handbook | 中文，含 AI Native / vLLM in K8s |
| `project-hami.io` | GPU 虚拟化中文文档与 Meetup 回顾 |
| `langfuse.com/library` | AI 工程精选资源库 |
| `devopsschool.org` LLMOps Roadmap | 免费分阶段路线 |
| NVIDIA GPU Operator 文档 | GPU 接入 K8s 权威文档 |
| LLMOps.Space | 社区 + 免费 Meetup 录播 |

### 关键开源项目（按学习顺序）
1. vLLM —— 推理引擎，重点
2. SGLang —— 备选引擎
3. dcgm-exporter —— GPU 监控
4. NVIDIA GPU Operator —— GPU 接入
5. HAMi —— GPU 虚拟化
6. Volcano / Kueue —— 批调度
7. LiteLLM —— 模型网关
8. KServe —— 推理平台抽象
9. Langfuse —— LLM 可观测
10. Ray —— 分布式（了解）

---

## 附录 B · 明确跳过清单（避免踩坑浪费时间）

以下内容对「大模型运维工程师」岗位性价比极低，除非有明确需要，**主动跳过**：

- 手推反向传播、梯度下降数学证明
- 各类优化器（Adam / AdamW / Lion）的公式细节
- 从零实现 Transformer（看懂即可，不必手敲）
- 论文复现、SOTA 追逐
- 预训练全流程与数据清洗管线
- Prompt 技巧大全（了解基本原则即可，这是算法/产品的活）
- 深入的 RLHF / DPO 对齐算法
- 深度学习理论课程（吴恩达 DL 系列可跳过前 3 门）

**判断标准：这个知识会不会出现在「服务挂了、成本高了、卡不够了」的排查现场？** 不会，就跳过。

---

## 附录 C · 每周节奏建议

| 时间 | 安排 |
|---|---|
| 周一至周五（每天 2h） | 1h 学理论/看文档 + 1h 动手实操 |
| 周六（3-4h） | 集中做本周的产出物（脚本 / chart / 报告） |
| 周日 | 休息，或补看视频 |

**避坑提醒**
1. **不要只看不做。** 每个模块都必须有产出物落到 Git，否则两周后全忘。
2. **M4 是你的舒适区，别恋战。** K8s/Helm/ArgoCD 你已经熟，两周内快速通过，把时间挪给 M2 和 M6。
3. **没有 GPU 就用云上抢占式实例。** 不用时开启「节省停机」保留磁盘，成本可压到极低；磁盘建议 100G 以上，模型文件很大。
4. **读 vLLM 源码当长期习惯。** 它是 Python、推理原理、GPU 三块知识的最佳交叉教材。
5. **所有实验都记录数据。** 简历上「提升 40% 吞吐」比「熟悉 vLLM」有说服力得多。
