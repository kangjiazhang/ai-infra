# M3 · GPU 与硬件基建学习计划

> 学习周期：1 周（6 天）
> 建议投入：工作日每天约 2 小时，周六 3～4 小时
> 学习目标：能从"会用 GPU 跑 vLLM"进阶到"能选卡、能接入 K8s、能排查 GPU 故障"——即完成从通用运维到 AI 运维的分水岭跨越。
> 核心产出：《GPU 机型选型与成本对照表》、《GPU 故障排查手册》、`gpu_probe.py` 采集脚本、一份 K8s GPU 接入 manifest 集。

---

## 一、M2 到 M3 的能力衔接

进入 M3 前，应能不看资料解释（全部来自 M2 实测）：

- Decode 为什么是显存带宽密集（memory-bound），带宽对 tokens/s 上限意味着什么
- 本机双 T4 是 `PHB` 互联、无 NVLink、无 P2P 直连，TP=2 的 All-Reduce 要过 CPU
- `nvidia-smi` 显示的 CUDA Version 是驱动支持上限，不是宿主机已装的 Toolkit 版本
- T4 是 Turing（CC 7.5）：无 BF16/FP8 Tensor Core、不支持 MIG
- 两卡 ECC 配置不一致（GPU 0 Disabled / GPU 1 Enabled），GPU 1 有历史 SW Power Capping 计数

M3 要建立的工程闭环：

```text
选型（什么业务用什么卡、多少钱）
  ↓
接入（驱动 / 容器直通 / K8s device plugin / 节点打标）
  ↓
分配（nvidia.com/gpu 如何被 kubelet 独占式分给 Pod）
  ↓
排障（OOM / 掉卡 / Xid / 驱动不匹配 / 性能异常）
```

M3 的最终目标是：

> 面对"买什么卡""为什么 Pod 拿不到 GPU""GPU 报 Xid 了怎么处理""GPU 利用率异常怎么定位"这类问题，能给出有依据的方案和处置流程，而不是只会重启。

---

## 二、固定学习方法

每天按以下节奏进行：

1. **30 分钟原理**：读 NVIDIA 官方文档 / K8s 文档
2. **70 分钟实验**：在本机双 T4 + k3s 上验证，或明确标注"文档结论"
3. **20 分钟复述**：用"机制 → 现象 → 排查动作"讲清当天内容

### 实验纪律（延续 M2）

- 每条关于本机的结论都要有命令输出作为证据，归档到 `python/m3/results/`
- 文档结论（如 H100 MIG 操作）与本机验证结论分开标注，不混写
- 所有 K8s 操作先 `--dry-run`，动节点标签/污点前记录当前状态
- 本机同时是 k3s 节点且有业务 Pod，变更后必须恢复原状

### 建议目录

```text
python/m3/
├── scripts/
│   ├── collect_gpu_env.sh        # nvidia-smi -q / topo / driver 环境快照
│   └── gpu_probe.py              # pynvml 周期采集 → CSV
├── k8s/
│   ├── device-plugin.yaml
│   ├── labels-and-taints.md      # 打标 / 污点操作记录
│   └── gpu-pod-examples.yaml     # nodeSelector / 独占验证用例
├── results/
│   └── gpu-probe-时间戳.csv
└── notes/
    ├── gpu-stack-layering.md     # 软件栈分层图
    └── xid-troubleshooting.md    # Xid 码表（最终并入排查手册）
```

目录仍建在本地 mac 的 study 仓库（与 `python/m2/` 并列），服务器只维护运行副本，同步方式与 M2 相同。

---

## 三、实验环境（复用 M2 已实测机器）

| 项目 | 实测值 | 对 M3 的意义 |
|---|---|---|
| GPU | 2 × Tesla T4（Turing，CC 7.5，Pass-Through 直通） | 软件栈 / device plugin / 排障全部可实操 |
| Driver | `580.126.20`，Persistence Mode 已启用 | 版本兼容实验的锚点 |
| `nvidia-smi` CUDA | `13.0`（驱动支持上限） | 讲"驱动上限 ≠ 已装 Toolkit"的最佳活教材 |
| 卡间互联 | `PHB`，PCIe Gen3 x16，无 NVLink/P2P | topo 解读与互联对比的实物样本 |
| 功耗 | 70 W Power Limit；GPU 1 有 SW Power Capping 计数 | `CLOCK_PERF` 降频排查的现成案例 |
| ECC | GPU 0 Disabled / GPU 1 Enabled | Xid / retired pages / 双 Bit 错误教学样本 |
| K8s | 宿主机 k3s（kubelet + containerd），`llm-lab-m2` 命名空间有 vllm Pod | 直接检验 GPU 是如何被 K8s 分配的 |
| MIG | 不支持 | MIG 用文档学，不做本机实验 |

### T4 的教学边界

- **能实操**：nvidia-smi 全字段、pynvml、Xid 日志检查、device plugin、NFD/打标/污点、容器直通、OOM 演练、性能降频排查
- **只学文档**：MIG 切分、NVLink 拓扑（NV# / NVS#）、FP8、H100/H20 特性
- **明确不做**：拔卡演练、刷驱动（生产机器不动驱动）、CUDA C++ 编程

### Day 0 前置检查（开始 Day 1 前完成）

M2 遗留的 TODO，正好是 M3 Day 4 的输入，先摸清现状：

```bash
kubectl get pods -A | grep -i nvidia        # 是否已有 device plugin / GPU Operator
kubectl describe node <节点> | grep -A5 -i nvidia   # nvidia.com/gpu 是否已注册为资源
kubectl -n llm-lab-m2 describe pod <vllm-pod> # 找 GPU 分配证据（env / resources）
```

结果记录进 `notes/`，Day 4 据此决定"逆向拆解已有链路"还是"从零部署"。

---

# Day 1：GPU 硬件常识——算力、带宽与互联

## 学习内容

### 1.1 算力与带宽，谁先成为瓶颈

FLOPS（每秒浮点运算次数）衡量算力，GB/s 衡量显存带宽。对 LLM 推理：

- **Prefill**：大矩阵并行计算，通常先碰**算力**瓶颈
- **Decode**：每轮读取全部模型权重却只算一个 token，通常先碰**带宽**瓶颈（M1 Day 7 结论）

由此得到选型第一直觉——单流 Decode 吞吐的理论上限：

```text
tokens/s 上限 ≈ 显存带宽 ÷ 每 token 必读数据量（≈ 权重字节）
```

用 M1 的权重显存数字手算 7B FP16（权重 14 GiB）：

| 卡 | 带宽 | 理论 tokens/s 上限 | 说明 |
|---|---:|---:|---|
| T4 | 320 GB/s | ≈ 22 | 单卡口径；TP=2 时每卡只读 7 GiB，理论上限应为 ≈45，M2 实测 16 tok/s，缺口主要来自 PHB All-Reduce |
| A100 80G | ≈ 2039 GB/s | ≈ 145 | — |
| H100 80G | ≈ 3350 GB/s | ≈ 239 | — |

折扣来自 KV Cache 读取、launch 开销、带宽利用率不满、降频等；TP 部署还叠加卡间通信（见下方口径注意）。**这个公式就是"运维为什么必须懂硬件"的证明：换卡的收益能提前算出来。**

**口径注意**：表中数字按"单卡装下全部权重"计算。TP=2 时每卡只持半权重 7 GiB，理论上限应按 7 GiB 计（T4 ≈45 tok/s）；M2 实测 16 tok/s 的缺口，主要来自 PHB 拓扑下过 CPU 的 All-Reduce（M2 Day 11 的分析）。"理论是上限、互联是变量"——这条实证 M3 后续会反复用到。

### 1.2 主流卡对比（建立数量级直觉）

