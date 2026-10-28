# 机器学习系统 SRE 工程师（Seed）面试准备指南

> 目标岗位：字节跳动 Seed 团队 — 大模型训练/推理基础设施运维  
> 本文档覆盖 JD 拆解、技术栈准备、生产常见问题、高频面试题及场景演练

---

## 目录

- [术语速查表](#术语速查表) **核心术语与背景知识**
- [第一章](#第一章-jd-拆解与能力模型) JD 拆解与能力模型
- [第二章](#第二章-k8s-与-gpu-调度生产必知) K8s 与 GPU 调度（生产必知）
- [第三章](#第三章-gpu-硬件与故障诊断) GPU 硬件与故障诊断
- [第四章](#第四章-分布式训练运维) 分布式训练运维
- [第五章](#第五章-网络与存储) 网络与存储
- [第六章](#第六章-可观测性与告警) 可观测性与告警
- [第七章](#第七章-资源管理与成本优化) 资源管理与成本优化
- [第八章](#第八章-推理服务部署) 推理服务部署
- [第九章](#第九章-多地域容灾与部署) 多地域容灾与部署
- [第十章](#第十章-sre-最佳实践) SRE 最佳实践
- [第十一章](#第十一章-go-语言-sre-开发) Go 语言 SRE 开发
- [第十二章](#第十二章-高频面试场景题) 高频面试场景题
- [第十三章](#第十三章-模拟面试问答) 模拟面试问答
- [第十四章](#第十四章-行为面试准备) 行为面试准备
- [第十五章](#第十五章-速查表) 速查表

---

## 术语速查表

> 以下是在 ML SRE 面试和日常工作中频繁出现的核心术语，按类别整理，建议在阅读正文前先通览一遍，建立全局概念。

### 一、GPU 硬件与驱动

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **CUDA** | Compute Unified Device Architecture | NVIDIA 的并行计算平台，提供 GPU 编程模型（C/C++ 扩展）。所有深度学习框架底层都依赖 CUDA |
| **cuDNN** | CUDA Deep Neural Network library | NVIDIA 为深度神经网络优化的 GPU 加速库，提供卷积、池化、归一化等算子 |
| **ECC** | Error Correcting Code | 纠错码。GPU 显存上的错误检测与纠正机制。单比特错误可自动纠正（CE），双比特错误不可纠正（UE，需要停机） |
| **Xid** | GPU Error Identifier | NVIDIA 驱动层错误编码，类似 Linux 的 errno。每个编号对应特定的硬件/驱动故障类型 |
| **NVLink** | NVIDIA NVLink | GPU 之间的高速直连总线（如 H100 NVLink 4.0 带宽 900 GB/s），替代传统 PCIe 用于 GPU-GPU 通信 |
| **NVSwitch** | NVIDIA NVSwitch | 连接多张 GPU 的交换芯片，使任意两张 GPU 都能以 NVLink 全速通信（全互联拓扑） |
| **SM** | Streaming Multiprocessor | GPU 的计算核心单元，类似 CPU 的"核"。H100 有 132 个 SM，每个 SM 包含 CUDA Core / Tensor Core |
| **Tensor Core** | - | GPU 中的专用矩阵乘加单元，FP16/BF16/TF32/FP8 精度下提供数倍于普通 CUDA Core 的算力 |
| **MIG** | Multi-Instance GPU | A100/H100/A6000 支持的硬件级分区技术，将一张物理 GPU 切分成多个独立实例，每个有专属显存和算力 |
| **MPS** | Multi-Process Service | CUDA 的软件级多进程共享机制，允许多个 CUDA 应用共享一张 GPU（隔离性弱于 MIG） |
| **DCGM** | Data Center GPU Manager | NVIDIA 官方 GPU 监控工具，暴露 GPU 遥测指标（温度、功耗、ECC、利用率等）给 Prometheus |
| **GPU Operator** | - | NVIDIA 在 K8s 上管理 GPU 全生命周期（驱动安装、Device Plugin、DCGM、MIG）的 Helm Chart/Operator |
| **Device Plugin** | - | K8s 插件机制，将 GPU 作为扩展资源（`nvidia.com/gpu`）注册到 kubelet，使 Pod 能请求 GPU |
| **Time-slicing** | GPU Time-Slicing | GPU 时分复用机制，多个容器轮转使用同一张 GPU 的时间片。隔离性弱但有共享弹性 |
| **Persistence Mode** | - | NVIDIA 驱动模式。开启后 GPU 驱动在无应用连接时也保持加载，避免反复初始化开销（生产必须开启） |

### 二、分布式训练

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **DDP** | Distributed Data Parallel | 数据并行。每张 GPU 持有完整模型副本，数据和梯度在各 GPU 间同步（AllReduce），适合模型能放入单卡 |
| **FSDP** | Fully Sharded Data Parallel | 全分片数据并行（PyTorch 对 ZeRO 的实现）。模型参数、梯度、优化器状态分片到各 GPU，用时空换算力 |
| **ZeRO** | Zero Redundancy Optimizer | DeepSpeed 提出的优化器冗余消除策略。ZeRO-1 分片优化器状态，ZeRO-2 加梯度分片，ZeRO-3 加参数分片 |
| **TP** | Tensor Parallelism | 张量并行。把模型中单层的矩阵运算切分到多张 GPU 上并行执行，层内通信量大，适合单层超出单卡显存 |
| **PP** | Pipeline Parallelism | 流水线并行。把模型按层切分成多个 Stage，每张 GPU 负责连续的若干层，batch 以流水线方式在 stage 间流转 |
| **3D Parallelism** | TP + PP + DP | 三种并行的组合策略（如 GPT-3/4 的训练方式），可在不同维度灵活配置以平衡显存和通信 |
| **Gradient Checkpointing** | 梯度检查点（Activation Recomputation） | 反向传播时丢弃部分中间激活值，需要时重新计算，用约 20% 额外计算换取 ~50% 激活值显存节省 |
| **Mixed Precision** | 混合精度训练 | 前向/反向使用 FP16/BF16 加速，权重和优化器状态保留 FP32 副本以保证精度 |
| **TorchElastic** | - | PyTorch 弹性训练模块，支持动态增减 Worker 节点而不中断训练（需要从 checkpoint 恢复） |

### 三、网络通信

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **NCCL** | NVIDIA Collective Communications Library | NVIDIA 的 GPU 集合通信库，实现 AllReduce/AllGather/Broadcast 等原语。是所有分布式训练框架的通信基石 |
| **RDMA** | Remote Direct Memory Access | 远程直接内存访问。网卡直接读写远端内存，绕过 CPU 和内核协议栈，实现微秒级延迟和高带宽 |
| **InfiniBand** | InfiniBand (IB) | 一种高性能计算互连标准，原生支持 RDMA。常用于 HPC 和 AI 训练集群。HDR 200Gb/s，NDR 400Gb/s |
| **RoCE** | RDMA over Converged Ethernet | 在标准以太网上运行 RDMA 的协议。RoCEv1 限于同子网广播域，RoCEv2 支持 IP 路由可用性更高 |
| **GPUDirect RDMA (GDR)** | - | NVIDIA 技术，允许网卡直接读写 GPU 显存，消除 GPU→CPU 内存→网卡的拷贝开销。NCCL_NET_GDR_LEVEL=5 为最高级别 |
| **GID Index** | Global Identifier Index | RoCEv2 中每个 RDMA 设备端口的多个标识符条目。配置错误会导致 NCCL 降级到 TCP，带宽骤降 |
| **PFC** | Priority Flow Control | IEEE 802.1Qbb 无损以太网流控机制。RoCE 网络需要 PFC 保证不丢包，配置不当导致 PAUSE 帧风暴 |
| **ECN** | Explicit Congestion Notification | 显示拥塞通知，配合 DCQCN 算法在 RoCE 网络中做拥塞控制，避免 PFC 触发 |

### 四、推理服务

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **TTFT** | Time To First Token | 用户提交请求到收到第一个输出 token 的时间。衡量推理服务响应速度的关键指标 |
| **TPOT** | Time Per Output Token | 生成阶段每个 token 的平均耗时（不含首 token）。等效为 decode 阶段吞吐的倒数 |
| **PagedAttention** | - | vLLM 提出的显存管理算法。将 KV Cache 按 page 管理（类似 OS 虚拟内存），减少显存碎片，提升吞吐 |
| **Continuous Batching** | 连续批处理 | 推理框架在 decode 循环中动态增减请求，而非等整个 batch 完成后再组新 batch。显著提升 GPU 利用率 |
| **KV Cache** | Key-Value Cache | Transformer 推理时缓存的 Key/Value 矩阵，避免每步重复计算。序列越长 KV Cache 越大，是显存瓶颈 |
| **Chunked Prefill** | 分块预填充 | 将长序列的 prefill 阶段拆成多个小块，与 decode 交织执行，降低首 token 延迟抖动 |
| **Prefix Caching** | 前缀缓存 | 复用多个请求共享的 prompt 前缀对应的 KV Cache 计算结果（如 system prompt），减少重复计算 |

### 五、SRE 方法论

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **SLI** | Service Level Indicator | 服务水平指标。系统服务水平的量化度量，如请求成功率、延迟 P99、GPU 可用率 |
| **SLO** | Service Level Objective | 服务水平目标。SLI 需要达成的目标阈值，如"训练任务成功率 >= 99.5% (月度)" |
| **SLA** | Service Level Agreement | 服务水平协议。违反 SLO 后的商业后果（赔偿等），通常是对外承诺 |
| **Error Budget** | 错误预算 | 1 − SLO，即系统允许的不可用时间/错误次数。错误预算耗尽 → 冻结发布 |
| **MTTR** | Mean Time To Repair | 平均修复时间，衡量故障恢复效率 |
| **MTTD** | Mean Time To Detect | 平均检测时间，衡量监控告警的灵敏度 |
| **RPO** | Recovery Point Objective | 恢复点目标，灾难恢复时可容忍的最大数据丢失量 |
| **RTO** | Recovery Time Objective | 恢复时间目标，灾难发生后恢复到可用状态的最大时间 |

### 六、K8s/调度

| 术语 | 解释 |
|------|------|
| **Gang Scheduling** | 全有或全无调度。一批 Pod 必须全部同时调度成功才能运行，任何一个失败则全部释放并重试 |
| **Taint/Toleration** | K8s 的节点排斥机制。Taint 打在节点上表示"拒绝"，Toleration 打在 Pod 上表示"容忍" |
| **DaemonSet** | 确保每个（或部分）节点运行一个 Pod 副本，常用于 GPU 驱动、Device Plugin、监控 Agent |
| **CRD** | Custom Resource Definition，K8s 扩展 API，允许自定义资源类型，如 Volcano 的 `Job.batch.volcano.sh` |
| **Operator** | 结合 CRD + Controller 实现自动化运维的模式，如 GPU Operator 管理 GPU 全生命周期 |
| **Informer** | client-go 核心机制。List+Watch API Server，将对象缓存到 Indexer，通过 EventHandler 和 WorkQueue 分发事件 |
| **Kata Containers** | 轻量级虚拟机容器运行时，每个容器运行在独立 kernel 中，提供 VM 级安全隔离 |
| **Topology Manager** | K8s kubelet 组件，保证 Pod 的 CPU/内存/设备分配在同一 NUMA Node，减少跨 NUMA 延迟 |

---

## 第一章 JD 拆解与能力模型

### 1 JD 五维度拆解

| 方向 | 关键词 | 权重 | 面试题型 | 核心考察点 |
|------|--------|------|----------|-----------|
| ML 系统稳定性 | 大模型训练/部署/推理链路 | 🔴 高 | 场景题 + 系统设计 | 你能否保障一个千卡级别训练集群的稳定运行？ |
| GPU 资源管理与成本 | 资源规划、预算、数据驱动 | 🔴 高 | 场景题 + 方案设计 | 你能否用数据说服管理层采购多少 GPU，并把利用率做高？ |
| 稳定性治理与效率 | 集群治理、利用率、平台化 | 🟡 中 | 场景题 + 项目复盘 | 你能否把运维经验沉淀为平台能力，让更多人自助使用？ |
| 多地域容灾与部署 | 多机房、容灾、机器治理 | 🟡 中 | 架构设计题 | 你能否设计一套跨机房容灾方案，让训练不因单机房故障中断？ |
| 日常运维与排障 | 问题排查、业务支持 | 🟢 基础 | 排障题 | 面对 GPU 故障/训练 Hang/推理延迟飙升，你的排查思路是什么？ |

**面试重点解读**：
- 🔴 高权重方向是面试的主战场，面试官会追问到较深层次，**80% 面试时间集中在 ML 系统稳定性和 GPU 资源管理这两个维度**
- 🟡 中权重方向是加分项，体现你的架构视野和平台化思维，回答得好会拉开差距
- 🟢 基础方向是门槛，如果不能快速定位常见 GPU 故障，前两个方向答得再好也会被否定
- **Seed 团队的特色**：比普通 SRE 更侧重 ML 领域知识，比算法工程师更侧重系统稳定性和运维效率

### 2 所需能力图谱

```
ML SRE 能力模型
├── 基础运维能力（Linux / 网络 / 存储）
├── K8s 深度能力（调度 / Operator / CRD）
├── GPU 专业知识（硬件 / 驱动 / 通信）
├── ML 框架理解（PyTorch / NCCL / 并行策略）
├── 编程能力（Go / Python / Shell）
└── 软技能（数据驱动 / 跨团队协作 / 成本意识）
```

---

## 第二章 K8s 与 GPU 调度（生产必知）

### 1 GPU Operator 部署架构

生产环境中，NVIDIA GPU Operator 是管理 GPU 驱动和运行时的标准方案。

**为什么需要 GPU Operator？** 手动在每个 GPU 节点上安装驱动、配置容器运行时、部署 Device Plugin、配置 MIG 是极为繁琐且容易出错的。GPU Operator 把这些组件全部容器化并自动化管理。

```
┌─────────────────────────────────────────────────┐
│              NVIDIA GPU Operator                 │
│              (统一管理所有 GPU 节点组件)           │
│                                                 │
│  ┌──────────────┐  ┌───────────────────────┐    │
│  │ Driver       │  │ Container Toolkit      │    │
│  │ (DaemonSet)  │  │ (DaemonSet)            │    │
│  │ 自动安装/更新  │  │ nvidia-container-runtime│  │
│  │ 驱动版本      │  │ / nvidia-docker2       │    │
│  │              │  │ 使容器能访问 GPU 驱动    │    │
│  └──────────────┘  └───────────────────────┘    │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ Device Plugin (DaemonSet)                │   │
│  │ 向 kubelet 注册 GPU 资源                   │   │
│  │ nvidia.com/gpu: 8                        │   │
│  │ 负责 GPU 分配 (Allocate) 和健康检查        │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ DCGM Exporter (DaemonSet)                │   │
│  │ 暴露 GPU 遥测指标给 Prometheus             │   │
│  │ 指标：温度、功耗、ECC、利用率、NVLink 等    │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ MIG Manager (可选 StatefulSet)            │   │
│  │ MIG 分区策略管理（切分/合并 GPU 实例）      │   │
│  │ 支持通过 CRD 声明 MIG 配置                │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**各组件详解**：

| 组件 | 运行方式 | 核心职责 | 故障影响 |
|------|----------|----------|----------|
| **Driver** | DaemonSet (privileged) | 编译并加载 NVIDIA 内核驱动到宿主机 | 驱动加载失败 → 该节点所有 GPU 不可用 |
| **Container Toolkit** | DaemonSet | 配置容器运行时（containerd/docker）使其识别 GPU | 配置失败 → Pod 无法创建 GPU 容器 |
| **Device Plugin** | DaemonSet | 向 kubelet 上报 GPU 资源量、处理 GPU 分配请求 | 不健康 → scheduler 看不到该节点的 GPU |
| **DCGM Exporter** | DaemonSet | 采集 GPU 指标，暴露 `/metrics` 端点 | 停止 → GPU 监控数据中断，告警失效 |
| **MIG Manager** | StatefulSet | 管理 MIG 分区策略和生命周期 | 停止 → MIG 配置无法变更（已配置的仍运行） |

```shell
# 安装 GPU Operator
$ helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
$ helm install gpu-operator nvidia/gpu-operator \
    --namespace gpu-operator \
    --create-namespace \
    --set driver.enabled=true \
    --set driver.version=550.54.15 \
    --set toolkit.enabled=true \
    --set mig.strategy=mixed \
    --set dcgmExporter.enabled=true
```

### 2 GPU Device Plugin 调度机制

```
Pod 请求 GPU 的完整链路：

Pod YAML (resources.limits.nvidia.com/gpu: 2)
  │
  ▼
kube-scheduler (Filter 阶段)
  │  → 调用 Device Plugin API: ListAndWatch()
  │  → 检查节点是否有 ≥2 张可用 GPU
  │
  ▼
kube-scheduler (Score 阶段，GPU 拓扑感知需要插件)
  │  → 优选 NVLink 互联的 GPU 对
  │  → 优选同一 NUMA Node 的 GPU
  │
  ▼
kubelet (节点上)
  │  → 调用 Device Plugin: Allocate(GPU-UUID-1, GPU-UUID-2)
  │  → Device Plugin 将 GPU 设备挂载到容器
  │    /dev/nvidia0, /dev/nvidia1
  │    NVIDIA_VISIBLE_DEVICES=GPU-xxxx,GPU-yyyy
  │
  ▼
nvidia-container-runtime
  │  → 注入 NVIDIA 驱动库到容器
  │  → 设置 CUDA 可见设备
```

### 3 生产常见问题：GPU 调度阻塞

**问题现象**：`kubectl describe pod` 显示 Warning `0/8 nodes are available: 8 Insufficient nvidia.com/gpu`

**排查流程**：

```shell
# 1. 查看节点 GPU 总量和已分配
$ kubectl describe node <node-name> | grep -A5 "nvidia.com/gpu"
Capacity:
  nvidia.com/gpu: 8
Allocatable:
  nvidia.com/gpu: 8
Allocated resources:
  nvidia.com/gpu: 8 (100%)  # 已全部分配

# 2. 查看哪些 Pod 占用了 GPU
$ kubectl get pods -A -o json | jq -r '
    .items[] | select(.spec.containers[].resources.limits["nvidia.com/gpu"] != null)
    | "\(.metadata.namespace)/\(.metadata.name) GPU:\(.spec.containers[].resources.limits["nvidia.com/gpu"]) Status:\(.status.phase)"
  '

# 3. 检查 Device Plugin 健康状态
$ kubectl get pod -n gpu-operator -l app=nvidia-device-plugin
$ kubectl logs -n gpu-operator <device-plugin-pod> --tail=20

# 4. 节点上验证 GPU 可用性
$ ssh <node> nvidia-smi
$ ssh <node> ls /dev/nvidia*
```

**根因分类**：

| 现象 | 根因 | 解决 |
|------|------|------|
| Device Plugin Pod CrashLoopBackOff | GPU 驱动版本不匹配 | 更新或降级驱动 |
| GPU 全部被分配但利用率低 | 任务碎片化 | 引入 Volcano 调度或 MIG |
| 部分 GPU 不可见 | PCIe 链路故障 | 硬件检查 / 更换 GPU |
| 新节点无法注册 GPU | Device Plugin 未就绪 | 检查 DaemonSet 调度到该节点 |

### 4 Volcano 批量调度器

大模型训练场景下，任务通常需要 Gang Scheduling（全有或全无）、队列管理、优先级抢占等能力，原生 Scheduler 无法满足。

```
Volcano 核心概念：

┌──────────────────────────────────────────┐
│  Queue (队列)                              │
│  ├── high-priority: weight=4, capacity=50%│
│  ├── normal: weight=2, capacity=30%       │
│  └── low-priority: weight=1, capacity=20% │
│                                           │
│  PodGroup (Pod 组)                         │
│  ├── minMember: 4  (最少 4 个才能运行)     │
│  ├── queue: high-priority                 │
│  └── priorityClassName: high              │
└──────────────────────────────────────────┘
```

```yaml
# Volcano Job 示例（PyTorch 分布式训练）
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: pytorch-training
spec:
  minAvailable: 4                # Gang Scheduling：4 个 Pod 必须同时调度
  schedulerName: volcano
  queue: high-priority
  priorityClassName: high
  policies:
    - event: PodEvicted
      action: RestartJob
  tasks:
    - replicas: 1
      name: master
      template:
        spec:
          containers:
            - name: pytorch
              image: pytorch/pytorch:2.0.1-cuda11.7-cudnn8-devel
              command: ["torchrun", "--nnodes=4", "--nproc_per_node=8", "train.py"]
              resources:
                limits:
                  nvidia.com/gpu: 8
    - replicas: 3
      name: worker
      template:
        spec:
          containers:
            - name: pytorch
              image: pytorch/pytorch:2.0.1-cuda11.7-cudnn8-devel
              resources:
                limits:
                  nvidia.com/gpu: 8
```

**生产常见问题**：

| 问题 | 原因 | 解决 |
|------|------|------|
| Job 一直 Pending | Gang Scheduling 不满足 minMember | 检查队列配额、资源碎片、节点污点 |
| 高优任务抢占后低优任务不恢复 | reclaim 策略未配置 | 配置 `reclaimable: true` |
| 队列饥饿 | 权重分配不均 | 调优 weight/guarantee/capability |
| Master Pod 启动慢 | 依赖 Worker 的 DNS 就绪 | 配置 `tasks[*].dependsOn` |

### 5 GPU 共享与 MIG

**为什么需要 GPU 共享？** 一张 H100 有 80GB 显存和 67 TFLOPS 的 FP32 算力，但很多推理任务只需要 10GB 显存和极低算力。如果每个小任务独占整张 GPU，利用率可能只有 15%。GPU 共享通过"切分"或"时分"让多个任务共享同一张 GPU。

```
GPU 共享方案对比：

┌──────────────┬──────────┬──────────┬──────────┬──────────────────────┐
│    方案       │ 隔离性   │ 显存隔离  │ 算力隔离  │ 适用场景              │
├──────────────┼──────────┼──────────┼──────────┼──────────────────────┤
│ Time-slicing │ 弱       │ ✗        │ ✗        │ 开发/测试/轻推理      │
│ MPS          │ 弱       │ ✗        │ 部分     │ 小模型推理            │
│ MIG (A100)   │ 强（硬件）│ ✓        │ ✓        │ 推理+小训练（7 分区）  │
│ MIG (H100)   │ 强（硬件）│ ✓        │ ✓        │ 推理+小训练（7 分区）  │
│ vGPU         │ 强       │ ✓        │ ✓        │ 虚拟化环境            │
└──────────────┴──────────┴──────────┴──────────┴──────────────────────┘
```

**MIG 详细工作原理**：

```
MIG (Multi-Instance GPU) 是把一张物理 GPU 在硬件层面切分成多个独立实例。

H100 MIG 分区能力：
┌─────────────────────────────────────────┐
│ 物理 H100 (80GB HBM, 132 SM)             │
├─────────────────────────────────────────┤
│ GI-0 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-1 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-2 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-3 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-4 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-5 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
│ GI-6 (1g.12gb, ~14 SM)    ≈ 1/7 张 GPU │
└─────────────────────────────────────────┘

每个 GI (GPU Instance) 有：
- 专属显存分区（硬件隔离，无法互相访问）
- 专属 SM 组（算力不互相干扰）
- 独立的内存带宽
- 独立的错误隔离（一个 GI 的 ECC 错误不影响其他 GI）

K8s 中通过 Device Plugin 暴露为：
- nvidia.com/mig-1g.12gb: 1   (请求 1 个 1g.12gb 的 MIG 实例)
- nvidia.com/mig-2g.24gb: 1   (请求 1 个 2g.24gb 的 MIG 实例)
```

**MIG vs Time-Slicing 选型决策树**：
```
需要 GPU 共享？
├── 需要严格隔离（不同用户/不同业务）？
│   └── YES → MIG（硬件隔离）
│       └── A100 → 最多 7 个分区
│       └── H100 → 最多 7 个分区
├── 需要灵活调整但可接受轻度干扰？
│   └── YES → Time-Slicing
│       └── 优点：不需重启，配置灵活
│       └── 缺点：显存不隔离，OOM 会互相影响
└── 需要动态切分 + 隔离？
    └── → vGPU（需要额外 license 费用）
```

**MIG 配置示例**：

```shell
# 查看 GPU MIG 能力
$ nvidia-smi mig -lgip
+----------------------------------------------------+
| GPU  0  Profile   1:  1g.20gb                      |
| GPU  0  Profile   2:  2g.40gb                      |
| GPU  0  Profile   3:  3g.80gb                      |  # A100-80GB
| GPU  0  Profile   4:  4g.80gb                      |
| GPU  0  Profile   5:  7g.80gb                      |
+----------------------------------------------------+

# H100 MIG 配置
$ nvidia-smi mig -cgi 9,9,9,9,9,9,9  # 创建 7 个 1g.12gb 实例
$ nvidia-smi mig -cci                 # 创建对应的 Compute Instance

# 对应 K8s 中请求 MIG 设备
# nvidia.com/mig-1g.12gb: 1
```

**生产常见 MIG 问题**：

```shell
# MIG 模式下 nvidia-smi 无输出
$ nvidia-smi mig -dci && nvidia-smi mig -dgi  # 先清理 MIG 配置
$ sudo reboot                                    # 重启使 MIG 模式变更生效

# MIG 实例被占用无法重新配置
$ kubectl cordon <node>                          # 隔离节点
$ kubectl drain <node> --ignore-daemonsets       # 驱逐 GPU Pod
$ nvidia-smi mig -dci && nvidia-smi mig -dgi     # 清理后重新配置

# MIG 模式切换需重启（A100 需要，H100 部分支持热切换）
# 确认 MIG 状态
$ nvidia-smi mig -i 0 --default_compute_instance
```

### 6 Kata Containers 与 GPU 场景

**Kata 原理**：

```
传统容器 (runc)               Kata 容器
┌──────────┐                 ┌──────────────────┐
│ Container │                 │    Container      │
│  + 应用    │                 │     + 应用         │
├──────────┤                 ├──────────────────┤
│ share     │                 │  Guest Kernel    │  ← 独立内核（安全隔离）
│ Host      │                 ├──────────────────┤
│ Kernel    │                 │  QEMU / Firecracker│ ← 轻量 VMM
└──────────┘                 ├──────────────────┤
                             │    Host Kernel    │
                             └──────────────────┘
```

**GPU 透传给 Kata**：

```yaml
# Kata + GPU 的 RuntimeClass
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-gpu
handler: kata
---
apiVersion: v1
kind: Pod
metadata:
  name: secure-inference
spec:
  runtimeClassName: kata-gpu
  containers:
    - name: vllm
      image: vllm/vllm-openai:latest
      resources:
        limits:
          nvidia.com/gpu: 1
```

**生产决策**：
- 推理多租户安全隔离 → 使用 Kata（启动时间可接受，安全收益大）
- 训练任务高性能 → 使用 runc（Kata 的 GPU 透传有性能损耗 2~5%）
- 不可信代码执行 → 必须 Kata

**常见坑**：

| 问题 | 原因 | 解决 |
|------|------|------|
| Kata 容器内 nvidia-smi 报错 | VFIO 绑定未就绪 | 确认 `/dev/vfio/` 路径和驱动 |
| 启动慢（>500ms） | VM 冷启动 | 使用 template 模式或 Firecracker |
| GPU 显存无法释放 | VM 进程未完全退出 | 强制 kill QEMU 进程 |
| 无法 GPU 热迁移 | VM 技术限制 | 计划性维护窗口处理 |

---

## 第三章 GPU 硬件与故障诊断

### 0 GPU 背景知识概览

> **为什么 ML SRE 必须懂 GPU 硬件？** 因为训练和推理的每一个异常最终都可能落在 GPU 硬件层面。软件栈（CUDA→PyTorch→训练脚本）的任何故障都能通过重试/恢复解决，但硬件故障（ECC 错误、NVLink 断链、GPU 掉卡）意味着必须下线节点甚至 RMA 显卡。区分"软件问题可快速恢复"和"硬件问题需隔离下线"是 ML SRE 的第一课。

```
GPU 软件栈层次（自下而上）：
┌─────────────────────────────────────┐
│  训练/推理框架 (PyTorch / vLLM)      │  ← 应用层，SRE 需理解但不需精通
├─────────────────────────────────────┤
│  CUDA Toolkit (cuBLAS / cuDNN)      │  ← 算子加速库
├─────────────────────────────────────┤
│  CUDA Runtime / Driver              │  ← 驱动层，Xid 错误在此捕获
├─────────────────────────────────────┤
│  GPU 硬件 (SM / HBM / NVLink / PCIe)│  ← 物理层，故障源头
└─────────────────────────────────────┘

SRE 视角：从下往上排查（硬件→驱动→框架），从上往下修复（框架→驱动→硬件）
```

**ECC 内存纠错详解**：
- GPU 的 HBM（高带宽显存）和 SRAM（寄存器/共享内存/L1/L2 缓存）都受 ECC 保护
- **可纠正错误 (CE, Correctable Error)**：单比特翻转，硬件自动修复，不影响计算。但如果**频繁出现**（如每天 > 10 次），说明存储单元正在劣化，需预警更换
- **不可纠正错误 (UE, Uncorrectable Error)**：双比特或多比特翻转，无法自动修复。此时 GPU 会触发 Xid 13 或 48，该 GPU 上的所有 CUDA 进程会失败，**必须立即下线 RMA**
- 生产建议：对 CE 设置趋势告警（每周递增 > 20%），对 UE 设置即时告警

**Xid 错误机制详解**：
- Xid 是 NVIDIA 驱动在检测到 GPU 异常时报告的错误码，记录在 `dmesg` 中：`NVRM: Xid (PCI:0000:18:00): 13, pid=12345, ...`
- 分类标准：
  - **应用层错误**：Xid 13/31/43/63/64 → 可能是 CUDA 代码 bug 或环境问题（温度/电源），有时无需下线
  - **硬件层错误**：Xid 45/48/74/79/95 → 几乎一定是硬件缺陷，需要隔离节点 + RMA
  - **信息类**：Xid 61/92/94 → 通常是临时状态，监控趋势即可
- 面试关键：能区分"看到哪个 Xid 就知道要立即下线节点"（45/48/74/79）vs "可以观察一阵"（31/63/64）

### 1 GPU 关键指标速查

```shell
# GPU 基本信息
$ nvidia-smi
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 550.54.15    Driver Version: 550.54.15    CUDA Version: 12.4     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA H100 80GB HBM3  On | 00000000:18:00.0 Off |                    0 |
| N/A   45C    P0    315W / 700W |   24576MiB / 81559MiB |     95%      Default |
+-------------------------------+----------------------+----------------------+

# 关键指标解读：
# Temp > 80°C  → 需检查散热/降频
# Pwr 接近 Cap  → GPU 满负载运行
# Volatile ECC > 0 → 有可纠正 ECC 错误（频繁出现需关注）
# GPU-Util 低但内存高 → 可能 IO 或通信瓶颈
# Perf 状态 P0(最高) ~ P8(最低待机)
```

### 2 GPU Xid Error 速查表

Xid Error 是 NVIDIA GPU 报错的核心机制。生产环境中能快速分类 Xid 是 ML SRE 的基本功。

| Xid | 级别 | 含义 | 处理方式 |
|-----|------|------|----------|
| **13** | 🔴 严重 | 显存 ECC 不可纠正错误 | 标记节点不可调度，RMA 显卡 |
| **31** | 🟡 中等 | 用户态驱动超时（CUDA Kernel Bug） | 检查应用代码，可能不需下线 |
| **43** | 🟡 中等 | GPU 陷入 Xid 43 状态 | 需 `nvidia-smi -r` 重置 GPU |
| **45** | 🔴 严重 | GPU 掉卡 / PCIe 链路故障 | 检查 PCIe 连接，可能硬件问题 |
| **48** | 🔴 严重 | 双比特 ECC 错误 | **立即下线节点**，RMA 显卡 |
| **61** | 🟢 信息 | GPU 内部微控制器异常 | 通常自动恢复，监控趋势 |
| **62** | 🟡 中等 | GPU 内存页面淘汰超时 | 可能需要 `nvidia-smi -r` |
| **63** | 🟡 中等 | GPU 温度保护降频 | 检查散热/风扇 |
| **64** | 🟡 中等 | GPU 电源保护降频 | 检查电源/PSU |
| **74** | 🔴 严重 | GPU 与 NVSwitch 通信失败 | 检查 NVSwitch 硬件 |
| **79** | 🔴 严重 | GPU 陷入安全模式 | **需断电重启物理机** |
| **92** | 🟡 中等 | PCIe 链路重训练 | 检查 PCIe 金手指/插槽 |
| **94** | 🟡 中等 | GPU 遇到不可恢复的 XID | 需 cold reset |
| **95** | 🔴 严重 | GPU 遇到致命的非硬件错误 | 需要 `nvidia-smi -r`，如无效则 RMA |

**Xid 检测脚本**：

```shell
#!/bin/bash
# 检测所有 GPU 节点的 Xid 错误
for node in $(kubectl get nodes -l nvidia.com/gpu.present=true -o name); do
    echo "=== Checking $node ==="
    kubectl debug node/${node#node/} -it --image=nvidia/cuda:12.4.0-base-ubuntu22.04 -- \
        bash -c "dmesg | grep -i 'NVRM: Xid'" 2>/dev/null
done
```

### 3 GPU 性能下降排查流程

```
现象：训练任务在某个节点上的吞吐量降低 30%

排查路径：

Step 1: GPU 硬件状态
$ nvidia-smi -q -d TEMPERATURE,POWER,CLOCK
→ 检查温度是否过高导致降频（Throttle Reason: Thermal）
→ 检查 Power Cap 是否被限制
→ 检查 SM/Memory Clock 是否低于标称值

Step 2: ECC 错误
$ nvidia-smi -q -d ECC
→ 检查 Volatile ECC Error Count
→ SRAM ECC > 0 或 DRAM ECC > 0 → 可能存在硬件隐患

Step 3: PCIe 链路
$ nvidia-smi -q -d PCIE
→ 检查 Link Gen 和 Width
→ H100 应为 Gen5 x16，如果是 Gen1 x1 则是链路降级

Step 4: NVLink
$ nvidia-smi nvlink -s
→ 检查 NVLink 是否全部 Active
→ 如果某个 NVLink 链路 Inactive → 影响多卡通信

Step 5: GPU 内存带宽
$ /usr/local/cuda/samples/1_Utilities/bandwidthTest/bandwidthTest
→ 与同型号正常 GPU 对比，偏差 > 20% → 硬件问题

Step 6: NCCL 通信性能
$ NCCL_DEBUG=INFO torchrun --nproc_per_node=8 nccl_test.py
→ 对比 busbw 是否达到标称值（H100 NVLink: 900 GB/s, InfiniBand: 400 GB/s）

Step 7: 应用层面
$ cat /proc/<pid>/status | grep -E "VmRSS|Threads"
→ 检查是否有内存泄漏、线程数异常
```

### 4 PCIe 拓扑与 NUMA 亲和性

```shell
# 查看 GPU 拓扑
$ nvidia-smi topo -m
        GPU0    GPU1    GPU2    GPU3    GPU4    GPU5    GPU6    GPU7    NIC0    NIC1    CPU Affinity
GPU0     X      NV18    NV18    NV18    NV18    NV18    NV18    NV18    PXB     PXB     0-31
GPU1    NV18     X      NV18    NV18    NV18    NV18    NV18    NV18    PXB     PXB     0-31
GPU2    NV18    NV18     X      NV18    NV18    NV18    NV18    NV18    PXB     PXB     0-31
GPU3    NV18    NV18    NV18     X      NV18    NV18    NV18    NV18    PXB     PXB     0-31
GPU4    NV18    NV18    NV18    NV18     X      NV18    NV18    NV18    PXB     PXB     32-63
GPU5    NV18    NV18    NV18    NV18    NV18     X      NV18    NV18    PXB     PXB     32-63
GPU6    NV18    NV18    NV18    NV18    NV18    NV18     X      NV18    PXB     PXB     32-63
GPU7    NV18    NV18    NV18    NV18    NV18    NV18    NV18     X      PXB     PXB     32-63
NIC0    PXB     PXB     PXB     PXB     PXB     PXB     PXB     PXB      X      PIX
NIC1    PXB     PXB     PXB     PXB     PXB     PXB     PXB     PXB     PIX      X

Legend:
  NV18 = NVLink 900 GB/s
  PXB  = PCIe 跨 CPU Socket（延迟高）
  PIX  = PCIe 同 CPU Socket（延迟中）
  SYS  = 跨 NUMA Node 通过 QPI/UPI（延迟最高）

# 最佳实践：
# GPU0~GPU3 绑定 NUMA 0 (CPU 0-31)
# GPU4~GPU7 绑定 NUMA 1 (CPU 32-63)
# NIC0、NIC1 各绑定一个 NUMA Node
```

**生产建议 — Pod 的 NUMA 拓扑约束**：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: training-pod
spec:
  containers:
    - name: trainer
      image: pytorch/pytorch:latest
      resources:
        limits:
          nvidia.com/gpu: 8
          cpu: 64
          memory: 512Gi
  # 通过 Topology Manager 保证 CPU/Memory/GPU 在同一 NUMA Node
  # 需要 kubelet 启用 TopologyManager policy: single-numa-node
```

---

## 第四章 分布式训练运维

### 0 为什么需要分布式训练

> 现代大模型的参数量远超单卡显存。例如 Llama-70B 在 BF16 精度下仅参数就需要 140GB，而 H100 单卡只有 80GB HBM。分布式训练通过"多卡协同"解决三个根本问题：**显存墙**（模型放不下）、**算力墙**（一轮训练太久）、**通信墙**（多卡通信效率决定扩展上限）。

### 1 分布式训练策略速览

| 策略 | 原理 | GPU 间通信 | 通信量 | 适用场景 |
|------|------|-----------|--------|----------|
| **DDP** (Data Parallel) | 每张 GPU 持有完整模型副本，数据切分 | AllReduce 梯度 | 正比于参数量 | 模型能放入单卡 |
| **FSDP** (ZeRO-3) | 模型参数/优化器状态分片到各 GPU | AllGather (前向)/ReduceScatter (反向) | 正比于参数量 | 模型 > 单卡显存 |
| **Tensor Parallel** | 层内张量切分到多 GPU | AllReduce 每层 | 正比于 hidden_size × batch | 单层 > 单卡显存 |
| **Pipeline Parallel** | 层间切分到多 GPU 流水线执行 | P2P Send/Recv | 正比于 micro_batch × hidden_size | 层数多、深度大 |
| **3D Parallel** | TP + PP + DP 组合 | 混合通信 | 三者叠加 | 超大模型（GPT-4 级别） |

**各策略深度解析**：

**DDP（数据并行）—— 最简单但最受限于显存**：
```
工作原理：
1. 每张 GPU 持有完整的模型副本（参数、梯度、优化器状态完全相同）
2. 每个 rank 读取不同的 mini-batch 数据进行前向/反向
3. 各 rank 通过 AllReduce 对梯度求平均
4. 用平均后的梯度在各 rank 本地更新参数（因初始参数相同，更新后仍保持同步）

优点：实现简单、通信只在反向传播结束后发生一次、PyTorch 原生支持
缺点：每张 GPU 需存储完整模型，无法训练超过单卡显存的模型

通信模式示意 (4 GPU)：
GPU0: grad0 ──┐
GPU1: grad1 ──┼── AllReduce ──→ avg_grad ──→ 各 GPU 独立 optimizer.step()
GPU2: grad2 ──┤
GPU3: grad3 ──┘
```

**FSDP（全分片数据并行）—— 用通信换显存**：
```
工作原理：
1. 模型参数被切分（shard）到所有 GPU，每张 GPU 只持有 1/N 的参数
2. 前向传播时：通过 AllGather 收集所需参数分片 → 计算 → 立即释放非本地分片
3. 反向传播时：再次 AllGather → 计算梯度 → ReduceScatter 将梯度归约到对应分片所在 GPU
4. 只有分片所在的 GPU 持有该部分参数的优化器状态

内存节省计算：
以 Llama-70B (BF16) 在 8 卡 H100 为例：
- 不分区：参数 140GB + 梯度 140GB + Adam 状态 560GB = 840GB/卡 → 远超 80GB
- FSDP 分区后：840GB / 8 = 105GB/卡 → 仍超 80GB，需配合 Gradient Checkpointing
- FSDP + GC 后：参数 17.5GB + 梯度 17.5GB + Adam 70GB + 激活值 ~20GB ≈ 125GB → 需进一步使用 CPU Offload

FSDP 通信量虽然等于 DDP（都传输一次完整参数/梯度），但分散到了前向和反向的每一步中，
这意味着通信与计算可以 Overlap（部分重叠），实际开销小于理论值。
```

**TP（张量并行）—— 层内切分，通信最密集**：
```
工作原理：
以 Transformer 的 Self-Attention 层为例（Q/K/V/O 四个矩阵）：
- 把 Q/K/V 的权重矩阵按列切分到 4 张 GPU（每张持有 1/4 的列）
- 前向：每张 GPU 分别计算各自的 Q/K/V/O 部分
- 每次做矩阵乘法后需要 AllReduce 来合并分片结果

通信特点：
- 通信发生在每层的前向和反向传播中（频率极高）
- 通信量取决于 hidden_size（如 8192）和 batch size
- 对 GPU 间带宽要求极高（需要 NVLink，不能跑在 PCIe 上）

使用场景：
- 单层权重大于单卡显存（如 GPT-3 的某些超大 FFN 层）
- 通常与 PP/DP 组合使用（3D Parallel），TP 只做 2-4 卡（NVLink 域内）
```

**PP（流水线并行）—— 层间切分，通信最少**：
```
工作原理：
把模型按层分成 N 个 Stage（如 Stage 0 = Layer 0-11, Stage 1 = Layer 12-23, ...）
每个 Stage 跑在不同的 GPU 上，数据以 micro-batch 为单位在 stage 间流水线传递

Bubble 问题（空闲气泡）：
时间 →
Stage0: [F0][F1][F2][F3][B3][B2][B1][B0]   F=Forward, B=Backward
Stage1:    [F0][F1][F2][F3][B3][B2][B1][B0]   空白部分 = Bubble（GPU 空闲）
Stage2:       [F0][F1][F2][F3][B3][B2][B1][B0]

Bubble 比例 ≈ (pipeline_stages - 1) / (pipeline_stages + micro_batches - 1)
减少 Bubble 的方法：增加 micro_batch 数量，或使用 1F1B 调度策略

使用场景：
- 模型层数很多且层间计算均匀（如 Llama-70B 的 80 层）
- 配合 DDP 使用：PP 解决单机显存问题，DDP 实现多机扩展
```

**3D Parallel 组合示例（Llama 70B 在 64 卡上训练）**：
```
TP=4, PP=4, DP=4  →  总共 4×4×4 = 64 张 GPU
- TP=4: 将每层切到 4 张 GPU 上（在同一 NVLink 域内）
- PP=4: 将 80 层分成 4 个 Stage，每个 Stage 20 层
- DP=4: 4 份数据副本，每份跑在 16 张 GPU（TP4×PP4）上

通信量分析：
- TP 通信：仅在 NVLink 域内（延迟极低，~1μs），每层都通信
- PP 通信：仅在相邻 Stage 间（P2P），通信量很小
- DP 通信：跨节点 AllReduce（走 InfiniBand），每 step 通信一次
```

### 2 NCCL 通信排障

NCCL 是 NVIDIA 的集合通信库，分布式训练的通信层。

**核心环境变量**：

```bash
# 调试与性能分析
NCCL_DEBUG=INFO           # 打印通信拓扑和带宽
NCCL_DEBUG_SUBSYS=ALL     # 打印所有子系统日志
NCCL_DEBUG_FILE=/tmp/nccl_%h_%p.log  # 输出到文件

# RDMA / InfiniBand
NCCL_IB_DISABLE=0          # 启用 InfiniBand
NCCL_IB_GID_INDEX=3        # RoCEv2 的 GID Index（关键！错误会导致通信失败）
NCCL_IB_HCA=mlx5_0,mlx5_1  # 指定使用的 HCA 设备
NCCL_IB_QPS_PER_CONNECTION=4  # 每个连接使用 4 个 QP（提升带宽）
NCCL_IB_TC=106             # RoCEv2 DSCP 优先级

# GPUDirect RDMA
NCCL_NET_GDR_LEVEL=5       # GPUDirect RDMA（GPU 显存直接 RDMA 到网卡）
                           # 0=禁用, 5=最高级别

# 网络接口
NCCL_SOCKET_IFNAME=eth0    # 指定 TCP 通信网卡（非 RDMA 场景）

# 超时与重试
NCCL_SOCKET_NTHREADS=4     # Socket 通信的线程数
NCCL_NSOCKS_PERTHREAD=4    # 每线程的 Socket 数
NCCL_TIMEOUT=1800           # 通信超时（秒）

# 拓扑检测
NCCL_TOPO_DUMP_FILE=/tmp/nccl_topo.xml  # 导出拓扑文件
```

**NCCL 常见故障排查**：

| 现象 | NCCL 日志关键词 | 根因 | 解决 |
|------|----------------|------|------|
| `ncclSystemError` | `NCCL WARN NET/IB` | InfiniBand 链路故障 | `ibstat` 检查链路状态 |
| `ncclInvalidUsage` | `no device found` | CUDA_VISIBLE_DEVICES 错误 | 检查环境变量 |
| 训练 Hang 住 | `NCCL INFO comm 0x...` 长时间无进展 | 某张卡通信超时 | 检查 `dmesg` Xid 错误 |
| 带宽远低于标称 | `busbw` < 预期 50% | GID_INDEX 错误或 PCIe 降级 | `ibv_devinfo -v` 检查 |
| `ncclRemoteError` | 跨节点通信失败 | 防火墙 / 路由 | `nccl-tests` 测不同节点对 |
| 启动后立即报错 | `NCCL WARN Duplicate` | 同一 GPU 被多个进程使用 | 检查进程隔离 |

**NCCL 性能测试**：

```shell
# nccl-tests 性能基准测试
$ git clone https://github.com/NVIDIA/nccl-tests.git
$ cd nccl-tests && make MPI=1 CUDA_HOME=/usr/local/cuda

# 单机 8 卡 AllReduce 测试
$ mpirun -np 8 -H localhost:8 \
    -x NCCL_DEBUG=INFO \
    ./build/all_reduce_perf -b 8 -e 2G -f 2 -g 1

# 多机 64 卡测试
$ mpirun -np 64 -H node1:8,node2:8,node3:8,node4:8,node5:8,node6:8,node7:8,node8:8 \
    -x NCCL_DEBUG=INFO \
    -x NCCL_IB_GID_INDEX=3 \
    -x NCCL_NET_GDR_LEVEL=5 \
    ./build/all_reduce_perf -b 8 -e 2G -f 2 -g 1

# 预期结果（H100 + NVLink + IB NDR400）：
# AllReduce busbw ~ 350-400 GB/s（单机 8 卡）
# AllReduce busbw ~ 300-380 GB/s（多机，取决于 IB 带宽）
```

### 3 训练任务 OOM 处理

OOM（Out of Memory）是训练任务最高频的故障，面试中几乎必问。ML SRE 需要能够区分三种 OOM 类型，并有针对性地解决。

**三种 OOM 类型对比**：

| OOM 类型 | 触发层 | 现象 | 排查方式 | 恢复难度 |
|----------|--------|------|----------|----------|
| **CUDA OOM** | CUDA Runtime | 训练代码报 `CUDA out of memory`，进程退出 | 检查 `torch.cuda.memory_summary()` | 低（调整 batch/显存策略） |
| **Pod OOM (Cgroup)** | Linux Cgroup | Pod 被 Evicted，`kubectl describe pod` 看到 OOMKilled | `kubectl describe pod`，`dmesg` | 中（需调整 memory request/limit） |
| **Node OOM** | Linux OOM Killer | 节点上所有 Pod 受影响，可能被随机 kill | `dmesg \| grep -i "out of memory"` | 高（可能影响多个任务） |

**CUDA OOM 详细排查方法论**：

```
第一步：确认是 CUDA OOM 而非其他 OOM
- 日志中出现：torch.cuda.OutOfMemoryError: CUDA out of memory
- 或：RuntimeError: CUDA out of memory. Tried to allocate XX GiB

第二步：查看当前显存使用分布
# 在容器内（训练进程仍在运行时）
$ python -c "import torch; print(torch.cuda.memory_summary())"

输出示例：
|===========================================================================|
|                  PyTorch CUDA memory summary, device ID 0                 |
|---------------------------------------------------------------------------|
|            CUDA OOMs: 0        |        cudaMalloc retries: 0             |
|===========================================================================|
|        Metric         | Cur Usage  | Peak Usage | Tot Alloc  | Tot Freed  |
|---------------------------------------------------------------------------|
| Allocated memory      |   75264 MB  |   80240 MB |  105120 MB |   29856 MB |
|       from large pool |   75008 MB  |   79984 MB |  104800 MB |   29792 MB |
|       from small pool |     256 MB  |     256 MB |     320 MB |      64 MB |
|---------------------------------------------------------------------------|
| Reserved memory       |   81920 MB  |   81920 MB |   81920 MB |       0 B  |
|       from large pool |   81536 MB  |   81536 MB |   81536 MB |       0 B  |
|       from small pool |     384 MB  |     384 MB |     384 MB |       0 B  |

解读：
- Allocated memory (75264 MB): 当前实际使用的显存（张量+模型+激活值）
- Reserved memory (81920 MB): PyTorch 缓存分配器持有的显存（包含空闲块）
- 如果 Reserved ≈ 总显存且还在 OOM → 确实显存不足
- 如果 Reserved << 总显存但 OOM → 可能有显存碎片问题

第三步：定位显存大户
from torch.profiler import profile, ProfilerActivity
with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
             profile_memory=True, record_shapes=True) as prof:
    loss = model(input_ids, labels=labels).loss
    loss.backward()
    optimizer.step()

print(prof.key_averages().table(sort_by="cuda_memory_usage", row_limit=10))
# 按 CUDA 显存使用排序，快速定位哪个操作分配了最多显存

第四步：按根因分类解决
┌──────────────────┬──────────────────────────────────────┐
│ 根因               │ 解决                                  │
├──────────────────┼──────────────────────────────────────┤
│ batch_size 太大    │ 减小 batch_size 或用梯度累积模拟大 batch│
│ seq_len 超出预期   │ 限制 max_seq_len 或截断长序列          │
│ 激活值过大         │ Gradient Checkpointing               │
│ 模型太大           │ FSDP/ZeRO-3 分片或 3D Parallel        │
│ 显存碎片           │ 设置 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True │
│ 内存泄漏           │ 检查是否有 tensor 未释放（如 list append 历史 loss）│
└──────────────────┴──────────────────────────────────────┘
```

**显存组成估算**（面试中经常需要快速估算）：

```
总显存 = 模型参数 + 梯度 + 优化器状态 + 激活值 + 临时缓冲区

示例（Llama-70B，BF16 训练）：
  模型参数:  70B × 2 bytes = 140 GB
  梯度:      70B × 2 bytes = 140 GB
  Adam 状态:  70B × (4+4) bytes = 560 GB  (momentum + variance, FP32)
  激活值:     取决于 batch_size 和 seq_len
  ─────────────────────────────────────
  合计（不含激活）: 840 GB
  使用 FSDP/ZeRO-3 分片 8 张 H100：840 / 8 = 105 GB/卡
  剩余用于激活值：80 - 105 ≈ 负数 → 需要 Gradient Checkpointing
```

**OOM 排查与优化**：

```python
# PyTorch 显存分析
import torch

# 1. 查看峰值显存
torch.cuda.max_memory_allocated() / 1024**3  # GB
torch.cuda.memory_summary()

# 2. 使用 PyTorch Profiler
from torch.profiler import profile, ProfilerActivity
with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
             profile_memory=True, record_shapes=True) as prof:
    output = model(input)
print(prof.key_averages().table(sort_by="cuda_memory_usage", row_limit=10))
```

**优化手段优先级**：

| 优先级 | 方法 | 显存节省 | 代价 |
|--------|------|---------|------|
| P0 | Gradient Checkpointing | ~50% 激活值 | 额外约 20% 计算 |
| P0 | BF16/FP16 混合精度 | ~50% 参数+激活 | 精度微小损失 |
| P1 | FSDP/ZeRO-3 | 参数分片 | 通信开销增加 |
| P1 | Flash Attention | ~50% 注意力激活值 | 需要适配 |
| P2 | 减小 batch_size | 线性减少 | 训练稳定性下降 |
| P2 | CPU Offloading | 极大 | 训练速度显著下降 |
| P3 | 增加 GPU 数量 | 线性 | 成本和通信开销 |

### 4 Checkpoint 管理

**生产常见 Checkpoint 问题**：

```shell
# 问题 1：Checkpoint 写入导致 IO 风暴
# → 使用异步 Checkpoint（PyTorch 2.0+ torch.save async）
# → 先写本地 NVMe 再异步上传对象存储

# 问题 2：分布式 Checkpoint 加载失败
# → 检查所有 rank 的 checkpoint shard 是否完整
# → 检查 world_size 是否与 checkpoint 一致

# 问题 3：Checkpoint 文件过大
# → 使用 FSDP SHARDED_STATE_DICT
# → 压缩后存储

# Checkpoint 存储架构建议：
# ┌──────────┐     ┌──────────┐     ┌──────────┐
# │  GPU Node │────▶│ NVMe SSD │────▶│ S3/COS   │
# │ (训练)    │     │ (快速写入)│     │ (持久存储)│
# └──────────┘     └──────────┘     └──────────┘
#   < 5s/checkpoint   < 30s/upload   长期保留
```

---

## 第五章 网络与存储

### 0 为什么网络是分布式训练的瓶颈

> 在千卡规模的训练中，GPU 约 50% 的时间在等待通信完成。如果网络带宽不达标或延迟过高，增加 GPU 数量反而会降低训练效率。

```
分布式训练中的通信开销分析：

训练一个 step 的总耗时 = 计算时间 + 通信时间

通信时间主要由 AllReduce 决定（梯度同步）：
AllReduce 耗时 ≈ (2 × (N-1) / N) × 数据量 / 带宽
其中 N = GPU 数量

例子（128 张 H100，AllReduce 70B 参数的 BF16 梯度）：
梯度数据量 = 70B × 2 bytes = 140 GB
理想情况下（Ring AllReduce，带宽 400 GB/s）：
通信时间 ≈ 2 × (128-1)/128 × 140GB / 400GB/s ≈ 0.69 秒

如果网络有故障导致带宽降为 40 GB/s：
通信时间 ≈ 6.9 秒（增加 10 倍），原本 1 秒的 step 变成 7.9 秒
GPU 利用率从 90% 降到 ~13%

这就是为什么 ML SRE 必须深入理解网络层的原因：
一次网络配置错误能让千卡集群变成废铁。
```

### 1 RDMA/RoCE 技术背景

**传统网络 I/O vs RDMA**：

```
传统 TCP/IP 数据传输路径（GPU → GPU 跨节点）：
数据在 GPU 显存 → CPU 内存 (PCIe copy) → 内核协议栈 (TCP/IP) → 网卡 → 网络
→ 网卡 → 内核协议栈 (TCP/IP) → CPU 内存 → GPU 显存 (PCIe copy)

问题：CPU 参与数据拷贝 + 内核态/用户态切换 + 协议栈开销
→ 延迟：50-100μs，带宽受限

RDMA 数据传输路径（GPU → GPU 跨节点）：
数据在 GPU 显存 → 网卡 (GPUDirect RDMA，直接 PCIe P2P) → 网络
→ 网卡 → GPU 显存 (GPUDirect RDMA)

优势：旁路 CPU、旁路内核、零拷贝
→ 延迟：1-3μs，带宽接近线速
```

**RDMA 两种实现对比**：

| 特性 | InfiniBand (IB) | RoCEv2 (RDMA over Ethernet) |
|------|-----------------|------------------------------|
| 物理层 | 专用 IB 线缆和交换机 | 标准以太网（需支持 DCB/PFC） |
| 网卡 | ConnectX HCA (Host Channel Adapter) | ConnectX 系列 NIC (支持 RoCE) |
| 延迟 | 1-2μs | 2-5μs |
| 带宽 | HDR 200Gb/s, NDR 400Gb/s | 25G/100G/200G/400G |
| 拥塞控制 | 基于 Credit（无损） | PFC + ECN/DCQCN |
| 管理复杂度 | 较低（封闭生态） | 较高（需配置 PFC/ECN/DCB） |
| 成本 | 高 | 中（复用以太网基础设施） |
| 主流场景 | 超大规模训练集群（千卡以上） | 中小规模训练 + 推理混合集群 |

**RoCEv2 的关键配置项**（面试高频）：

1. **PFC (Priority Flow Control)**：在以太网端口上按优先级做反压，保证 RoCE 流量不丢包。
   - 配置不当 → PFC 风暴（一个慢速设备拖垮整个网络）
   - 典型配置：对 RoCE 流量的优先级启用 PFC，TCP 流量不用
   
2. **ECN + DCQCN**：拥塞控制算法，防止 PFC 过度触发。
   - ECN 在交换机上标记拥塞的报文
   - DCQCN 在网卡侧根据 ECN 标记调整发送速率
   
3. **GID Index**：RoCEv2 使用 GID 来标识 RDMA 端点。
   - 错误配置 → NCCL 无法建立 RDMA 连接 → 回退 TCP → 带宽降 10-100 倍

### 2 RDMA / RoCE 网络排障

```shell
# InfiniBand 设备状态检查
$ ibstat
CA 'mlx5_0'
    CA type: MT4129
    Number of ports: 1
    Firmware version: 28.35.1012
    Port 1:
        State: Active
        Physical state: LinkUp
        Rate: 400                    # NDR 400Gb/s
        Base lid: 0

# RoCE 网卡状态
$ ibv_devinfo -v
hca_id: mlx5_0
    port: 1
        state: PORT_ACTIVE (4)
        max_mtu: 4096 (5)
        active_mtu: 4096 (5)         # MTU 4096 正常
        link_layer: Ethernet         # RoCE 走以太网

# RDMA 延迟测试
$ ib_send_bw -d mlx5_0 -i 1 -F --report_gbits
# 预期 H100 + NDR400: ~400 Gb/s

# GID 信息（RoCEv2 需要 GID Index）
$ ibv_devinfo -v | grep -A5 GID
# 找到 IPv4 RoCEv2 的 GID Index（通常为 3）
```

**RoCE 网络常见故障**：

| 现象 | 根因 | 排查命令 |
|------|------|----------|
| `ibstat` 显示 Link Down | 光模块/线缆故障 | `mlxlink -d <dev>` |
| MTU 不匹配 | 交换机端口配置错误 | `ibv_devinfo` 检查 active_mtu |
| PFC 丢帧 | ECN/PFC 配置问题 | `ethtool -S <dev> \| grep -i pfc` |
| GID 无 IPv4 条目 | RDMA CM 未配置 IPoIB | `ip addr show ib0` |
| 带宽不达预期 | 多 QP 未启用 / PCIe 降级 | `nvidia-smi topo -m` |

### 3 并行文件系统（Lustre/GPFS）

大模型训练数据集动辄 TB 级别，对存储吞吐有极高要求。

```
生产存储分级架构：

┌─────────────────────────────────────────────┐
│  热数据层                                     │
│  Lustre / GPFS  (多节点并行访问)               │
│  聚合带宽：100+ GB/s                          │
│  用途：训练数据集读取、Checkpoint 写入          │
├─────────────────────────────────────────────┤
│  温数据层                                     │
│  节点本地 NVMe RAID0 (数据集预处理 & 缓存)      │
│  单节点带宽：20+ GB/s                         │
│  用途：数据集预热、临时 Checkpoint              │
├─────────────────────────────────────────────┤
│  冷数据层                                     │
│  对象存储 (MinIO / COS / S3)                  │
│  用途：历史 Checkpoint、模型版本归档            │
└─────────────────────────────────────────────┘
```

**Lustre 常见问题**：

| 问题 | 现象 | 解决 |
|------|------|------|
| `lfs df -h` 显示 OST 满 | 写入报错 | 清理过期 Checkpoint，增加 OST |
| MDS 负载过高 | `ls` 命令卡顿 | 元数据分布在多 MDS 上 |
| Client 连接断开 | IO 任务 Hang | `lctl ping` 检测 + 恢复 client |
| 单 Client 带宽低 | 训练数据读取慢 | 增加 stripe_count |

```shell
# Lustre 生产常用命令
$ lfs df -h                           # 查看存储空间
$ lfs getstripe /mnt/lustre/dataset   # 查看文件条带化设置
$ lfs setstripe -c 8 /mnt/lustre/dataset  # 设置条带数
$ lctl get_param osc.*.stats          # 查看 IO 统计
$ lctl dl                             # 查看 Lustre 设备列表
```

---

## 第六章 可观测性与告警

### 1 GPU 监控指标（DCGM）

```promql
# ===== GPU 核心指标 =====

# GPU 利用率
DCGM_FI_DEV_GPU_UTIL{node="gpu-node-01"}

# 显存使用率
DCGM_FI_DEV_MEM_COPY_UTIL / 100
# 或
(DCGM_FI_DEV_FB_USED / DCGM_FI_DEV_FB_TOTAL) * 100

# GPU 温度（告警阈值 > 80°C）
DCGM_FI_DEV_GPU_TEMP > 80

# ECC 错误计数（告警阈值 > 0）
increase(DCGM_FI_DEV_ECC_CURRENT_COUNT[5m]) > 0

# NVLink 带宽利用率
DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL

# GPU 功耗
DCGM_FI_DEV_POWER_USAGE / DCGM_FI_DEV_POWER_MGMT_LIMIT * 100

# GPU 时钟频率（检测降频）
DCGM_FI_DEV_SM_CLOCK < 1500  # H100 标称 1980MHz

# GPU Xid 错误（关键告警）
DCGM_FI_DEV_XID_ERRORS
```

### 2 GPU 告警规则

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gpu-alerts
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: gpu-hardware
      rules:
        # GPU 温度过高
        - alert: GPUTemperatureHigh
          expr: DCGM_FI_DEV_GPU_TEMP > 85
          for: 5m
          labels:
            severity: warning
            component: gpu
          annotations:
            summary: "GPU 温度 > 85°C"
            description: "节点 {{ $labels.node }} GPU {{ $labels.gpu }} 温度 {{ $value }}°C"

        # GPU ECC 错误
        - alert: GPUECCError
          expr: increase(DCGM_FI_DEV_ECC_CURRENT_COUNT[5m]) > 0
          for: 1m
          labels:
            severity: critical
            component: gpu
          annotations:
            summary: "GPU ECC 错误"
            description: "节点 {{ $labels.node }} GPU {{ $labels.gpu }} 出现 ECC 错误，需检查"

        # GPU 掉卡
        - alert: GPUNotAvailable
          expr: DCGM_FI_DEV_GPU_UTIL < 0
          for: 2m
          labels:
            severity: critical
            component: gpu
          annotations:
            summary: "GPU 不可用"
            description: "节点 {{ $labels.node }} GPU {{ $labels.gpu }} 无响应"

        # GPU 降频
        - alert: GPUThrottling
          expr: DCGM_FI_DEV_SM_CLOCK < 1500 and DCGM_FI_DEV_GPU_UTIL > 80
          for: 10m
          labels:
            severity: warning
            component: gpu
          annotations:
            summary: "GPU 降频"
            description: "节点 {{ $labels.node }} GPU {{ $labels.gpu }} SM Clock {{ $value }}MHz（利用率 > 80%）"

        # 集群 GPU 整体利用率低
        - alert: GPUClusterLowUtilization
          expr: avg(DCGM_FI_DEV_GPU_UTIL) < 30
          for: 1h
          labels:
            severity: info
            component: resource
          annotations:
            summary: "集群 GPU 整体利用率 < 30%"
            description: "可能存在大量空闲 GPU"

    - name: training-monitoring
      rules:
        # 训练任务失败检测（需业务导出指标）
        - alert: TrainingJobFailed
          expr: increase(training_job_failed_total[5m]) > 0
          for: 1m
          labels:
            severity: critical
            component: training
          annotations:
            summary: "训练任务失败：{{ $labels.job_name }}"

        # NCCL 通信超时检测
        - alert: NCClTimeout
          expr: increase(nccl_timeout_total[5m]) > 0
          for: 1m
          labels:
            severity: critical
            component: network
          annotations:
            summary: "NCCL 通信超时"
```

### 3 训练任务指标导出

业务侧需要导出训练相关指标：

```python
# 在训练代码中导出 Prometheus 指标
from prometheus_client import Gauge, Counter, Histogram, start_http_server

# 训练 loss
training_loss = Gauge('training_loss_current', 'Current training loss')

# 训练吞吐
tokens_per_second = Gauge('training_tokens_per_second', 'Training throughput (tokens/s)')

# 梯度累积步数
gradient_accumulation_steps = Gauge('training_gradient_accumulation_steps', 'Current GA steps')

# Checkpoint 写入耗时
checkpoint_duration = Histogram('training_checkpoint_duration_seconds', 'Checkpoint save duration')

# NCCL 通信超时次数
nccl_timeout = Counter('nccl_timeout_total', 'NCCL timeout count')

# 启动 metrics server
start_http_server(9090)

# 训练循环中更新
while training:
    ...
    training_loss.set(loss.item())
    tokens_per_second.set(tok_per_sec)
```

---

## 第七章 资源管理与成本优化

### 1 GPU 资源利用率计算

```
关键指标：
┌─────────────────────────────────────┐
│ 分配率 = 已分配 GPU / 总 GPU × 100%  │
│ 利用率 = 实际使用 GPU 时间 / 总时间  │
│ 碎片率 = (分配率 - 利用率) / 分配率  │
│ 排队时间 = 任务提交 → 开始运行       │
│ 吞吐率 = 完成任务数 / 时间          │
└─────────────────────────────────────┘

理想状态：分配率 ≈ 利用率（碎片率 → 0）
现实状态：分配率 80% 但有 40% 利用率 → 50% 碎片率
```

### 2 成本模型

```
单次训练成本 = GPU数量 × 训练时长(h) × GPU单价(元/卡·时)
              + 存储费 + 带宽费 + 人力运维成本

GPU 单价(元/卡·时) = (采购价折摊 + 电费 + 机房租用) / 使用寿命(h)

示例（H100 按 3 年折摊）：
  采购价: 300,000 元 / 台
  3 年折摊每小时: 300,000 / (3×365×24) ≈ 11.4 元/h
  电费: 700W × 1元/kWh ≈ 0.7 元/h
  机房租用: 约 1 元/h
  ─────────────────────────────
  H100 单价: ~13 元/卡·时
  8 卡训练 30 天: 8 × 720h × 13 ≈ 74,880 元/任务
```

### 3 利用率优化策略

```
策略 1：MIG 碎片回收
  问题：8 个小任务各占 1 张 H100，7 张空闲时第 8 张被跑大任务占用
  方案：MIG 切成 7 个 1g.12gb + 1 个完整 GPU（留给大任务）
  效果：碎片率从 50% → 15%

策略 2：动态 GPU 共享（Time-slicing）
  问题：推理任务 GPU 利用率 < 20%，但仍独占 GPU
  方案：Time-slicing 配置 4 个副本共享 1 张 GPU
  效果：GPU 利用率 20% → 60%（但可能导致延迟抖动）

策略 3：优先级抢占
  问题：高优训练任务排队，低优任务占用资源
  方案：Volcano 优先级抢占，高优任务可驱逐低优任务
  关键：需要支持断点续训

策略 4：弹性训练
  问题：白天高峰排队，夜间资源闲置
  方案：使用 TorchElastic，支持动态增减 Worker
  效果：利用率曲线更平滑

策略 5：Spot Instance 模式
  问题：大量 GPU 闲置，但需要为峰值预留
  方案：推出 Spot GPU（低价可抢占），搭配 Checkpoint
  效果：利用率 +20%，成本 -30%
```

### 4 资源数据报表

```python
import pandas as pd
from prometheus_api_client import PrometheusConnect

prom = PrometheusConnect(url="http://prometheus:9090")

# GPU 利用率日报
query = 'avg by (node) (DCGM_FI_DEV_GPU_UTIL)'
result = prom.custom_query_range(
    query=query,
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z",
    step="5m"
)

# 按团队统计 GPU 使用量
query = '''
    sum by (team) (
        kube_pod_labels{label_team!=""}
        * on(pod, namespace) group_left(team)
        sum by (pod, namespace) (
            container_resource_limits{resource="nvidia_com_gpu"}
        )
    )
'''

# 成本归因
# 每个团队的 GPU 用量 × GPU 单价 = 团队 GPU 成本
```

---

## 第八章 推理服务部署

> JD 职责#1 明确要求"支持大模型的**部署**环节"，推理服务是 ML SRE 的半壁江山。
> 推理与训练的根本区别：训练追求**吞吐（samples/s）**，推理追求**延迟（TTFT/TPOT）+ 并发（QPS）**。推理服务的挑战在于 **KV Cache 显存管理**、**长尾延迟控制**、**突发流量应对**。

### 0 推理服务核心概念

**自回归生成（Autoregressive Generation）—— 为什么推理和训练如此不同**：
```
训练时：一次前向+反向传播处理整个序列（Teacher Forcing，已知答案）
推理时：逐 token 生成，每步都依赖之前的结果（无法并行）

Transformer 推理的两阶段：
┌─────────────────┐     ┌─────────────────────┐
│ Prefill 阶段     │     │ Decode 阶段          │
│ (处理 prompt)    │────▶│ (逐 token 生成)      │
│ 计算密集型        │     │ 显存带宽密集型         │
│ 一次处理所有输入   │     │ 每个 token 串行生成   │
│ 输出: KV Cache   │     │ 使用: KV Cache       │
└─────────────────┘     └─────────────────────┘

性能特点：
- Prefill 阶段：GPU 算力利用率高（矩阵乘密集），但耗时正比于 prompt 长度
- Decode 阶段：GPU 显存带宽瓶颈（不断读写 KV Cache），每步只做少量计算
- 瓶颈转移：> 10 个并发请求后，Decode 阶段从算力瓶颈变为显存带宽瓶颈
```

**KV Cache 机制详解**（理解这个是调试推理 OOM 的关键）：
```
Transformer 自注意力需要 Q、K、V 三个矩阵。
在自回归生成中，之前 token 的 K 和 V 可以复用：

Step 1 (token_0): 计算 Q_0·K_0^T, 需要 K_0, V_0 → 缓存 K_0, V_0
Step 2 (token_1): 计算 Q_1·[K_0,K_1]^T, 需要 K_0,K_1,V_0,V_1 → 缓存 K_1,V_1（复用 K_0,V_0）
Step 3 (token_2): 计算 Q_2·[K_0,K_1,K_2]^T, 复用 K_0,K_1,V_0,V_1 → 缓存 K_2,V_2
...

KV Cache 显存估算：
每个 token 的 KV Cache 大小 = 2 × num_layers × num_heads × head_dim × dtype_bytes
Llama-70B (8k 序列)：每个 token ≈ 2 × 80 × 64 × 128 × 2 bytes = 2.5 MB
8k 序列 × 256 并发请求 = 8k × 256 × 2.5 MB ≈ 5.1 TB → 远超单节点显存

这就是为什么推理服务的核心在 KV Cache 管理：
- vLLM 的 PagedAttention：像 OS 管理虚拟内存那样管理 KV Cache 分页
- Prefix Caching：共享前缀的请求复用同一份 KV Cache
- 量化 KV Cache：用 INT8 存储 KV Cache，节省一半显存
```

### 1 推理框架对比

| 框架 | 特点 | 适用场景 | 关键指标 |
|------|------|----------|----------|
| **vLLM** | PagedAttention、Continuous Batching、高吞吐 | 在线推理 API 服务 | Tokens/s、TTFT、TPOT |
| **TGI** (Text Generation Inference) | HuggingFace 官方、支持量化 | 与 HF 生态深度集成 | 同上 + 量化后精度 |
| **Triton Inference Server** | NVIDIA 官方、多框架、多模型 | 需要统一推理平台 | 延迟、吞吐、GPU 利用率 |
| **SGLang** | RadixAttention、结构化生成 | 需要前缀缓存/结构化输出 | Cache 命中率 |
| **llama.cpp** | CPU/GPU 混合推理、量化友好 | 资源受限 / 边缘推理 | Tokens/s、内存占用 |

### 2 vLLM 生产部署架构

```
┌──────────────────────────────────────────────────────────┐
│                    推理服务部署架构                          │
│                                                          │
│  Client (API Request)                                    │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐         │
│  │  Nginx /  │────▶│  vLLM    │────▶│  vLLM    │         │
│  │  Envoy    │     │  Pod-0   │     │  Pod-1   │         │
│  │ (LB + TLS)│     │ GPU-0    │     │ GPU-1    │         │
│  └──────────┘     └──────────┘     └──────────┘         │
│       │                  │                │              │
│       │          ┌───────┴────────┴───────┐             │
│       │          │    Prometheus Metrics  │             │
│       │          │  (queue_length,        │             │
│       │          │   ttft, tpot, kv_cache)│             │
│       │          └────────────────────────┘             │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │              HPA / KEDA (基于请求队列深度扩缩)      │   │
│  │  指标: vllm:num_requests_waiting > 5 → 扩容        │   │
│  │  缩容: 需 Graceful Shutdown (等待请求排空)          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 3 vLLM 关键参数与调优

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-llama3-70b
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.5.0
          args:
            - "--model"
            - "/models/Llama-3-70B-AWQ"
            - "--tensor-parallel-size"
            - "4"                           # TP=4，4 张 GPU 张量并行
            - "--max-model-len"
            - "8192"                         # 最大序列长度
            - "--max-num-seqs"
            - "256"                          # 最大并发序列数
            - "--gpu-memory-utilization"
            - "0.90"                         # GPU 显存使用率上限
            - "--enable-prefix-caching"      # 开启前缀缓存（KV Cache 复用）
            - "--enable-chunked-prefill"     # Chunked Prefill，减少首 token 延迟
            - "--max-num-batched-tokens"
            - "16384"                        # 每批次最大 token 数
            - "--dtype"
            - "auto"
          resources:
            limits:
              nvidia.com/gpu: 4
              memory: "256Gi"
          env:
            - name: VLLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: vllm-secrets
                  key: api-key
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 120
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 60
            periodSeconds: 5
```

### 4 推理服务扩缩容策略

```yaml
# KEDA ScaledObject - 基于 vLLM 队列深度自动扩缩
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-autoscaler
spec:
  scaleTargetRef:
    name: vllm-llama3-70b
  minReplicaCount: 1
  maxReplicaCount: 8
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring:9090
        metricName: vllm_num_requests_waiting
        query: |
          sum(vllm:num_requests_waiting{model_name="Llama-3-70B"})
        threshold: "5"                    # 等待请求 > 5 → 扩容
  advanced:
    horizontalPodAutoscalerConfig:
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 300  # 缩容冷静期 5min
          policies:
            - type: Pods
              value: 1
              periodSeconds: 120          # 每分钟最多缩 1 个
```

### 5 推理服务常见问题与调优

| 问题 | 现象 | 排查方向 | 解决 |
|------|------|----------|------|
| **TTFT 高**（首 token 延迟） | 用户等待时间长 | Prefill 阶段计算量大 | Chunked Prefill / 增加 TP |
| **TPOT 高**（每 token 延迟） | 生成速度慢 | Decode 阶段瓶颈 | 减少 max-num-seqs / 升配 GPU |
| **OOM 重启** | Pod 频繁重启 | KV Cache 膨胀 | 降低 max-model-len / 开启 Prefix Caching |
| **队列堆积** | 请求超时 | 流量突增 | 扩容 / 加请求队列上限 |
| **长尾延迟抖动** | P99 >> P50 | 长序列请求阻塞短请求 | P/D 分离部署 / 请求分队列 |
| **模型加载慢** | Pod 启动 5min+ | 模型文件大（70B ~140GB） | 使用 NVMe 本地缓存 / Lazy Load |

### 6 推理服务灰度发布

```
金丝雀发布策略（大模型推理）：

┌─────────────┐     ┌─────────────────────┐
│  Load        │     │  推理服务集群         │
│  Balancer    │────▶│                     │
│              │     │  vLLM v1 (90% 流量)  │  ← 稳定版本
│              │     │  vLLM v2 (10% 流量)  │  ← 金丝雀
│              │     └─────────────────────┘
└─────────────┘

验证指标：
  - P50/P99 TTFT 不劣于 v1
  - 吞吐量（tokens/s）不劣于 v1
  - 错误率 < v1 的 1.2 倍
  - GPU 显存使用率正常范围内
  - 对比 30min 后决策：全量发布 / 回滚
```

### 7 模型量化方案

```
量化 vs 精度 trade-off：

┌──────────────┬──────────┬───────────┬──────────┬──────────┐
│ 量化方法       │ 精度位数  │ 模型大小  │ 推理速度  │ 精度损失  │
├──────────────┼──────────┼───────────┼──────────┼──────────┤
│ FP16/BF16    │ 16-bit   │ 1.00x     │ 1.00x    │ 基准      │
│ INT8 (动态)   │ 8-bit    │ 0.50x     │ 1.5-2x   │ < 0.5%    │
│ GPTQ 4-bit   │ 4-bit    │ 0.25x     │ 2-3x     │ 1-3%      │
│ AWQ 4-bit    │ 4-bit    │ 0.25x     │ 2-3x     │ 1-2%      │
│ FP8 (H100)   │ 8-bit    │ 0.50x     │ 2x       │ < 0.1%    │
└──────────────┴──────────┴───────────┴──────────┴──────────┘

生产建议：
  - H100 优先用 FP8（硬件原生支持，精度损失最小）
  - 在线推理用 AWQ 4-bit（速度 + 精度平衡好）
  - 离线批量推理用 GPTQ（节省显存）
```

---

## 第九章 多地域容灾与部署

> JD 职责#4 专门提到"多地域、多机房的系统容灾、服务部署管理和集群机器治理"，这是系统设计题的必考方向。

### 1 多地域架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      多地域 ML 训练平台                           │
│                                                                 │
│  ┌─────────────────────┐          ┌─────────────────────┐       │
│  │    Region A (华北)   │          │    Region B (华南)   │       │
│  │   主训练集群          │          │   灾备集群            │       │
│  │                     │          │                     │       │
│  │  K8s Cluster        │  ◀─ 同步 ─▶  K8s Cluster       │       │
│  │  500 Nodes × 8 H100 │  Checkpoint │  200 Nodes × 8 H100 │       │
│  │  Lustre (主存储)     │   模型权重  │  Lustre (只读副本)   │       │
│  │  对象存储 (主)        │  ◀─ 双写 ─▶  对象存储 (副本)     │       │
│  └─────────┬───────────┘          └─────────────────────┘       │
│            │                                                      │
│            │    ┌─────────────────────────────┐                  │
│            └───▶│   全局调度层                   │                  │
│                 │   跨 Region 任务分发           │                  │
│                 │   故障检测 + 自动切换           │                  │
│                 │   DNS / GSLB 流量调度          │                  │
│                 └─────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2 多地域关键挑战与解决方案

| 挑战 | 问题描述 | 解决方案 |
|------|----------|----------|
| **跨地域通信延迟** | AllReduce 在跨地域 30ms+ 延迟下无法工作 | 训练任务**必须在同一 Region 内**完成；跨地域只做 Checkpoint 同步和灾备 |
| **Checkpoint 同步** | 训练中 Checkpoint 多 GB 级，跨地域传输慢 | 异步增量同步 + 压缩传输；本地 NVMe 写完后异步上传 COS；跨地域 COS 桶复制 |
| **模型权重分发** | 新模型版本需同步到所有 Region | 对象存储多地域复制（COS 跨地域复制 / S3 Cross-Region Replication） |
| **数据集一致性** | 不同 Region 的训练数据可能不一致 | 数据集在对象存储集中管理，训练前预热到本地 Lustre；禁止直接修改 Region 本地数据集 |
| **故障切换** | 主集群不可用时，如何切换到灾备集群 | 训练任务需支持断点续训；切换后从最新 Checkpoint 恢复；切换时间 < 30min |
| **成本控制** | 灾备集群 GPU 闲置率高 | 灾备集群跑低优先级任务（离线评估、数据预处理）；主集群故障时抢占 |

### 3 跨地域 Checkpoint 同步方案

```
方案对比：

┌──────────────────┬──────────────┬──────────────┬──────────────┐
│ 方案               │ RPO (数据丢失)│ RTO (恢复时间) │ 成本          │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 对象存储跨地域复制  │ 分钟级        │ < 30min      │ 中等（带宽费） │
│ Lustre 同步 (Robinhood)│ 小时级    │ < 1h         │ 低            │
│ 专用线路 + rsync   │ 实时          │ < 15min      │ 高（专线费）   │
│ 人工介入             │ 天级          │ 数小时        │ 最低          │
└──────────────────┴──────────────┴──────────────┴──────────────┘

推荐方案：
训练节点 → NVMe (秒级) → COS 本Region (分钟级) → COS 跨地域复制 (分钟级)
RPO: 5~15min  |  RTO: 20~30min
```

### 4 容灾演练与混沌工程

```yaml
# Chaos Mesh: 模拟 GPU 节点大规模故障
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: gpu-node-failure-drill
spec:
  action: pod-kill
  mode: fixed-percent
  value: "20"                           # 随机 kill 20% 的 GPU Pod
  selector:
    namespaces:
      - training
    labelSelectors:
      app: pytorch-training
  duration: "5m"
  scheduler:
    cron: "0 10 * * 0"                 # 每周日 10:00 自动演练
```

**容灾演练 SOP**：

```
1. 演练前（T-30min）
   - 确认灾备集群可用资源足够
   - 确认最新 Checkpoint 已同步到灾备 Region
   - 通知相关团队

2. 演练中
   - 模拟主集群 Region A 不可用
   - 切换 DNS / GSLB 到 Region B
   - 灾备集群加载最新 Checkpoint
   - 重启训练任务

3. 演练后
   - 记录 RTO（实际恢复时间）
   - 记录数据丢失量（RPO 偏差）
   - 输出改进项（哪些步骤慢了、哪些依赖遗漏了）
   - 回切到主集群
```

### 5 多集群管理（KubeFed / Clusternet）

```
多集群方案选型：

┌──────────────┬──────────┬──────────┬──────────┐
│ 方案           │ 复杂度   │ 适用规模  │ GPU 支持  │
├──────────────┼──────────┼──────────┼──────────┤
│ KubeFed v2   │ 高       │ 大       │ 一般      │
│ Clusternet   │ 中       │ 中       │ 良好      │
│ Karmada      │ 中       │ 大       │ 良好      │
│ 自研 + ArgoCD │ 低       │ 任意     │ 任意      │
└──────────────┴──────────┴──────────┴──────────┘

推荐 Pattern: ArgoCD App of Apps + 自定义 Scheduler
  - ArgoCD 管理所有集群的应用部署
  - 自定义 Scheduler 负责跨 Region 任务分发
  - GPU Operator 在各集群独立安装和管理
```

---

## 第十章 SRE 最佳实践

> JD 职责#3 要求"运维人效提升"和"平台化系统化的手段"，SRE 方法论是回答这类问题的理论框架。

### 1 SLO / SLI / Error Budget

```
SRE 核心三角：

┌──────────────┐
│    SLI       │  服务水平指标（Service Level Indicator）
│  测量的是什么  │  示例：训练任务成功率 = 成功完成 / 总提交数
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    SLO       │  服务水平目标（Service Level Objective）
│  目标是多少    │  示例：训练任务成功率 >= 99.5%（月度）
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Error Budget │  错误预算（允许的不可用时间）
│  能失败多少次  │  示例：一个月 1000 任务，允许失败 5 次
│              │  Error Budget 耗尽 → 冻结发布
└──────────────┘
```

**训练平台的 SLO 示例**：

| SLI | SLO 目标 |测量方式 |
|-----|----------|--------|
| 训练任务提交成功率 | >= 99.5% | success / total |
| GPU 节点可用性 | >= 99.9% | up{job="gpu-node"} |
| GPU 调度延迟 P99 | < 5 min | 提交到 Running 的时间 |
| Checkpoint 保存成功率 | >= 99.9% | 成功保存次数 |
| 推理服务可用性 | >= 99.95% | HTTP 200 / total |
| 推理服务 TTFT P99 | < 500ms (短期), < 2s (长序列) | vLLM metrics |

### 2 运维人效提升 — 平台化思路

```
人效提升的三个阶段：

Phase 1: 脚本化（人肉运维）
  → "我 SSH 上去重启一下服务"
  → 问题：不可复制、易出错、无记录

Phase 2: 自动化（CI/CD + IaC）
  → "Jenkins pipeline 自动部署"
  → "Terraform + Ansible 管理基础设施"
  → 问题：自动化 ≠ 平台化，门槛仍然高

Phase 3: 平台化（Self-Service）
  → "算法工程师在 Web UI 上提交训练任务，平台自动分配资源"
  → 运维变成平台开发者，用户自助完成操作
  → 关键：声明式 API + 审批流 + 审计日志

衡量人效的关键指标：
  - 任务从提交到开始运行的平均等待时间
  - 常见运维操作的一次成功率（如 GPU 节点上下线）
  - 无需运维介入的故障自愈比例
  - Oncall 告警数量趋势（目标是持续下降）
```

### 3 Oncall 与故障管理

```
故障管理流程：

告警触发 → 值班响应 → 初步定级 → 紧急修复 → 根因分析 → 改进项跟踪

定级标准：
  P0: 训练平台不可用 / 推理服务全挂 / GPU 集群大规模故障 → 15min 响应
  P1: 部分节点/任务异常，影响 < 50% 用户 → 30min 响应
  P2: 个别任务失败，用户可自行重试 → 2h 响应
  P3: 功能异常但不影响任务 → 下一个工作日

故障复盘（Postmortem）模板：
  1. 时间线（精确到分钟）
  2. 根因分析（5 Whys）
  3. 影响范围（用户数、损失 GPU 时、数据损失）
  4. 检测延迟（从故障发生→告警触发用了多久）
  5. 恢复时间（RTO）
  6. Action Items（负责人 + 截止日期）
```

### 4 容量规划方法论

```python
# GPU 容量预测模型
from sklearn.linear_model import LinearRegression
import numpy as np

# 历史数据：每周 GPU 使用量
weeks = np.array(range(1, 13)).reshape(-1, 1)  # 过去 12 周
gpu_usage = np.array([120, 135, 148, 155, 170,
                       180, 195, 210, 230, 245, 260, 280])

model = LinearRegression().fit(weeks, gpu_usage)
week_16_prediction = model.predict([[16]])[0]  # 预测第 16 周

print(f"第 16 周 GPU 需求预测: {week_16_prediction:.0f} 张")

# 采购建议
current_gpu = 350  # 当前 GPU 数量
lead_time = 8      # 采购到货周期（周）
target_week = 16 + lead_time
target_demand = model.predict([[target_week]])[0]
safety_margin = 1.2  # 20% 安全余量

recommended = max(0, target_demand * safety_margin - current_gpu)
print(f"建议采购: {recommended:.0f} 张 GPU（到货周期 {lead_time} 周）")
```

**容量规划汇报要点（面试高频）**：

```
向管理层汇报 GPU 资源规划时，需要展示：

1. 现状：
   - 当前 GPU 总量 / 分配率 / 利用率
   - 各业务线 GPU 用量占比

2. 趋势：
   - 过去 6 个月的 GPU 使用趋势（环比/同比）
   - 业务增长预估（新模型、新业务）

3. 缺口分析：
   - 按当前趋势，6 个月后缺口 = XX 张
   - 采购周期 8~12 周 → 需提前启动

4. 优化空间：
   - 利用率可从 45% 提升到 65%，等价释放 XX 张 GPU
   - 混合卡策略（云上弹性 + 自有机器）节省 XX 成本

5. 建议：
   - 短期：优化利用率释放资源
   - 中期：采购 XX 张 H100/H200
   - 长期：建立弹性 GPU 池（云上 Spot + 自有）
```

---

## 第十一章 Go 语言 SRE 开发

> JD 要求#2 明确要求 Go 语言。ML SRE 的 Go 开发主要围绕 K8s Operator/Controller 和 GPU 管理工具。
> 
> **面试中的 Go 考察重点**：不同于后端岗位的"微服务 + 数据库"，ML SRE 的 Go 侧重**K8s 生态开发**。核心能力是理解 Controller 模式、熟练使用 client-go，以及能写出生产级别的并发安全代码。

### 0 Go 在 ML SRE 中的典型应用场景

```
ML SRE 使用 Go 开发的主要场景：
├── K8s Controller/Operator（最常见）
│   ├── GPU 故障检测与自动标记
│   ├── 训练任务生命周期管理
│   ├── GPU 节点的 Taint/Drain 自动化
│   └── 自定义调度逻辑（Scheduler Extender）
├── 监控数据聚合与报表
│   ├── 并发查询多集群 Prometheus
│   ├── GPU 利用率日报/周报生成
│   └── 成本归因计算
├── CLI 工具与自动化脚本
│   ├── 批量 GPU 节点操作工具
│   ├── Checkpoint 管理工具
│   └── 训练任务提交 CLI
└── API / Web 服务
    ├── GPU 资源查询 API
    └── 训练平台后端服务
```

**面试重点**：面试官通常不会让你写一个完整的 Operator（代码量太大），但会考察你对以下概念的理解：
1. Controller 模式的核心思想（声明式 + Reconcile Loop）
2. Informer 机制（ListWatch + Indexer + WorkQueue）
3. 并发安全（goroutine + channel + sync）
4. K8s client-go 的常用 API

### 1 GPU Node Controller（Go + client-go）

面试可能要求手写或描述一个简单的 Controller 逻辑。

```go
package main

import (
    "context"
    "fmt"
    "time"

    corev1 "k8s.io/api/core/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/client-go/kubernetes"
    "k8s.io/client-go/tools/cache"
    "k8s.io/client-go/util/workqueue"
    "k8s.io/klog/v2"
)

// GPUNodeController 监控 GPU 节点健康状态
type GPUNodeController struct {
    clientset kubernetes.Interface
    queue     workqueue.RateLimitingInterface
    informer  cache.SharedIndexInformer
}

// 核心 Reconcile 循环
func (c *GPUNodeController) Run(ctx context.Context) {
    defer c.queue.ShutDown()

    // 注册事件处理器
    c.informer.AddEventHandler(cache.ResourceEventHandlerFuncs{
        AddFunc: func(obj interface{}) {
            c.enqueue(obj)
        },
        UpdateFunc: func(old, new interface{}) {
            // 只在 GPU 相关 label 变化时处理
            c.enqueue(new)
        },
    })

    // 启动 workers
    for i := 0; i < 4; i++ {
        go c.worker(ctx)
    }

    <-ctx.Done()
}

func (c *GPUNodeController) worker(ctx context.Context) {
    for c.processNextItem() {
    }
}

func (c *GPUNodeController) processNextItem() bool {
    item, quit := c.queue.Get()
    if quit {
        return false
    }
    defer c.queue.Done(item)

    key := item.(string)
    err := c.reconcile(key)
    if err != nil {
        klog.Errorf("reconcile failed for %s: %v", key, err)
        c.queue.AddRateLimited(item)
        return true
    }
    c.queue.Forget(item)
    return true
}

// Reconcile: 核心逻辑 — 检查 GPU 节点健康并标记
func (c *GPUNodeController) reconcile(nodeName string) error {
    ctx := context.Background()
    node, err := c.clientset.CoreV1().Nodes().Get(ctx, nodeName, metav1.GetOptions{})
    if err != nil {
        return fmt.Errorf("get node: %w", err)
    }

    // 检查节点是否有 GPU
    gpuCount, hasGPU := node.Status.Capacity["nvidia.com/gpu"]
    if !hasGPU || gpuCount.Value() == 0 {
        return nil // 非 GPU 节点，跳过
    }

    // 检查 GPU 健康条件（需自定义 condition 或外部检测）
    gpuHealthy := c.checkGPUHealth(nodeName)

    if !gpuHealthy {
        // Taint 节点
        taint := corev1.Taint{
            Key:    "gpu.health/fault",
            Value:  "true",
            Effect: corev1.TaintEffectNoSchedule,
        }
        // 添加 taint（实际需要 merge 已有 taints）
        klog.Warningf("GPU node %s unhealthy, marking as fault", nodeName)
        _ = taint // 实际生产中调用 update node with taint

        // 驱逐 GPU Pod
        pods, _ := c.clientset.CoreV1().Pods("").List(ctx, metav1.ListOptions{
            FieldSelector: fmt.Sprintf("spec.nodeName=%s", nodeName),
        })
        for _, pod := range pods.Items {
            // 只驱逐使用 GPU 的 Pod
            for _, container := range pod.Spec.Containers {
                if _, hasGPU := container.Resources.Limits["nvidia.com/gpu"]; hasGPU {
                    klog.Infof("Evicting GPU pod %s/%s", pod.Namespace, pod.Name)
                    c.clientset.CoreV1().Pods(pod.Namespace).Delete(ctx, pod.Name, metav1.DeleteOptions{})
                    break
                }
            }
        }

        // 发送告警通知
        c.notifyOps(fmt.Sprintf("GPU node %s health check failed", nodeName))
    }

    return nil
}

func (c *GPUNodeController) checkGPUHealth(nodeName string) bool {
    // 生产实现：
    // 1. 通过 Prometheus API 查询 ECC Error / Xid Error / Temperature
    // 2. 或通过 SSH/NPD 执行 nvidia-smi 健康检查
    // 3. 或检查节点上的 DCGM 指标
    return true
}

func (c *GPUNodeController) notifyOps(msg string) {
    // 发送企业微信 / 钉钉 / PagerDuty
    klog.Infof("NOTIFICATION: %s", msg)
}

func (c *GPUNodeController) enqueue(obj interface{}) {
    key, _ := cache.MetaNamespaceKeyFunc(obj)
    c.queue.Add(key)
}
```

### 2 其他常见 Go 开发场景

```go
// 场景 1：GPU 资源报表聚合（并发查询多个集群的 GPU 利用率）
func AggregateGPUUtilization(clusters []string) map[string]float64 {
    result := make(map[string]float64)
    var mu sync.Mutex
    var wg sync.WaitGroup

    for _, cluster := range clusters {
        wg.Add(1)
        go func(c string) {
            defer wg.Done()
            util := queryGPUUtilization(c)
            mu.Lock()
            result[c] = util
            mu.Unlock()
        }(cluster)
    }
    wg.Wait()
    return result
}

// 场景 2：批量节点操作（cordon/drain GPU 节点分组执行）
func BatchDrainNodes(nodeList []string, maxConcurrent int) error {
    sem := make(chan struct{}, maxConcurrent) // 并发控制
    errCh := make(chan error, len(nodeList))

    for _, node := range nodeList {
        sem <- struct{}{}
        go func(n string) {
            defer func() { <-sem }()
            if err := drainNode(n); err != nil {
                errCh <- err
            }
        }(node)
    }
    // ...
    return nil
}

// 场景 3：Prometheus 指标客户端（Go 原生查询）
import "github.com/prometheus/client_golang/api"
import v1 "github.com/prometheus/client_golang/api/prometheus/v1"

func QueryGPUMetrics(promURL string) (v1.Warnings, error) {
    client, _ := api.NewClient(api.Config{Address: promURL})
    api := v1.NewAPI(client)

    result, warnings, err := api.Query(context.Background(),
        `avg(DCGM_FI_DEV_GPU_UTIL) by (node)`,
        time.Now(),
    )
    // 处理 vector result...
    return warnings, err
}
```

### 3 K8s Informer 机制（面试高频）

```
Informer 是 client-go 的核心机制，面试中理解它体现对 K8s 的深度掌握：

┌──────────┐     ┌──────────┐     ┌──────────┐
│ API      │────▶│ Reflector│────▶│  Delta   │
│ Server   │List │ (List &  │Watch │  FIFO    │
│          │Watch│  Watch)  │     │  Queue   │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
                                       ▼
                               ┌──────────────┐
                               │   Indexer    │ ← 本地缓存（内存）
                               │ (ThreadSafe) │   Get/List 无网络开销
                               └──────┬───────┘
                                      │
                                      ▼
                               ┌──────────────┐
                               │  EventHandler│ ← Add/Update/Delete 回调
                               └──────┬───────┘
                                      │
                                      ▼
                               ┌──────────────┐
                               │  WorkQueue   │ ← 异步处理
                               └──────────────┘

关键面试点：
  - Reflector 做 List + Watch，保证不丢事件（ResourceVersion 兜底）
  - Indexer 是本线程安全的缓存，按 key 索引存储
  - WorkQueue 解耦生产（EventHandler）和消费（Worker）
  - 为什么用 WorkQueue 而不是直接在 EventHandler 处理？
    → 避免阻塞 Reflector，保证事件不丢失
    → 支持重试（RateLimiting Queue）
    → 天然支持并行（多个 Worker goroutine）
```

---

## 第十二章 高频面试场景题

### 场景 1：训练任务 Hang 住排查

**问题**：一个 64 卡分布式训练任务运行到 step 500 时卡住，所有 GPU 利用率降为 0%，如何排查？

**标准回答框架**：

```
Step 1: 快速定位（1 分钟）
  - kubectl describe pod → 有无 OOMKilled / Evicted
  - dmesg | grep -i "NVRM: Xid" → 有无 GPU 硬件错误
  - nvidia-smi → GPU 状态、温度、功耗是否正常

Step 2: 通信层排查（3 分钟）
  - 检查 NCCL_DEBUG=INFO 日志 → 卡在哪个通信原语
  - 检查 InfiniBand/RoCE 链路 → ibstat 确认状态
  - 检查是否有 link flap → dmesg | grep -i "link down"

Step 3: 应用层排查（5 分钟）
  - py-spy dump 训练进程 → 卡在哪个 Python 调用栈
  - strace -p <pid> → 系统调用层面
  - 检查是否有 CUDA 错误 → nvidia-smi pmon -c 1

Step 4: 根因定位
  常见：
  - Rank 0 等待其他 Rank 的 barrier（某 Rank 慢或挂死）
  - NCCL Ring 通信中某个节点网络中断
  - GPU 显存耗尽但未 OOM（CUDA 分配器死锁）
  - IO 阻塞（Checkpoint 写入或数据加载 Hang）

Step 5: 恢复
  - 短期：kill 任务 → 从最后一个 Checkpoint 恢复
  - 中期：隔离问题节点（cordon + drain）→ 加入新节点
  - 长期：增加 NCCL_TIMEOUT + 心跳检测 → 自动重试
```

### 场景 2：GPU 集群利用率低但排队严重

**问题**：集群 GPU 利用率只有 40%，但大量训练任务在排队，等待时间超过 2 小时，如何分析并解决？

**回答框架**：

```
问题本质：资源碎片化

Step 1: 数据收集
  - GPU 分配率 vs 利用率 → 40% 利用率说明大量"已分配但未使用"
  - 任务大小分布 → 如果大量 1-2 卡任务 + 少量 8 卡任务
  - 队列等待时间 → 确认是碎片问题还是容量问题

Step 2: 根因分析
  场景 A：大任务饥饿
    8 卡任务需要等 8 个连续空闲 GPU，但被小任务碎片化
    → 引入 Gang Scheduling（Volcano）+ 资源预留

  场景 B：GPU 已被分配但任务空闲
    kubectl top pod → GPU 利用率 < 5% → 开发环境未用 GPU
    → 设置 GPU 空闲超时回收机制

  场景 C：任务分布不均
    部分节点满、部分空 → 调度策略问题
    → 使用 Bin Packing 或 Spreading 策略（Volcano taskTopology）

Step 3: 解决方案
  短期：
    - MIG 切割：H100 切 7 份跑推理/小任务，减少碎片
    - 清理僵尸 Pod（GPU 占用但无实际负载）
  中期：
    - 引入 Volcano 调度器：Gang Scheduling + 队列优先级
    - GPU Time-slicing：小任务共享 GPU
  长期：
    - Spot GPU 模式：提升整体利用率
    - 弹性训练：TorchElastic 动态扩缩
```

### 场景 3：推理服务延迟抖动

**问题**：vLLM 推理服务 P99 延迟从 200ms 飙升到 5s，但 GPU 利用率正常，如何排查？

```
Step 1: 指标对比
  - GPU 利用率 vs 延迟 → 确认瓶颈不在 GPU 算力
  - GPU 温度/频率 → 检查是否降频（Throttle Reason）
  - KV Cache 使用率 → 是否接近显存上限
  - 请求队列长度 → 是否有突发流量

Step 2: 逐层排查
  - GPU 层面：nvidia-smi dmon → 检查 SM/Memory/Encoder 利用率
  - 推理框架：vLLM metrics → prefill_time vs decode_time
  - 网络层面：是否有高延迟请求源
  - 系统层面：CPU 是否饱和、是否有 NUMA 跨节点访问

Step 3: 常见根因与解决
  ┌─────────────────────┬───────────────────────────────────┐
  │ 根因                  │ 解决                              │
  ├─────────────────────┼───────────────────────────────────┤
  │ KV Cache 膨胀        │ 限制 max_num_seqs / 启用 Prefix Caching│
  │ 长序列请求           │ 限制 max_model_len / 队列拒绝     │
  │ GPU 降频             │ 环境降温 / 驱动调优                │
  │ Prefill 阻塞 Decode  │ P/D 分离部署 / Chunked Prefill     │
  │ CPU 瓶颈（tokenizer）  │ 增加 CPU / 分离 Tokenizer 服务     │
  └─────────────────────┴───────────────────────────────────┘
```

### 场景 4：设计万卡训练平台

**问题**：请设计一个支持 10000 张 H100 的大模型训练平台。

**架构设计要点**：

```
┌─────────────────────────────────────────────────────────┐
│                     用户层                               │
│  Web UI / CLI / API → 提交训练任务                        │
├─────────────────────────────────────────────────────────┤
│                     调度层                               │
│  Volcano / Yunikorn (Gang Scheduling, Queue, Priority)   │
│  + 自定义 GPU 拓扑调度插件（NVLink + NUMA 感知）          │
├─────────────────────────────────────────────────────────┤
│                     计算层                               │
│  10000 × H100 (8-GPU × 1250 nodes)                      │
│  网络: InfiniBand NDR400 + NVSwitch (Rail-optimized)     │
│  K8s + NVIDIA GPU Operator + MPI Operator                │
├─────────────────────────────────────────────────────────┤
│                     存储层                               │
│  Lustre (热) → 本地 NVMe (缓存) → S3/COS (冷)            │
│  Checkpoint: Async → NVMe → COS                          │
├─────────────────────────────────────────────────────────┤
│                     可观测性                             │
│  DCGM + Prometheus + Grafana + Loki + Jaeger            │
│  全链路: GPU 指标 → NCCL 通信 → 训练 Loss → 排队时间     │
├─────────────────────────────────────────────────────────┤
│                     容灾与高可用                          │
│  多机房部署 (Active-Standby)                              │
│  故障域: Rack-aware Scheduling                           │
│  自愈: 自动检测 GPU 故障 → 下线 → 替换 → 恢复训练        │
│  Checkpoint 跨机房同步（30min 间隔）                      │
└─────────────────────────────────────────────────────────┘

关键设计决策：
1. 调度器选型：Volcano vs 自研 → 万卡规模需考虑调度吞吐
2. 网络拓扑：Rail-optimized 拓扑（8 rail × 1250 GPU）
3. 故障自愈：GPU 故障自动检测 + Checkpoint 恢复
4. 存储架构：多级缓存减轻 Lustre 压力
5. 资源效率：MIG 用于推理/小任务，完整 GPU 用于大训练
```

---

## 第十三章 模拟面试问答

### Q1：Pod 从创建到运行在 GPU 节点的全流程？

```
1. kubectl apply / API Server 接收请求 → 写入 etcd
2. Scheduler 监听到新 Pod（未绑定 NodeName）
3. Filter 阶段：过滤不满足条件的节点
   - NodeSelector / NodeAffinity 匹配
   - 检查 nvidia.com/gpu 资源是否足够
   - 检查 Taint/Toleration
4. Score 阶段：为候选节点打分
   - 默认策略：LeastRequestedPriority / BalancedResourceAllocation
   - GPU 拓扑插件（如有）：优选 NVLink 互联的 GPU
5. 选定最优节点 → 绑定 Pod 到节点 → 更新 etcd
6. Kubelet watch 到 Pod → 调用 CRI 创建容器
7. NVIDIA Device Plugin → Allocate GPU → 设置环境变量
   - NVIDIA_VISIBLE_DEVICES=GPU-xxxx
   - 挂载 /dev/nvidia* 到容器
8. nvidia-container-runtime → 注入驱动库 → 启动容器
9. CNI 分配 Pod IP → Pod Running
```

### Q2：如何实现 GPU 故障自动检测和自愈？

```
方案设计：

1. 检测层（DaemonSet：GPU Health Checker）
   - DCGM 指标采集（ECC Error、Xid、Temperature）
   - 定期运行 GPU Burn Test / nvidia-smi health check
   - 检测 PCIe 链路状态、NVLink 状态

2. 判定层（PrometheusRule + Controller）
   - ECC Uncorrectable Error（Xid 13/48）→ Critical, 立即标记
   - Persistent Correctable ECC > threshold → 标记为 Degraded
   - GPU 掉卡（Xid 45/79）→ Critical
   
3. 执行层（GPU Node Controller，CRD: Gpunode）
   State Machine:
   Healthy → (检测到故障) → Degraded → Cordon Node
                                      → Drain GPU Pods
                                      → Taint Node (gpu-fault=critical:NoSchedule)
                                      → 通知运维 / 自动创建工单
                                      → Failed → (RMA 完成挂回) → Healthy

4. 训练任务恢复
   - TorchElastic 检测到 Worker 退出 → 自动重新分配
   - 从最新 Checkpoint 恢复训练
```

### Q3：NCCL_GID_INDEX 作用及如何确定值？

```
背景：为什么需要 GID Index？

在 RoCEv2 网络中，每个 RDMA 设备端口配置了多个 GID (Global Identifier)，
类似于一个网卡有多个 IP 地址。NCCL 需要知道用哪个"地址"来建立 RDMA 连接。

GID 的结构：
GID = 子网前缀 (8 bytes) + 接口标识 (8 bytes)
- RoCEv1 GID：基于 MAC 地址，仅限同一广播域
- RoCEv2 GID：基于 IP 地址，支持路由（跨子网）

RoCEv2 的两种封装版本：
- RoCEv2 v1：使用 GRH (Global Routing Header)，GID 基于 IPv4 或 IPv6
- RoCEv2 v2：使用 IP/UDP 封装 + 可路由 RoCE (RRoCE)，GID 基于 IPv4

典型 GID 表：
$ show_gids
DEV     PORT    INDEX   GID                                  IPv4            VER     DEV
---     ----    -----   ---                                  ------------    ---     ---
mlx5_0  1       0       fe80:0000:0000:0000:...                             v1      eth0
mlx5_0  1       1       fe80:0000:0000:0000:...                             v2      eth0
mlx5_0  1       2       0000:0000:0000:0000:0000:ffff:c0a8:0064 192.168.0.100 v1   eth0
mlx5_0  1       3       0000:0000:0000:0000:0000:ffff:c0a8:0064 192.168.0.100 v2   eth0
                                                        ↑
                                              IPv4 地址：192.168.0.100

选择策略：
1. 找到有 IPv4 地址的条目
2. 在同一 IPv4 地址的条目中，选择 VER=v2（RoCEv2）而非 v1（RoCEv1）
3. 最终选择 Index 3

为什么错误配置后果严重？
- GID_INDEX 错误 → NCCL 无法通过 RDMA 建立连接
- NCCL 会 fallback 到 TCP/IP Socket（可通过 NCCL_IB_DISABLE=1 强制 TCP 来验证）
- TCP 带宽通常只有 IB 的 1/10 ~ 1/100 → 训练速度骤降

实际排查案例：
现象：训练从 8 卡扩展到 16 卡后，速度没有线性增长
排查：
  1. NCCL_DEBUG=INFO 日志显示 "NCCL WARN NET/IB : No device found"
  2. show_gids 发现 16 卡集群中新增的节点 GID 配置不一致
  3. 统一 GID_INDEX=3 后，16 卡训练速度恢复线性 scaling
```

### Q4：如何处理 GPU 节点频繁 OOM？

```
分析维度：
1. 确认 OOM 类型
   - Pod OOM (Cgroup Killer) → 查看 Pod events + kubectl describe
   - Node OOM → dmesg | grep -i "out of memory"
   - GPU OOM (CUDA Out of Memory) → 训练日志 CUDA error

2. 根因分类
   ┌─────────────────┬─────────────────────────────────────┐
   │ 类型              │ 根因                                │
   ├─────────────────┼─────────────────────────────────────┤
   │ 内存 Request < 实际 │ 预留不足，训练时被 Cgroup Kill       │
   │ 内存泄漏          │ 训练代码未释放中间变量                  │
   │ 多个进程争抢      │ GPU Pod + Sidecar 争抢 Host 内存      │
   │ 数据加载过大      │ DataLoader num_workers × prefetch    │
   │ NUMA 不均衡      │ 跨 NUMA 访问导致慢路径 + 内存堆积       │
   └─────────────────┴─────────────────────────────────────┘

3. 解决
   - 设置合理的 memory request = limit（Guaranteed QoS）
   - 限制 DataLoader workers 数量
   - 启用 Gradient Checkpointing（显存换计算）
   - 监控进程内存使用（container_memory_working_set_bytes）
```

### Q5：Kata Containers 在 ML 场景的适用性？

```
适用场景：
  ✓ 推理服务多租户隔离（安全要求高）
  ✓ 不可信代码执行（用户自定义模型/算子）
  ✓ 合规要求（需要 VM 级别隔离）

不适用场景：
  ✗ 大规模分布式训练（性能敏感，通信开销）
  ✗ GPU 设备需要热迁移的场景
  ✗ 启动延迟敏感的场景（冷启动 > 200ms）

性能对比：
  GPU 计算：Kata 损耗 < 2%（GPU 透传后接近原生）
  GPU 显存：Kata 损耗 < 1%
  磁盘 IO：Kata 损耗 5-15%（VM 层开销）
  网络：Kata 损耗 3-10%（虚拟化网络栈）

决策树：
  安全隔离必须？ → Yes → Kata
  No → GPU 性能敏感？ → Yes → runc
        No → → Kata 也可以
```

---

## 第十四章 行为面试准备

> JD 要求#5~6 明确提出：责任心、学习能力、沟通自驱力、团队合作、逻辑分析能力。字节面试行为面权重不低，必须准备 STAR 故事。

### 1 STAR 法则模板

```
S - Situation  (背景): 当时是什么场景？什么项目？什么角色？
T - Task       (任务): 需要达成的目标是什么？有什么约束？
A - Action     (行动): 你具体做了什么？关键决策是什么？为什么这么选？
R - Result     (结果): 带来了什么可量化的效果？学到了什么？

关键原则：
  - 所有 Action 都要说"我"做了什么，而非"我们"
  - Result 必须有数据支撑（利用率 45%→72%、MTTR 2h→30min）
  - 控制在 3-5 分钟，不要说教
```

### 2 8 个高频行为问题 + 故事框架

#### Q1：最有成就感的稳定性优化项目？（责任心 + 技术深度）

```
推荐方向：
  - 发现并解决了一个长期被忽视的 GPU 集群故障
  - 系统性地提升了某个关键 SLI（如训练成功率从 92%→99%）

故事示例框架：
  S: GPU 训练集群每月有 5-8 次非预期中断，算法团队投诉频繁
  T: 需要将训练中断率降低到每月 < 1 次
  A:
    - 分析了 3 个月的中断日志，发现 60% 是 GPU ECC 错误未被及时发现
    - 搭建 DCGM + Prometheus + AlertManager 告警链路
    - 开发 GPU Health Controller（Go），自动标记故障节点并驱逐任务
    - 推动建立 GPU 节点定期巡检机制
  R:
    - 训练中断率从 5-8 次/月 → 0.5 次/月（↓93%）
    - 故障响应时间从"用户报障" → "自动告警"，MTTD 从 30min → 2min
    - GPU 节点可用性从 99.5% → 99.95%
```

#### Q2：如何推动跨团队合作解决一个棘手问题？（沟通 + 推动力）

```
故事示例框架：
  S: 算法团队提交了一个训练任务需要 512 张 H100，集群只有 300 张空闲
  T: 需要在 2 周内为这个任务协调出足够的 GPU 资源
  A:
    - 和算法团队沟通，分析任务的实际峰值 GPU 使用（发现平均只需 400 张）
    - 推动算法侧使用 FSDP 降低单卡显存需求
    - 和资源规划团队沟通，临时调配其他业务的闲置 GPU
    - 建立了 GPU 资源优先级机制（Volcano Queue），后续类似问题有章可循
  R:
    - 任务如期启动，实际使用 380 张 GPU（比预期少 25%）
    - 推动建立了 GPU 资源优先级制度，后续资源协调效率提升 50%
```

#### Q3：讲一个你通过数据分析驱动决策的例子？（逻辑分析 + 数据驱动）

```
故事示例框架：
  S: 管理层计划采购 200 张新 GPU，但不清楚实际缺口
  T: 需要提供数据支撑的资源规划建议
  A:
    - 分析了 6 个月的 GPU 使用趋势（Prometheus历史数据）
    - 区分了不同业务线的 GPU 使用模式（训练 vs 推理）
    - 计算了利用率优化空间（MIG分片、空闲回收 可释放约 15% GPU）
    - 建立线性回归预测模型，预估未来 6 个月需求
  R:
    - 建议采购 120 张（而非 200 张），节省约 2400 万元
    - 同时给出利用率优化方案，整体 GPU 效率从 45% → 58%
```

#### Q4：讲一个你快速学习新技术并落地的案例？（学习能力 + 自驱力）

```
故事示例框架：
  S: 团队需要上线大模型推理服务，之前团队和本人都没接触过 vLLM
  T: 2 周内完成 vLLM 部署和压测，支持新业务上线
  A:
    - 第一周：阅读 vLLM 源码中的 PagedAttention / Continuous Batching 实现
    - 搭建测试环境，压测不同 TP/PP 配置和大小的吞吐和延迟
    - 输出《vLLM 生产部署最佳实践》文档（含参数调优指南）
    - 第二周：编写 Helm Chart + HPA 配置，灰度上线
  R:
    - 推理服务在 2 周内上线，支持了 2 个新业务线
    - 文档被团队其他成员在后续部署中复用
```

#### Q5：如何处理过生产环境紧急故障？（责任心 + 压力下决策）

```
故事示例框架：
  S: 凌晨 2 点，核心训练任务的 64 个节点全部 GPU 利用率归零，任务 Hang
  T: 需要在 30 分钟内恢复，训练不能中断超过 1 小时（SLO 要求）
  A:
    - 快速诊断：检查 Prometheus → 发现 1 个节点的 InfiniBand link down
    - 这个节点的 NCCL Ring 通信阻塞了整个训练
    - 决策：(1) 短期：隔离故障节点，从 Checkpoint 恢复 → 关键是要快
           (2) 而非 debug 网络根因（耗时不确定）
    - 通知算法团队当前进度和预计恢复时间
    - 训练恢复后，排查网络根因（交换机端口故障）
  R:
    - 训练在 22 分钟内恢复（RTO < SLO）
    - 后续建立了自动检测 + 自动隔离链路故障节点的机制
    - 在复盘会上推动了网络监控告警的完善
```

#### Q6：如何对业务逻辑进行抽象和拆分？（逻辑分析）

```
故事示例框架：
  S: 不同的算法团队各自提交训练任务的方式不统一（curl / Python SDK / 直接 kubectl）
  T: 需要设计一个统一的训练任务提交平台
  A:
    - 调研各团队的训练流程，抽象出通用模型：
      TrainingJob CRD = 镜像 + 资源规格 + 训练脚本 + 环境变量 + 数据集 + 输出路径
    - 将变体通过不同的训练模板（Template）管理
    - 上层统一 API → 下发到 Volcano → K8s
  R:
    - 训练任务提交时间从 30min → 3min
    - 新模型类型接入从"代码改动" → "新增模板配置"
```

#### Q7：如何与算法/研究团队沟通？（团队合作）

```
要点：
  - 算法工程师关心"我的训练能不能跑、什么时候跑完"
  - SRE 关心"集群稳定性、资源效率、成本"
  - 关键：用对方的语言沟通，给算法提供"预期时间"和"状态可视化"
  - 具体做法：
    - 建了训练任务看板（Grafana Dashboard）：排队位置、预计开始时间、GPU 使用率
    - 制定 GPU 使用公约（如：长时间空闲未使用 GPU 需释放）
    - 定期 sync 会议，同步集群状态和即将到来的大任务
```

#### Q8：你遇到过最大的技术挑战是什么？（综合能力）

```
推荐思路：
  - 选一个体现多方面能力的项目（技术深度 + 沟通 + 项目管理）
  - 比如：从零搭建了公司的 GPU 训练平台
  - 或者：解决了某个困扰团队数月的神秘 GPU 故障

结构：
  S: 当时还没有统一的 GPU 训练平台，各团队各自管理自己的 GPU
  T: 需要搭建一个共享 GPU 训练平台，支持多团队、多优先级
  A:
    - 技术选型：K8s + Volcano + PyTorch Operator
    - 难点1：GPU 拓扑感知调度 → 自研 Scheduler Plugin
    - 难点2：多租户 GPU 隔离 → MIG + Kata 组合方案
    - 难点3：Checkpoint 多级缓存（NVMe → COS）
  R:
    - 平台上线后，GPU 利用率从 35% → 62%
    - 训练任务平均排队时间从 4h → 30min
    - 支撑了 5 倍的任务量增长，运维人员没有增加
```

### 3 行为面试的常见错误

```
❌ 错误1：用"我们"代替"我"
   → 面试官想知道你做了什么，不是你的团队做了什么

❌ 错误2：只有定性没有定量
   → "提升了很多" → 不如 "从 45% 提升到 72%"

❌ 错误3：过于技术细节
   → 行为面不是技术面，不要陷入实现细节

❌ 错误4：没有展现学习/反思
   → 好的 Result 需要包含 "学到了什么" 和 "如何改进"

❌ 错误5：负面评价前同事
   → 即使跨团队协作有摩擦，要用建设性的方式表达
```

---

## 第十五章 速查表

### 1 常用排障命令速查

```shell
# ===== GPU 相关 =====
nvidia-smi                                      # GPU 基本信息
nvidia-smi -q -d TEMPERATURE,POWER,CLOCK,ECC   # 详细信息
nvidia-smi topo -m                              # GPU 拓扑
nvidia-smi dmon -s pucvmet                     # 实时监控
nvidia-smi nvlink -s                            # NVLink 状态
nvidia-smi mig -lgip                            # MIG 能力
nvidia-smi -r                                   # GPU 重置
dmesg | grep -i "NVRM: Xid"                     # Xid 错误查询
nvidia-bug-report.sh                            # 完整诊断报告

# ===== InfiniBand/RDMA =====
ibstat                                          # IB 设备状态
ibv_devinfo -v                                  # RDMA 设备详情
show_gids                                       # GID 表
ib_send_bw -d mlx5_0 -i 1                      # RDMA 带宽测试
mlxlink -d <dev> -m                             # 链路诊断
perfquery -x                                    # 端口错误统计

# ===== NCCL =====
NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=ALL python train.py  # 开启 Debug
NCCL_TOPO_DUMP_FILE=/tmp/nccl_topo.xml                 # 导出拓扑

# ===== K8s GPU =====
kubectl describe node <node> | grep nvidia      # 节点 GPU 信息
kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[].resources.limits["nvidia.com/gpu"] != null)'
kubectl top pod <pod>                           # Pod 资源使用
kubectl logs -n gpu-operator <nvidia-device-plugin-pod>

# ===== 进程 =====
py-spy dump --pid <pid>                         # Python 调用栈
strace -p <pid> -f -e trace=network             # 系统调用追踪
cat /proc/<pid>/status | grep -E "VmRSS|Threads"

# ===== 存储 =====
lfs df -h                                       # Lustre 空间
lfs getstripe /path/to/file                     # 文件条带化
iostat -x 1                                     # 磁盘 IO
```

### 2 关键环境变量

```bash
# NCCL
NCCL_DEBUG=INFO
NCCL_IB_GID_INDEX=3
NCCL_IB_HCA=mlx5_0,mlx5_1
NCCL_NET_GDR_LEVEL=5
NCCL_SOCKET_IFNAME=eth0
NCCL_TIMEOUT=1800
NCCL_IB_QPS_PER_CONNECTION=4

# CUDA
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
CUDA_DEVICE_MAX_CONNECTIONS=1
NCCL_P2P_DISABLE=0
NCCL_IB_DISABLE=0

# PyTorch
TORCH_DISTRIBUTED_DEBUG=DETAIL
TORCH_NCCL_ASYNC_ERROR_HANDLING=1
TORCH_CPP_LOG_LEVEL=INFO
OMP_NUM_THREADS=1                          # 避免 CPU 过载
```

### 3 文档索引

| 文档 | 内容 |
|------|------|
| `K8s.md` | K8s 基础（Pod/Controller/Service/存储/Helm） |
| `K8s_Advanced.md` | K8s 生产进阶（RBAC/HPA/调度/安全/GitOps/TKE） |
| `Prometheus_Observability.md` | Prometheus 全链路可观测性 |
| 本文档 | ML SRE 面试准备（GPU/训练/推理/SRE实践/Go开发/行为面） |

---

> **文档版本**: v1.2  
> **适用岗位**: 机器学习系统 SRE 工程师（Seed）  
> **更新日期**: 2024-07  
> **v1.2 新增**：术语速查表（六大分类、70+ 核心术语定义）；第三章 GPU 背景知识（ECC 详解、Xid 错误机制、软件栈层次）；第四章 分布式训练策略深度解析（DDP/FSDP/TP/PP 工作原理图解、3D Parallel 组合示例、通信量化分析）；第五章 网络背景知识（RDMA 原理对比、RoCEv2 关键配置、为什么网络是训练瓶颈）；第八章 推理服务核心概念（自回归生成两阶段、KV Cache 机制与显存估算）；GPU Operator 组件功能详解表；OOM 三种类型对比与 CUDA OOM 排查方法论；MIG 详细工作原理与选型决策树；Go 开发场景总览；Q3 问答扩展  
> **v1.1 新增**：第八章 推理服务部署（vLLM/TGI/Triton 框架对比、生产部署架构、KEDA 自动扩缩、灰度发布、量化方案）；第九章 多地域容灾与部署（跨地域架构、Checkpoint 同步、混沌工程、多集群管理）；第十章 SRE 最佳实践（SLO/SLI/Error Budget、人效提升、Oncall 故障管理、容量规划方法论）；第十一章 Go 语言 SRE 开发（GPU Node Controller 完整代码、Informer 机制、批量操作模式）；第十四章 行为面试准备（8 道 STAR 故事框架 + 常见错误）  
> **推荐阅读顺序**: 术语速查表（快速建立概念）→ 第一章（JD拆解）→ 第二至七章（核心技术栈）→ 第八至十二章（进阶专题+场景题）→ 第十三至十四章（模拟问答+行为面）→ 第十五章（速查表）