| 卡 | 架构 | 显存 | 带宽 | FP16 Tensor Core（dense） | 互联 | MIG | 典型定位 |
|---|---|---:|---:|---:|---|---|---|
| T4 | Turing | 16G GDDR6 | 320 GB/s | 65 TFLOPS | PCIe | ✗ | 老卡、低成本推理 |
| A10 | Ampere | 24G GDDR6 | 600 GB/s | ≈125 TFLOPS | PCIe | ✗ | 主流推理卡 |
| L20 | Ada | 48G GDDR6 | 864 GB/s | ≈119 TFLOPS | PCIe | ✗ | 大显存推理 |
| L40S | Ada | 48G GDDR6 | 864 GB/s | ≈181 TFLOPS | PCIe | ✗ | 高性能推理/图形 |
| A100 80G | Ampere | 80G HBM2e | ≈2039 GB/s | 312 TFLOPS | NVLink 600 GB/s | ✓ | 上代旗舰，训练+推理 |
| H100 80G | Hopper | 80G HBM3 | ≈3350 GB/s | ≈990 TFLOPS | NVLink 900 GB/s | ✓ | 旗舰，FP8 原生 |
| H20 | Hopper | 96G HBM3 | ≈4000 GB/s | ≈148 TFLOPS | NVLink 900 GB/s | ✓ | 中国特供：带宽高、算力低 |
| H800 | Hopper | 80G HBM3 | ≈3350 GB/s | ≈990 TFLOPS | NVLink 缩减 | ✓ | 中国特供：算力保留、互联降 |

> 表中 TFLOPS 数字仅建立数量级直觉，做正式选型时必须以当期 NVIDIA datasheet 和云厂商规格页为准；H20 是"带宽/算力失衡"的典型样本——对 Decode 密集的推理场景反而没那么差，面试可以拿它举例。

**必须建立的判断**：推理选型先看「显存容量（装不装得下）」再看「带宽（Decode 多快）」，最后才看「算力（Prefill/量化反算）」。这和训练选型（算力优先）正好相反。

### 1.3 算力的水分

- **稀疏算力**：Ampere 及以后支持 2:4 结构化稀疏，datasheet 标 ×2 的都是稀疏值；LLM 推理一般拿不到
- **峰值条件**：TFLOPS 是理想大矩阵 + 满频率下的理论值；本机 70 W 功耗墙下降频后实际算力低于标称
- **低精度膨胀**：T4 标称 INT4 260 TOPS，是 batch 理想化数字，与真实 LLM 服务吞吐没有直接换算关系
- **利用率口径**：M2 已验证 GPU Util 高 ≠ 真实算力占用，M6 会用 `SM_ACTIVE / PIPE_TENSOR_ACTIVE` 补齐这块

### 1.4 卡间互联（本机实物）

`nvidia-smi topo -m` 的 legend 解读：

| 标记 | 含义 |
|---|---|
| `NV#` | NVLink 直连（HBM 级带宽，TP 的理想互联） |
| `NVS#` | 经 NVSwitch 全互联（DGX/HGX 机型） |
| `PIX` | 同一 PCIe 交换芯片下直连 |
| `PHB` | 经 CPU 的 PCIe Host Bridge 互联（**本机**，无 P2P） |
| `NODE` / `SYS` | 跨 PCIe Host Bridge / 跨 CPU Socket（QPI/UPI） |

本机 M2 实测：`PHB` 下 TP=2 的 All-Reduce 过 CPU，TPOT 62ms 中通信占相当比例——这就是"选卡时互联拓扑比卡数更重要"的实证。

### 1.5 多机互联（概念级）

- **RDMA**：网卡绕过 CPU 直接读写远端内存，多机训练/推理的延迟基础
- **InfiniBand**：专用无损网络，HPC/大规模训练首选
- **RoCE**：RDMA over 以太网，需要 PFC/ECN 保证无损
- **GPUDirect RDMA**：网卡直接读写 GPU 显存，省 CPU 中转
- **与 M2 的连接**：M2 Day 17 分析过 PD 分离的 KV 传输成本由网络决定——生产 PD 分离基本以 RDMA/IB 为前提

## 动手任务

1. 复跑并归档 `nvidia-smi topo -m`，逐行解读本机输出（含 legend）
2. 用 `带宽 ÷ 权重` 公式手算：7B FP16、7B INT4、14B INT4 在 T4/A10/A100 上的单流 Decode 上限，写进 `notes/`
3. 登录 1～2 家云厂商控制台，查 T4/A10/L20/A100 按量与包月价格，开始填《机型选型成本表》（Day 6 定稿）
4. 回答：同样的预算，"2×A10"和"1×A100 40G"分别适合什么负载？

## 当天验收

1. 为什么 LLM 推理选型显存带宽常常比 TFLOPS 更关键？
2. T4 跑 7B FP16 单流 Decode 理论上限多少？怎么算的？
3. NVLink 和 PCIe 对 TP 各意味着什么？本机是什么拓扑？
4. datasheet 的稀疏算力和实际服务吞吐为什么差距大？

## 验收参考答案

#### 1. 为什么带宽常常更关键？

> 因为 Decode 阶段每生成一个 token 都要把全部模型权重从显存读一遍，计算量却只有一个 token 的规模——属于典型 memory-bound（M1 Day 7）。此时单流速度的上限由"带宽 ÷ 权重字节"决定，算力再高也快不过数据搬运。本机实证：7B TP=2 的 TPOT 62ms ≈ 16 tok/s，已接近 T4 320 GB/s ÷ 7 GiB（每卡一半权重）× 折扣的理论区间；同卡上把模型换小一倍，TPOT 几乎线性变好——瓶颈在带宽不在算力。

#### 2. 理论上限怎么算？

> `tokens/s ≈ 带宽 ÷ 每 token 必读字节数`。公式要选对口径：**单卡口径**（假想一张 T4 装下全部 14 GiB）320/14 ≈ 22 tok/s——但 M2 已证明 7B FP16 单 T4 装不下，这只是教学口径；**TP=2 口径**（每卡只读半权重 7 GiB）320/7 ≈ 45 tok/s 理论上限，M2 实测 16 tok/s，缺口主要来自 PHB All-Reduce、KV Cache 读取、launch 空泡与降频。价值有两层：换卡前就能预估收益；TP 场景必须把"互联"纳入公式，否则会严重高估。

#### 3. NVLink 与 PCIe 对 TP 的意义？

> TP 每层都要 All-Reduce，通信时间 = 数据量 ÷ 互联带宽，是串行压在每一步上的刚性成本（M2 Day 11）。NVLink（300+ GB/s、点对点直连）让通信占比小，接近线性加速；PCIe（Gen3 x16 约 12～16 GB/s）且无 P2P 时数据还要经 CPU 中转，通信可能支配单步时间——本机 `PHB` 拓扑 TP=2 主要解决容量而非性能，实测 TPOT 的相当比例花在通信上。所以"几卡"要和"什么互联"一起看，DGX/HGX 的 NVSwitch 全互联是溢价的原因。

#### 4. 稀疏算力为什么拿不到？

> 稀疏 ×2 需要 2:4 结构化稀疏（Ampere+），要求权重每 4 个元素有 2 个零且推理路径支持跳零计算；通用 LLM 权重不满足该结构，实际服务里几乎不可能拿到标称翻倍。同理，峰值 TFLOPS 假设满频 + 大矩阵 + 无访存等待，LLM Decode 的小 kernel + 带宽等待 + 功耗降频都会打折。选型时只看 dense 值，并把 datasheet 数字当"上限"而非"预期"。

---

# Day 2：NVIDIA 软件栈分层与容器 GPU 直通

## 学习内容

### 2.1 软件栈分层（必须能默画）

```text
┌─────────────────────────────────────────────┐
│ 应用层    vLLM / PyTorch                      │
├─────────────────────────────────────────────┤
│ 通信库    NCCL（多卡 All-Reduce/多机通信）      │
├─────────────────────────────────────────────┤
│ 算子库    cuDNN / cuBLAS（矩阵与深度学习算子）  │
├─────────────────────────────────────────────┤
│ CUDA     Runtime（libcudart，随应用/容器走）    │
│          编译工具 nvcc、驱动 API（libcuda）     │
├─────────────────────────────────────────────┤
│ 驱动     NVIDIA Driver（内核模块 + libcuda +    │
│          NVML）        ← 宿主机只需要这一层     │
├─────────────────────────────────────────────┤
│ 硬件     GPU                                   │
└─────────────────────────────────────────────┘
```

各层一句话职责：

- **Driver**：内核态管理 GPU、提供 `libcuda`（驱动 API）和 NVML（监控接口）。装在宿主机，升级需要停机
- **CUDA Toolkit**：开发/运行时（nvcc、libcudart、profiler）。**应用镜像自带，不需要装在宿主机**
- **cuDNN/cuBLAS**：深度学习/矩阵算子库，PyTorch wheel 或镜像内自带
- **NCCL**：卡间/机间集合通信库，TP 的 All-Reduce 靠它
- **PyTorch/vLLM**：通过以上各层调用 GPU

### 2.2 版本兼容三条规则

1. **驱动是上限**：CUDA Runtime 要求 驱动 ≥ 其版本。`nvidia-smi` 右上角的 CUDA Version（本机 13.0）= 该驱动能支持的最高 CUDA 版本，不是已安装版本
2. **容器自带 Runtime**：vLLM/PyTorch 镜像里打包了自己的 CUDA Runtime 和 cuDNN；宿主机只装驱动。所以"宿主机没装 CUDA"也能跑 GPU 容器
3. **Minor Version Compatibility**：同为 12.x 的 Runtime 可在支持 12.0+ 的驱动上运行；跨大版本（11.x vs 12.x）才要严格匹配

**排查模板**：`CUDA driver version is insufficient for CUDA runtime version` → 先 `nvidia-smi` 看驱动，再查镜像要求的 CUDA 大版本，结论永远是"升驱动或换镜像"。

### 2.3 nvidia-container-toolkit 直通原理

裸容器看不到 GPU——device、驱动库都在宿主机。toolkit 的作用：

```text
kubelet / docker
  ↓ 传入 NVIDIA_VISIBLE_DEVICES=0,1 等环境变量
nvidia-container-runtime（替换/包装默认 runtime）
  ↓ 注入 /dev/nvidia* 设备 + libcuda/NVML 等驱动库 + 必要挂载
容器内进程可以 nvidia-smi、访问 GPU
```

两种模式：

- **legacy**：靠 `NVIDIA_VISIBLE_DEVICES` 等环境变量 + runtime hook（传统方式）
- **CDI**（Container Device Interface）：以设备描述符方式声明，K8s 1.28+ 生态推荐，更干净

### 2.4 把本机版本画进分层图

| 层 | 本机值 |
|---|---|
| Driver | `580.126.20`，Persistence Mode 开 |
| 驱动支持 CUDA | 13.0（上限） |
| 容器内 CUDA/PyTorch/vLLM | M2 Day 1 已采集（`collect_env.sh` 输出） |
| container toolkit / CDI | Day 0 检查结果 |

## 动手任务

1. 画软件栈分层图（`notes/gpu-stack-layering.md`），把本机每层实际版本标注上去
2. 宿主机与 vllm 容器内分别执行 `nvidia-smi`、`cat /proc/driver/nvidia/version`，确认驱动一致、CUDA Runtime 只在容器内
3. 在容器内执行 `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"`，记录三段版本
4. 追踪 M2 的 vllm-smoke Pod 是怎么拿到 GPU 的：`kubectl describe pod` 找 `nvidia.com/gpu` 资源与容器 env，`crictl inspect` 看 runtime 与设备注入（能做多少做多少）
5. 产出《本机版本兼容矩阵》三行表（对齐大纲"驱动 ↔ CUDA ↔ vLLM/PyTorch"）：Driver `580.126.20` → 支持的 CUDA 上限 13.0；容器内 vLLM/PyTorch → 实际 CUDA Runtime（`torch.version.cuda`）；结论行——当前组合是否兼容、升驱动/换镜像各自解锁什么
6. 跑一个**不请求 GPU 资源的普通容器**，验证它看不到 `/dev/nvidia*`（直通是按需注入，不是全局可见）

## 当天验收

1. 宿主机需要装 CUDA Toolkit 吗？为什么？
2. `nvidia-smi` 显示 CUDA 13.0 代表什么、不代表什么？
3. 容器里的 GPU 可见性由什么机制决定？
4. 报 "CUDA driver version insufficient" 时排查顺序是什么？

## 验收参考答案

#### 1. 宿主机需要装 CUDA Toolkit 吗？

> 不需要。现代 GPU 容器化部署里宿主机只装**驱动**（内核模块 + libcuda + NVML）；CUDA Runtime、cuDNN、NCCL 全部随应用镜像分发。这样多个应用可以用不同 CUDA 版本共享同一台宿主机，驱动机房级统一升级即可。本机正是如此：宿主机只有驱动，vLLM 容器内自带一整套 Runtime。只有裸机直跑 `pip install torch` 且要编译算子时才涉及宿主 Toolkit。

#### 2. CUDA 13.0 代表什么？

> 代表**驱动 580.126.20 能支持的 CUDA Runtime 最高到 13.0**，是能力上限：任何要求 CUDA ≤ 13.0 的镜像都能跑。它不代表宿主机安装了 CUDA Toolkit，也不代表容器内的 CUDA 版本——容器内版本要看镜像（`torch.version.cuda`）。这是"驱动上限 ≠ 实际 Runtime"的活教材，面试常拿来甄别是否真懂分层。

#### 3. GPU 可见性由什么决定？

> 由 nvidia-container-toolkit 决定：kubelet 分配设备后把 GPU ID 写进 `NVIDIA_VISIBLE_DEVICES`（legacy 模式）或 CDI 设备描述，容器 runtime 据此把对应的 `/dev/nvidia*` 设备节点和驱动库注入容器。没请求 GPU 的容器里什么都不会注入——这正是 Day 2 实验验证的现象。也解释了 `CUDA_VISIBLE_DEVICES` 的两个层次：它是 CUDA 层的掩码，在已注入的设备里再选子集，与容器层的注入是两回事。

#### 4. driver version insufficient 的排查顺序？

> ① `nvidia-smi` 看宿主机驱动版本和它支持的 CUDA 上限；② 查应用镜像要求的 CUDA 大版本（release notes / `torch.version.cuda`）；③ 结论二选一——升驱动（需停机窗口）或换低 CUDA 要求的镜像。利用 Minor Version Compatibility：12.x 的镜像只需要驱动支持 12.0+，通常不用精确对齐。禁止用"改环境变量骗过检查"之类的绕过手段——驱动真的不够时运行时必崩。

---

# Day 3：nvidia-smi、NVML 与 Xid 排障

## 学习内容

### 3.1 nvidia-smi 命令族

```bash
nvidia-smi                     # 默认面板：快照
nvidia-smi -l 1                 # 每 1s 刷新（监控用）
nvidia-smi -q                    # 全量详细信息（排障第一入口）
nvidia-smi -q -d CLOCK,PERFORMANCE,ECC,POWER   # 按域查询
nvidia-smi --query-gpu=...       # 结构化输出（脚本/监控采集）
nvidia-smi dmon -s pucvmet       # 每卡逐秒流式指标
nvidia-smi topo -m                # 拓扑（Day 1）
```

### 3.2 面板字段全解读（对照本机）

| 字段 | 含义 | 本机注意点 |
|---|---|---|
| Temp / Perf | 温度 / P 状态（P0 全速，P8 空闲省电） | 空闲时 P8、PCIe 降到 Gen1 属正常（M2 已记录） |
| Pwr / Cap | 实际功耗 / 功耗上限 | 本机 70W 上限；压测时看 `PerfCap` 是否 `SW` |
| Bus-Id / Mem-Util | PCIe 总线 / 显存控制器利用率 | Decode 期常高，与 GPU Util 含义不同 |
| Util GPU | 采样窗口内"有 kernel 在跑"的时间占比 | **有欺骗性**（M1/M2 已证），不等于算力占满 |
| Memory-Usage | 显存占用 | 含权重 + KV Cache + CUDA Context |
| ECC | 纠错位翻转 | 本机 GPU 0 关 / GPU 1 开——对比活教材 |
| GPU Virtualization Mode | 直通/vGPU | 本机显示 Pass Through |

### 3.3 `-q` 深层字段（排障金矿）

- **Persistence Mode**：保持驱动常驻，避免每次初始化开销——本机已启用
- **Clocks Throttle Reasons**（`-d PERFORMANCE`）：`SW Power Cap` = 功耗墙降频。**本机 GPU 1 有历史记录**，压测时复现并归档
- **Retired Pages**：ECC 翻错后 retired 的物理页（Single/Double Bit）；Double Bit 多了要换卡
- **Compute Mode**：Default / Prohibited / Exclusive Process（独占进程）
- **Max Clocks vs 应用时钟**：降频判断的证据链

### 3.4 NVML 与 pynvml

NVML 是 nvidia-smi 背后的 C 库，`pynvml`（`nvidia-ml-py`）是其 Python 绑定——所有自定义 GPU 巡检脚本的基础，也是 M6 dcgm-exporter 之外补充细粒度指标的手段。

### 3.5 Xid 错误码

Xid 是 NVIDIA 驱动对 GPU 事件的编号，出现在 `dmesg` / `journalctl`（形如 `NVRM: Xid (PCI:0000:xx): 79, ...`）。必背子集：

| Xid | 含义 | 处置 |
|---:|---|---|
| 13 | 图形引擎异常 | 通常是应用/驱动 bug，收集日志重试 |
| 31 | GPU 显存页错误 | 常伴随 OOM/越界，查应用 |
| 43 | GPU 停止处理 | 多由外部事件引发，看伴随日志 |
| 45 | 抢占式清理 | 一般为进程被 kill 的正常伴随 |
| 48 | **Double Bit ECC** | 硬件故障信号：记录 → 隔离该卡 → 报修 |
| 63/64 | ECC 页 retired / 行重映射 | 监控 retired 数增长趋势 |
| 79 | **GPU 掉卡（fell off bus）** | 检查 PCIe/供电/散热 → `nvidia-smi -r` 尝试复位 → 失败则报修 |
| 94 | Contained error（受控隔离） | 按事件详情定位具体单元 |
| 119/120 | GSP RM 超时 | 新驱动常见，复位/重启观察 |

**处置总原则**：Xid 不是"重启解决一切"——48/79 这类硬件信号必须保留证据、隔离设备、走报修流程。

## 动手任务

1. 归档 `nvidia-smi -q` 全量输出，逐域标注：哪些字段正常、哪些与基线有差异
2. 复现功耗墙：压测（复用 M2 bench 脚本）期间 `nvidia-smi -q -d PERFORMANCE,CLOCK` 采集，确认 GPU 1 的 `SW Power Cap` 是否 active、SM 时钟降到多少——与 M2 记录的 Max 1590 MHz 对比
3. 编写 `scripts/gpu_probe.py`：用 pynvml 周期采集 `util / mem.used / power / temp / sm_clock / ecc_errors` → CSV，采样间隔与压测窗口可对齐（安装：`pip install nvidia-ml-py`；注意本机 GPU 0 ECC 关闭，其 ECC 字段无意义——正好练习按卡区分采集逻辑）
4. 用 gpu_probe.py 采集一轮 M2 压测全程，产出"时间线三线图"：GPU Util、SM 时钟、Power——预期看到 70W 触顶与时钟回落
5. `dmesg | grep -i -E "xid|nvrm"` 留档（预期为空，形成基线）

## 当天验收

1. GPU Util 的采样语义是什么？为什么它能 100% 而吞吐很低？
2. 功耗墙如何确认？对性能数字有什么影响？
3. Xid 48 和 Xid 79 分别意味着什么、处置差异是什么？
4. pynvml 和 dcgm-exporter 的分工？（为 M6 铺垫）

## 验收参考答案

#### 1. GPU Util 的语义？

> 它表示采样窗口内"至少有一个 kernel 在执行"的时间占比，不区分 kernel 大小、是否在等显存数据。Decode 期大量小 kernel + 带宽等待时，Util 可以接近 100% 而 SM/Tensor 真实占用很低、吞吐很差（M1 Day 7、M2 Day 10 已建立该结论）。判断真实算力占用要看 DCGM 的 `SM_ACTIVE` / `PIPE_TENSOR_ACTIVE`（M6），判断"GPU 到底在忙什么"要结合 Util + 显存带宽 + 时钟 + 吞吐交叉验证——本机 Day 3 实验的四条时间线正是这个交叉验证的雏形。

#### 2. 功耗墙怎么确认？

> `nvidia-smi -q -d PERFORMANCE` 里 `Clocks Throttle Reasons` 出现 `SW`（Software Power Cap）即被功耗墙限制，配合 `-d CLOCK` 可见 SM 时钟低于 Max。本机 70W 上限 + GPU 1 有历史 SW Power Capping 计数，压测大概率复现。影响：所有性能数字都建立在降频后的实际时钟上——这也是 M2 "别人博客的数字不可移植"的物理原因之一；报告里注明压测时段的实际 SM 时钟才算严谨。

#### 3. Xid 48 与 79 的差异？

> **48 = Double Bit ECC**：显存两位翻转、硬件无法自动纠正——这是显存故障的直接证据，处置是记录 `nvidia-smi -q` 的 Retired Pages、把该卡从调度摘除（cordon/去标签）、走报修；它通常不自我恢复。**79 = GPU 从 PCIe 总线消失**：表现是 `nvidia-smi` 突然少一张卡，先查 PCIe 插拔/供电/温度，可尝试 `nvidia-smi -r`（或重启）复位，反复出现则硬件报修。两者共同点：都不是"重启就完事"，区别在故障域（显存 vs 总线/供电）。本机 GPU 1 ECC 开启，若实验中出现 48 类事件，正好按 SOP 走一遍记录流程。

#### 4. pynvml 与 dcgm-exporter 的分工？

> pynvml 是**点/脚本级**采集：巡检、故障快照、实验期间的高频旁路记录（如本日压测时间线），灵活但不成体系。dcgm-exporter（M6）是**服务级监控**：以 Prometheus 指标常驻暴露 DCGM 全量字段，接 Grafana 告警。经验上：排障现场用 pynvml 拍快照，长期水位与告警交给 DCGM；两者同源于 NVML/DCGM 体系，字段语义一致。

---

# Day 4：K8s GPU 接入——device plugin 与 GPU Operator

## 学习内容

### 4.1 device plugin 机制（核心原理）

K8s 原生只认识 CPU/内存，GPU 靠 **device plugin 框架**以扩展资源接入：

```text
NVIDIA device plugin（DaemonSet）
  ↓ 通过 kubelet 的 socket（/var/lib/kubelet/device-plugins/）注册
kubelet Device Manager
  ↓ 把 nvidia.com/gpu 报告为 Extended Resource（capacity/allocatable）
调度器按资源量调度 Pod
  ↓ kubelet 分配具体设备 ID
NVIDIA_VISIBLE_DEVICES=<id>（或 CDI 设备）
  ↓ nvidia-container-toolkit 注入设备与驱动库（Day 2）
容器内可用 GPU
```

关键规则：

- `nvidia.com/gpu` 是**整数资源**：只能 1、2、3，不能要 0.5 张卡，**不能超卖**
- 默认**独占分配**：一张卡同一时刻只给一个 Pod（容器级隔离，非虚拟化）
- 节点重启后 socket 会变，device plugin 必须以 DaemonSet 常驻并支持重新注册

### 4.2 共享的三个层次（为 M5 铺垫）

| 方案 | 隔离性 | 一句话 |
|---|---|---|
| 默认独占 | 强 | 一卡一 Pod，最稳但浪费（M5 开头"80G 卡跑 7B"的问题） |
| Time-slicing | 无 | device plugin 配置多 Pod 分时复用，无显存隔离，一个 OOM 全遭殃 |
| MIG / MPS / HAMi | 中～强 | 硬件切分 / 进程级共享 / 虚拟化，M5 专题 |

### 4.3 GPU Operator（一站式方案）

手动链路 = 驱动 + toolkit + device plugin + （MIG 配置）+ DCGM exporter 各装各的。GPU Operator 用 Operator 模式统一管理：

| 组件 | 职责 | 本机对策 |
|---|---|---|
| nvidia-driver-daemonset | 容器化安装/升级宿主机驱动 | 本机驱动已直通装好，应禁用（driver upgrade 策略） |
| container-toolkit | 注入设备与驱动库 | Day 0 检查现状 |
| device plugin | 注册 `nvidia.com/gpu` | 同上 |
| GPU Feature Discovery | 给节点打 GPU 标签（驱动/CUDA/型号） | Day 5 与 NFD 一起看 |
| mig-manager | MIG 切分管理 | T4 不支持，跳过 |
| dcgm-exporter | GPU 监控指标 | M6 再深入 |
| validator | 安装后自检 | 学习其检查项 |

**选型判断**：机房级标准化、节点多、要 MIG/驱动统一管理 → GPU Operator；小集群/已有驱动直通（如本机 pass-through 场景）→ 手动 device plugin 足够。

### 4.4 趋势一句话（面试加分）

K8s 1.26+ 的 DRA（Dynamic Resource Allocation）正在取代 device plugin 处理 GPU 这类复杂设备，值得知道但当前生产主流仍是 device plugin / GPU Operator。

## 动手任务（本机 k3s）

1. **摸清现状**：`kubectl describe node` 查看 `nvidia.com/gpu` 的 capacity/allocatable；`kubectl get pods -A -o wide | grep -i nvidia` 列出已有 GPU 组件——与 Day 0 结论合并
2. **逆向拆解**：`kubectl -n llm-lab-m2 describe pod <vllm-pod>`，找到 `resources.limits: nvidia.com/gpu: 1` 与 env/CDI 证据，画出 Day 2 学的完整分配链路图（哪个组件在哪个环节起作用）
3. **验证独占**：在剩余 GPU 上同时调度两个各要 1 GPU 的 Pod，第二个应 Pending（`Insufficient nvidia.com/gpu`）；改 `CUDA_VISIBLE_DEVICES` 绕不过 kubelet 层，试一次并解释为什么
4. **（若 Day 0 发现无 plugin）** 手动部署官方 device plugin DaemonSet，验证注册与分配
5. **探针实验**：写一个 `nvidia-smi` 作为命令的 Pod（请求 1 GPU），确认 K8s 分配的卡与宿主机视角一致（`kubectl exec` + `nvidia-smi -L`）

## 当天验收

1. `nvidia.com/gpu` 从注册到容器可用的完整链路是什么？
2. 为什么 GPU 不能像 CPU 那样超卖/按毫核分配？
3. device plugin 和 GPU Operator 是什么关系？
4. Pod 请求了 GPU 但一直 Pending，怎么排查？

## 验收参考答案

#### 1. 完整链路？

> device plugin DaemonSet 向 kubelet 注册设备 → kubelet 把 `nvidia.com/gpu` 计入节点 capacity/allocatable（Extended Resource）→ 调度器按 Pod 的 requests/limits 找够量的节点 → kubelet Device Manager 从可用池里挑出具体设备 ID → 写入 `NVIDIA_VISIBLE_DEVICES`（legacy）或 CDI 描述 → container toolkit 把 `/dev/nvidia*` 和驱动库注入容器 → 容器内进程可见 GPU。本机 Day 4 实验 2 的逆向拆解就是从 Pod 的 limits 和 env 把这条链路两头对上。

#### 2. 为什么不能超卖？

> CPU 的毫核是**分时**抽象，进程天然可抢占调度；GPU 的 `nvidia.com/gpu` 默认是**设备归属**抽象：驱动库、显存、CUDA Context 都是设备级资源，两个不受限的容器共享一张卡会互相踩显存（一个 OOM 可能拖垮另一个）且无法公平计量。K8s 用整数 Extended Resource 表达"独占"这一安全默认值；真正的共享需要额外机制——time-slicing（无隔离）、MIG（硬件切分）、MPS/HAMi（软件虚拟化），这正是 M5 的主题。所以"K8s 不支持 GPU 共享"是错误说法：**默认不支持的是无隔离的共享**。

#### 3. device plugin 与 GPU Operator 的关系？

> device plugin 是 K8s 的**机制**（设备注册与分配的一环），GPU Operator 是基于该机制的**管理方案**——把驱动安装、toolkit、plugin、GFD、MIG 管理、DCGM exporter 全部 Operator 化统一部署和升级。类比：device plugin 是 kubelet 插件协议，GPU Operator 是把整条 GPU 接入流水线打包的"应用商店"。本机驱动 pass-through 已装好，若上 GPU Operator 要显式禁用其 driver 组件避免覆盖宿主机驱动。

#### 4. Pod Pending 怎么排查？

> 按 `kubectl describe pod` 的 Events 分层：① `Insufficient nvidia.com/gpu` → 节点容量不足或被独占（`kubectl describe node` 看 Allocated resources），是调度问题；② 资源够但起不来 → 运行时问题，查容器日志（驱动不兼容、toolkit 缺失、CDI 配置）；③ device plugin 没跑/没注册 → 节点 capacity 里根本没有 `nvidia.com/gpu`，`kubectl get pods -A | grep nvidia` 确认 DaemonSet 状态。顺序永远是"先看节点资源行是否存在，再看是否有余量，最后看运行时"——本机独占实验的 Pending 输出就是第①类的标准现场。

---

# Day 5：NFD、节点打标与 GPU 调度

## 学习内容

### 5.1 为什么要自动打标

GPU 节点与 CPU 节点混布时，调度必须区分。靠人工维护标签（`gpu=true`）会漂移；NFD（Node Feature Discovery）+ GPU Feature Discovery 自动发现并打标：

```text
nvidia.com/gpu.product=Tesla-T4
nvidia.com/gpu.count=2
nvidia.com/gpu.driver_version=580.126.20
nvidia.com/gpu.cuda_version.major=13
feature.node.kubernetes.io/pci-10de.present=true   # NVIDIA vendor ID
```

**运维纪律**：调度选择器用标签（product/feature），不用主机名——机器会替换、标签语义稳定，这是 GitOps 的前提。

### 5.2 污点、容忍与亲和

- **污点（taint）** `nvidia.com/gpu=true:NoSchedule`：默认把普通负载挡在贵卡之外
- **容忍（toleration）**：GPU 工作负载声明它愿意上这个节点
- **nodeAffinity / nodeSelector**：正向选择 GPU 节点
- 三者配合的完整模式：

```yaml
nodeSelector:
  nvidia.com/gpu.product: Tesla-T4   # 正向选择
tolerations:
- key: nvidia.com/gpu
  operator: Equal
  value: "true"
  effect: NoSchedule                 # 容忍污点
```

### 5.3 与 M4/M5 的衔接

- M4：vLLM 的 Helm chart 里就要写这段 selector/toleration 模板
- M5：拓扑感知调度（NVLink 亲和、Binpack/Spread 对 GPU 碎片的影响）建立在今天的基础上
- 排障视角：`kubectl get nodes -o wide` + `kubectl describe node` 的 Taints/Labels 段是"为什么调度到/没调度到这台"的权威答案

## 动手任务

1. 导出本机节点当前 labels 与 taints 快照（`kubectl get node --show-labels`、`kubectl describe node`），归档为基线
2. 手动打标：`kubectl label node <节点> nvidia.com/gpu.product=Tesla-T4`，确认生效
3. 部署两个对照 Pod：
   - A：带 `nodeSelector: nvidia.com/gpu.product: Tesla-T4` → 应落在本节点
   - B：不带任何 selector → 观察它落在哪（说明无污点时普通负载会占 GPU 节点）
4. 给节点加污点 `nvidia.com/gpu=true:NoSchedule`（与 5.2 示例同一 key），验证 B 类 Pod（无容忍）变为 Pending；给 Pod 加容忍后恢复调度
5. 产出 `k8s/labels-and-taints.md`：一份「GPU 节点接入 checklist」（驱动 → toolkit → plugin → 资源注册 → 打标 → 污点），每步带验证命令
6. **清理恢复**：移除实验污点与临时标签，回到基线状态（本机有业务 Pod，纪律）

## 当天验收

1. GPU 节点为什么应该打污点？不打会发生什么？
2. NFD 自动标签和人工标签各适合什么场景？
3. 一个 Pod 调度到了 GPU 节点但没要到 GPU 资源，怎么解释？
4. 调度相关问题的排查命令链是什么？

## 验收参考答案

#### 1. 为什么要打污点？

> 不打污点时，GPU 节点对普通负载完全开放——一个无特殊资源请求的后端 Pod 可能占掉 GPU 节点，导致 GPU Pod 反而调度不进去（"普通负载抢占贵节点"），这是真实生产事故的高频来源。污点把默认策略反转：只有**显式容忍 + 显式选择**的 GPU 负载才进得来。本日实验 4 的对照（加污点前后普通 Pod 的调度变化）就是这个现象的最小复现。

#### 2. 自动标签 vs 人工标签？

> 人工标签适合表达**意图/分组**（`env=prod`、`pool=inference`）；NFD/GFD 自动标签适合表达**硬件事实**（卡型号、驱动版本、PCI 设备存在性）。调度硬件负载必须用事实标签：驱动升级后 `driver_version` 标签自动更新，工作负载可以要求"驱动 ≥ 某版本"——人工维护必然漂移。两者的组合才完整：用意图标签选机房/环境，用事实标签选硬件。

#### 3. 为什么会出现"上了节点但没拿到 GPU"？

> 这是两类资源的解耦：节点选择（selector/亲和/污点）只决定"去哪台机器"，设备分配（`nvidia.com/gpu` 的 requests）决定"拿到什么"。Pod 可以被调度到 GPU 节点但没请求 GPU 资源——它只是和 GPU 做邻居，看不到设备（Day 2 实验 5 验证过）。排障时先分清问的是哪一层：`describe pod` 的 Node 字段回答前者，Resources/Events 回答后者。

#### 4. 排查命令链？

> ① `kubectl get pods -A -o wide`：Pod 在哪个节点/是否 Pending；② `kubectl describe pod`：Events 里的调度失败原因（资源不足/污点不容忍/亲和不匹配）；③ `kubectl describe node`：Labels、Taints、Allocated resources 三段对照——标签对不对、污点挡没挡、GPU 是不是被别的 Pod 占了；④ 需要时 `kubectl get events --sort-by=.lastTimestamp` 看时间线。原则：**调度问题在 node 的三段信息里一定有答案**，先看现场再猜。

---

# Day 6：故障排查实战、机型选型表与 M3 总验收

## 学习内容：四类高频故障的处置框架

| 故障类 | 典型现象 | 证据链 | 处置 |
|---|---|---|---|
| 显存 OOM | Pod CrashLoop / `CUDA out of memory` | 容器日志 + `nvidia-smi` 显存曲线 + M1 显存公式 | 降 `gpu-memory-utilization`/量化/加卡；检查是否有进程泄漏显存 |
| 驱动不匹配 | `CUDA driver version is insufficient` | `nvidia-smi` vs 镜像 CUDA 要求 | 升驱动或换镜像（Day 2 SOP） |
| 掉卡/ECC（Xid 79/48） | `nvidia-smi` 少卡、Xid 日志 | dmesg/journalctl + `-q` Retired Pages | 保留证据 → cordon 摘除 → 复位尝试 → 报修 |
| 性能异常 | Util 高吞吐低/掉频 | Day 3 四线图 + `PERFORMANCE` 域 | 区分带宽瓶颈/降频/小 kernel/调度问题（M2 Day 18 第 8 问的完整版） |

## 动手任务

> Day 6 工作量按周六 3～4 小时预算设计；时间紧时，场景 A 的运行期 OOM 可挪到 Day 3 压测窗口顺手完成。

### 1. 故障演练（可控范围内）

- **场景 A（OOM，实操，两条路径）**：① 启动期——把 `gpu-memory-utilization` 预算调到超出可用显存，预期得到启动期"free memory 不足"类报错（注意：这与运行期 OOM 是**两种不同现场**，日志特征和排查价值不同）；② 运行期——正常启动后用长上下文/高并发把 KV Cache 打满，预期得到 `CUDA out of memory`。两种现场都归档：报错日志特征、`nvidia-smi` 显存水位、Pod 状态变化、恢复操作
- **场景 B（驱动不匹配，推演）**：写一个要求更高 CUDA 大版本的假想镜像案例，按 Day 2 SOP 走一遍判断（不真刷驱动）
- **场景 C（掉卡，推演）**：写 Xid 79 的完整处置剧本：发现（监控/巡检）→ 证据固定（dmesg 时间戳、`nvidia-smi -q` 快照）→ 隔离（cordon + 去 GPU 标签）→ 复位尝试 → 报修交接单内容

### 2. 定稿《GPU 故障排查手册》

必含：Xid 码速查表、四类故障 SOP（现象→证据→动作）、日常巡检项清单（基于 `gpu_probe.py` 的字段）、升级路径（什么情况必须报修而不是重启）。

### 3. 定稿《GPU 机型选型与成本对照表》

结构（价格当日云控制台核实，标注查询日期）：

| 维度 | 内容 |
|---|---|
| 规格区 | Day 1 的八卡对比表 + 云上实例规格（vCPU/内存/本地盘） |
| 价格区 | 按量 / 包月 / 抢占式三档 × 目标卡型 |
| 选型区 | 按负载画像给推荐：7B INT4 低并发（T4/A10 单卡）→ 32B（A100/H20 级）→ 高并发旗舰（H100/H800 多卡） |
| 本机实证区 | 用 M2 数据佐证：双 T4 跑 7B 的实测吞吐/成本换算，量化"什么场景 T4 够用" |
| 结论区 | 同预算下"多张小卡 vs 少张大卡"的取舍（容量/互联/运维复杂度） |

### 4. M3 总验收

脱稿回答文末自测题，并把 M3 三个产出物放进 Git 仓库，与 M1/M2 产出物并列。

---

# 四、最终产出物

## 1. `python/m3/scripts/gpu_probe.py`

- [ ] pynvml 采集 util / memory / power / temp / sm_clock / ECC → CSV
- [ ] 采样间隔与压测窗口可对齐
- [ ] 至少一次"压测全程时间线"数据（Util / 时钟 / 功耗三线）

## 2. K8s GPU 接入 manifest 集（`python/m3/k8s/`）

- [ ] device plugin（或现状拆解记录）
- [ ] 打标 / 污点 / selector / toleration 用例
- [ ] 独占分配验证记录（Pending 现场归档）
- [ ] 《GPU 节点接入 checklist》

## 3. 《GPU 机型选型与成本对照表》

- [ ] 八卡规格对比（标注"数字以 datasheet 为准"）
- [ ] 云价格（带查询日期）
- [ ] 按负载画像的选型建议 + 本机实证数据
- [ ] 至少回答：7B / 14B / 32B / 72B 分别推荐什么卡、为什么

## 4. 《GPU 故障排查手册》

- [ ] Xid 码速查表
- [ ] OOM / 驱动不匹配 / 掉卡 / 性能异常四类 SOP
- [ ] 巡检项清单 + 必须报修的判定标准

---

# 五、M3 最终自测题

- [ ] 为什么 LLM 推理选型显存带宽常比 TFLOPS 关键？如何手算单流 Decode 上限？
- [ ] T4 / A10 / A100 / H100 / H20 各自的定位一句话？H20 什么场景反而合适？
- [ ] 稀疏算力的水分在哪？datasheet 数字为什么当上限看？
- [ ] NVLink / NVSwitch / PCIe / RDMA / RoCE / IB 分别解决什么互联需求？
- [ ] 宿主机为什么只需要驱动不需要 CUDA Toolkit？
- [ ] `nvidia-smi` 显示的 CUDA Version 是什么、不是什么？
- [ ] 容器怎么看到 GPU？`NVIDIA_VISIBLE_DEVICES` 和 `CUDA_VISIBLE_DEVICES` 区别？
- [ ] `nvidia.com/gpu` 从注册到分配的完整链路？
- [ ] 为什么 GPU 默认不能超卖？共享有哪些路线（引到 M5）？
- [ ] device plugin 与 GPU Operator 的关系？本机为何可禁用 Operator 的 driver 组件？
- [ ] Xid 48 / 79 / 13 分别怎么处置？什么情况必须报修而不是重启？
- [ ] 功耗墙怎么确认？它如何影响你的压测结论？
- [ ] GPU Util 100% 但吞吐低，完整的排查思路？
- [ ] Pod 请求 GPU 一直 Pending，排查命令链？
- [ ] 为什么 GPU 节点要打污点？普通负载占 GPU 节点怎么发生的？
- [ ] 驱动升级窗口为什么要停机？升级前必须固定哪些版本兼容信息？

---

## 参考答案

每题先用 30～60 秒给出结论，再按追问补充机制、本机证据和工程影响。

### 1. 为什么带宽常比 TFLOPS 关键？怎么手算单流 Decode 上限？

**面试简答：**

> Decode 每生成 1 个 token 都要把全部权重从显存读一遍，计算量却只有 1 个 token 的规模，属于 memory-bound（M1 Day 7）。此时速度上限由"带宽 ÷ 每 token 必读字节"决定，算力再高也只能等数据搬完。

```text
tokens/s 上限 ≈ 显存带宽 ÷ 每 token 必读数据量（≈ 权重字节 + 该步读取的 KV）
```

**两个口径（本机 7B FP16）：**

| 口径 | 计算 | 上限 |
|---|---|---|
| 单卡装全权重（假想，实际 T4 装不下 14 GiB + 运行时） | 320 GB/s ÷ 14 GiB | ≈ 22 tok/s |
| TP=2，每卡读半权重 7 GiB | 320 ÷ 7 | ≈ 45 tok/s |

M2 实测 TP=2 的 TPOT 62ms ≈ **16 tok/s**，只有理论的 36%。缺口来自：PHB 拓扑下过 CPU 的 All-Reduce、KV Cache 读取、launch 空泡、70W 降频。**"换卡前就能预估收益"就是这条公式的运维价值**——同时提醒：TP 场景不把互联算进去，会严重高估。

### 2. 五张卡一句话定位，H20 反而合适在哪？

**面试简答：**

| 卡 | 定位 |
|---|---|
| **T4** | 老卡（Turing）：16G + 320 GB/s，只能低成本跑 7B INT4、边缘/实验 |
| **A10** | 主流推理卡：24G GDDR6 + 600 GB/s，单卡 7B FP16 的起步线 |
| **A100 80G** | 上代旗舰：≈2 TB/s + MIG，训练与大规模推理的主力存量 |
| **H100** | 当前旗舰：3.35 TB/s + NVLink 900 + 原生 FP8 |
| **H20** | 特供"偏科卡"：96G + 4 TB/s 带宽，但 FP16 仅 ≈148 TFLOPS |

**H20 的甜区**：Decode 密集、长上下文、KV Cache 吃紧而**算力不敏感**的推理服务——它的带宽/算力比极端倾斜，恰好匹配 memory-bound 场景；反之 Prefill 密集（长 prompt 首响）和训练任务在它上面是明显浪费。这也说明选型要按"负载是 Prefill 型还是 Decode 型"分，而不是按跑分分。

### 3. 稀疏算力的水分与 datasheet 的定位

**面试简答：**

> datasheet 是"理论峰值"，由三个前提叠加而成：结构化稀疏、满频、理想大矩阵。三者中任何一个不成立，实际数字就会大幅折扣。

**三层水分：**

1. **稀疏 ×2 需要 2:4 结构化稀疏**（Ampere+）：权重每 4 个元素必须恰好 2 个零且推理路径支持跳零，通用 LLM 权重不满足 → 实际拿不到
2. **峰值假设满频 + 大矩阵 + 无访存等待**：Decode 是小 kernel + 带宽等待，远低于峰值；本机 70 W 功耗墙还会降频（第 12 题）
3. **低精度数字膨胀**：T4 标称 INT4 260 TOPS 是理想化 INT4 推理吞吐，与真实 LLM 服务没有换算关系

**结论**：选型只比 dense 值；报告里所有峰值数字都要标注"理论值，受带宽/功耗/内核效率约束"。

### 4. 六种互联各解决什么

**面试简答：**

| 互联 | 解决什么 | 量级/条件 |
|---|---|---|
| **PCIe** | CPU↔GPU、GPU↔网卡/盘的通用总线（共享） | Gen3 x16 ≈ 12~16 GB/s |
| **NVLink** | GPU↔GPU 点对点直连，TP 的 All-Reduce 走它 | 300~900 GB/s |
| **NVSwitch** | 节点内多卡**全互联**交换芯片（DGX/HGX） | 任意两卡高带宽 |
| **RDMA** | 跨机内存直接读写，绕过 CPU 拷贝 | 低延迟、高吞吐 |
| **RoCE** | 在以太网上跑 RDMA，需 PFC/ECN 保证无损 | 通用网络上的 RDMA |
| **InfiniBand** | 专用无损网络，HPC/大规模训练首选 | 最高档 |

**本机实证**：`nvidia-smi topo -m` 显示 `PHB`——两卡无 NVLink、无 P2P，All-Reduce 经 CPU 中转，这是 TP=2 只有 16 tok/s 的主因之一（M2 Day 11）。多机 PD 分离的 KV 传输成本由 RDMA/IB 决定（M2 Day 17）。

### 5. 宿主机为什么只需要驱动？

**面试简答：**

> 驱动（内核模块 + `libcuda` + NVML）装在宿主机；CUDA Runtime、cuDNN、NCCL、PyTorch 全部随镜像分发。这样多个应用可以各带不同 CUDA 版本共享同一驱动，驱动作为机房级基础设施统一升级，宿主环境保持最小。

**三个原因：**

- **版本解耦**：Minor Version Compatibility 下，12.x 镜像只需驱动支持 12.0+，不必精确对齐
- **稳定性**：驱动是内核态组件，升级要停机；其余组件随镜像滚动，不碰宿主
- **最小化**：宿主装 Toolkit 会引入与镜像版本冲突的风险，且没有使用方

**排查模板**：`CUDA driver version is insufficient` → 看驱动上限、查镜像要求 → 升驱动或换镜像，不要绕。

### 6. `nvidia-smi` 的 CUDA Version 是什么、不是什么

**面试简答：**

> 它是**该驱动能支持的最高 CUDA Runtime 版本**（本机 580.126.20 → 13.0），是能力上限。它不是宿主机已安装的 Toolkit 版本，也不是容器内实际运行的 CUDA 版本——后者要看镜像里的 `torch.version.cuda`。

这一句能区分"背过命令"和"懂分层"。本机宿主只有驱动，容器内才是真实 Runtime（Day 2 实验已验证）。

### 7. 容器怎么看到 GPU？两个环境变量的区别

**面试简答：**

> kubelet 分配设备后写入 `NVIDIA_VISIBLE_DEVICES`（legacy）或 CDI 设备描述，**nvidia-container-toolkit** 据此把 `/dev/nvidia*` 与驱动库注入容器。没请求 GPU 的容器里什么都不会注入。

**两个变量层次不同：**

| 变量 | 作用层 | 谁设置 |
|---|---|---|
| `NVIDIA_VISIBLE_DEVICES` | **注入层**：决定哪些 GPU 设备进入容器 | kubelet / runtime |
| `CUDA_VISIBLE_DEVICES` | **CUDA 层**：在已注入设备里再选子集 | 容器内用户/进程 |

**关键推论**：`CUDA_VISIBLE_DEVICES` 改不了"容器有没有 GPU"，只能在已有设备内做掩码——Pod Pending 时设置它毫无用处。

### 8. `nvidia.com/gpu` 从注册到分配的链路

**面试简答：**

```text
device plugin DaemonSet（socket 注册）→ kubelet
  → 节点 capacity/allocatable 出现 nvidia.com/gpu
  → 调度器按 requests/limits 选节点
  → kubelet Device Manager 分配具体设备 ID
  → NVIDIA_VISIBLE_DEVICES / CDI
  → container toolkit 注入设备与驱动库
  → 容器内可见 GPU
```

排障时沿这条链倒查：`describe node` 有无资源行 → 是否已分配满 → 调度条件（污点/选择器）→ 运行时注入（Day 4 的 Pending 现场就是第 0、1 环）。

### 9. 为什么不能超卖？共享有哪些路线

**面试简答：**

> `nvidia.com/gpu` 是整数独占型设备资源。两个不受管控的容器共享一卡：显存互相踩（一个 OOM 可能拖垮另一个）、算力无法公平计量、CUDA Context 互相干扰。K8s 用"整数 + 独占"表达这个安全默认值——**不是 K8s 不支持共享，而是默认不支持"无隔离共享"**。

**共享路线（M5 展开）：**

| 方案 | 隔离性 | 本质 |
|---|---|---|
| device plugin time-slicing | 无 | 分时复用，显存不隔离 |
| NVIDIA MPS | 弱～中 | 进程级共享，统一 Context |
| MIG | 强 | 硬件切分（T4 不支持） |
| HAMi | 中～强 | K8s 原生显存/算力软隔离 |

### 10. device plugin 与 GPU Operator 的关系，为何禁用 driver 组件

**面试简答：**

> device plugin 是 K8s 的**机制**（设备注册与分配的一环）；GPU Operator 是基于该机制的**管理方案**，把驱动、toolkit、plugin、GFD、MIG 管理、DCGM exporter 统一 Operator 化。

**本机禁用 driver 组件的原因**：这台机器的 T4 是 **PCIe Pass-Through 直通**、驱动（580.126.20）已在宿主机装好。Operator 的 driver 容器会尝试安装/管理驱动，与直通场景和既有驱动冲突；而驱动升级本身需要停机（第 16 题）。正确姿势是 `driver.enabled=false`，只让它管 toolkit / plugin / GFD / dcgm。

### 11. Xid 48 / 79 / 13 怎么处置

**面试简答：**

| Xid | 含义 | 处置 |
|---|---|---|
| **48** | Double Bit ECC（显存两位翻转，硬件不可纠） | 固定证据（dmesg 时间戳 + `nvidia-smi -q` Retired Pages）→ cordon + 去 GPU 标签 → **报修** |
| **79** | GPU 掉卡（fell off bus） | 查 PCIe/供电/散热 → 排空进程后尝试 `nvidia-smi -r` 复位 → 反复出现则**报修** |
| **13** | 图形引擎异常（多为应用/驱动 bug） | 收集日志、重试、复现定位，一般不换卡 |

**必须报修而非重启的判定**：任何**硬件域信号**——48、79 反复出现，Retired Pages 持续增长，ECC 双 Bit 计数上升。重启只能让症状暂时消失，代价是每次重启都付出一次冷启动和一次业务中断。本机 GPU 1 ECC 开启，若真出现 48 类事件，正好按 SOP 走一遍证据固定流程。

### 12. 功耗墙怎么确认？如何影响压测结论

**面试简答：**

> `nvidia-smi -q -d PERFORMANCE` 的 `Clocks Throttle Reasons` 出现 **SW Power Cap** 即被功耗墙限制；配合 `-d CLOCK` 对比 SM 实际时钟与 Max（本机 70 W 上限、Max 1590 MHz，GPU 1 还有历史 SW Power Capping 计数）。

**对结论的影响：**

- 所有性能数字都建立在**降频后时钟**上——报告必须记录压测时段实际 SM 时钟，否则数字不可复现
- 解释了"别人博客的数字不可移植"：同型号卡不同功耗策略/散热，结果差一截
- 压测中若温度/功耗触顶，吞吐曲线会出现无法用参数解释的平台期——**先看 throttle 再怀疑参数**

### 13. GPU Util 100% 但吞吐低，怎么排查

**面试简答：**

> Util 只表示"采样窗口内有 kernel 在跑"，不代表算力被高效利用。必须用六个信号交叉验证：SM_ACTIVE、显存带宽、batch 大小、队列深度、抢占、时钟。

```text
① 是否 memory-bound：SM/Tensor Active 低 + 带宽高 → Decode 带宽瓶颈（可能是正常现象）
② batch 是否太小：小 batch → kernel 小 → launch 开销占比高
③ 调度：waiting > 0 且 running < max-num-seqs → 调度/容量问题，不是算力问题
④ KV：gpu_cache_usage_perc 高 + num_preemptions > 0 → 抢占导致反复重算
⑤ 时钟/功耗：throttle active → 降频
⑥ 多卡通信：TP 下 All-Reduce 占比高（本机 PHB）→ 通信等待被算进"忙"
⑦ kernel 选择：日志里的 Attention Backend（T4 只能 TRITON_ATTN，无 FA2）
```

一句话：Util 高只回答"GPU 在忙"，不回答"忙得有没有价值"。

### 14. Pod 请求 GPU 一直 Pending，命令链

**面试简答：**

```bash
kubectl get pods -A -o wide | grep -i nvidia     # device plugin 是否在跑
kubectl describe node <node>                     # ①有无 nvidia.com/gpu ②Allocated 是否满 ③Taints/Labels
kubectl describe pod <pod>                       # Events 里的具体原因
```

| 现象 | 原因 | 动作 |
|---|---|---|
| capacity 里**没有** `nvidia.com/gpu` | device plugin 未注册 | 查 DaemonSet 日志、socket 路径 |
| capacity 有、Allocated 已满 | GPU 被独占 | 释放其他 Pod / 加卡 |
| 资源够但 Pending | 污点不容忍 / 选择器不匹配 | 补 toleration 或改 selector |

### 15. 为什么 GPU 节点要打污点？普通负载怎么占上去

**面试简答：**

> 没有污点时，不请求 GPU 的 Pod 也能被调度到 GPU 节点——节点选择只看"资源够不够"，普通 Pod 的 CPU/内存请求在 GPU 节点上完全能满足。

**后果链**：普通 Pod 占了 GPU 节点 → 该节点 CPU/内存被吃掉 → GPU Pod 调度不进去（或挤上去后 OOM）→ 贵节点上跑着便宜业务。

**修法**：`taint nvidia.com/gpu=true:NoSchedule` + GPU 负载显式 `toleration` + `nodeSelector`（Day 5 模板）。原则：**用"意图 + 事实"双标签描述节点，用污点做准入**，不用主机名。

### 16. 驱动升级为什么要停机？升级前固定哪些信息

**面试简答：**

> 驱动是内核模块（`nvidia.ko`），升级要卸载/重载 → 所有 GPU 进程的 CUDA Context 全部失效、显存复位。无法热升级，必须排空节点。

**升级前必须固定的兼容信息：**

| 项 | 本机当前值（示例） |
|---|---|
| 驱动版本 | 580.126.20 |
| GPU 型号 / 架构 | Tesla T4 / Turing CC 7.5 |
| 各镜像要求的 CUDA Runtime | vLLM 镜像内 `torch.version.cuda` |
| vLLM / PyTorch 版本 | v0.28.0 / 对应 torch |
| NCCL 版本（多卡时） | 随镜像 |
| container-toolkit / CDI 模式 | 当前使用模式 |
| 内核版本 | 影响内核模块编译 |

**流程**：cordon → drain GPU 负载 → 备份版本号与回滚路径 → 升级 → `nvidia-smi` + 冒烟推理（含多卡 TP）验证 → 解封。**升级窗口的停机时长 ≈ 冷启动时长**——这也是 M4 把冷启动治理列为核心议题的原因。

> 16 题里最容易被追问到底的是 **第 1、6、7、11、12、16 题**（带宽直觉、分层认知、注入机制、故障判断、性能归因、运维窗口），建议优先练到能脱稿讲 60 秒再回答追问。

---

# 六、学习资源

| 资源 | 用法 | 优先级 |
|---|---|---|
| NVIDIA `nvidia-smi` 官方文档 | 全字段与 query 语法权威来源 | 最高 |
| NVIDIA Xid Errors 官方文档 | Xid 码表，排查手册的底稿 | 最高 |
| NVIDIA CUDA Compatibility 官方文档 | 驱动/Runtime 兼容规则 | 高 |
| NVIDIA GPU Operator 官方文档 | 组件清单与部署策略 | 高 |
| Kubernetes Device Plugins 文档 | 机制原理 | 高 |
| NVIDIA device plugin GitHub（k8s-device-plugin） | README：time-slicing/CDI/配置 | 高 |
| Node Feature Discovery 文档 | 标签体系 | 中 |
| 各云厂商 GPU 实例规格与价格页 | 成本表数据源（当日核实） | 中 |
| `jimmysong.io` kubernetes-handbook AI Native 章节 | 中文 K8s+GPU 实践 | 中 |

---

# 七、明确取舍与避坑

M3 必须深入：

- 带宽/算力权衡与显存计算（衔接 M1 公式）
- 软件栈分层与版本兼容规则
- `nvidia-smi` / NVML / Xid 排障
- device plugin 分配链路、GPU Operator 组件
- 节点打标 / 污点 / 亲和调度

M3 只需理解，不强求实操：

- MIG 切分（本机 T4 不支持，读文档 + Day 4 表格）
- NVSwitch / IB / RoCE 的底层协议细节（知道选型含义即可）
- GPU 微架构（SM / warp / Tensor Core 到"能读懂指标"的深度为止）
- DRA 等演进方向（知道存在）

明确跳过：

- CUDA C++ 编程、写 kernel
- vGPU / license 体系（非本岗位路径）
- 在生产机器上刷驱动、拔卡演练（用推演替代）

常见误区：

1. **只看卡数和显存选型**，不看带宽与互联——TP 性能会被拓扑杀死（本机 PHB 实证）
2. **拿 datasheet TFLOPS 推算服务吞吐**——峰值≠实际，Decode 先碰带宽墙
3. **宿主机装一堆 CUDA/cuDNN**——分层不清，镜像自带 Runtime
4. **看到 Xid 就重启**——48/79 是硬件证据，先固定证据再谈恢复
5. **人工维护主机名选择器**——机器一换全漂移，用事实标签
6. **GPU 节点不打污点**——普通负载抢占贵节点的经典事故
7. **把 `nvidia-smi` 的 CUDA Version 当已装版本**——它是驱动上限
8. **抄云价不记日期**——价格波动大，成本表必须带查询日期

判断标准：

> 每学一项硬件/接入知识，都问：它如何影响「选型花多少钱、Pod 拿不拿得到卡、故障怎么处置」这三件现场事？影响不到的，降到"了解"档。

---

M3 完成后进入 M4：把 vLLM 用 Helm + ArgoCD 部署到这台 k3s 上——届时本机的 device plugin、标签、污点、探活经验全部直接复用。
