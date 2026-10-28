# Kubernetes 生产实战完全指南

> 整合 `K8s.md`（基础 10 章）与进阶内容（11~29 章），涵盖从入门到生产落地的完整知识体系。

---

## 目录

**前置基础**（原 K8s.md 概要）

- [第一章](#第一章-初识-kubernetes) 初识 Kubernetes — 简介 / 为什么需要 / 能做什么
- [第二章](#第二章-组件架构) 组件 & 架构 — 控制平面 / Node 组件 / 集群搭建
- [第三章](#第三章-pod--container) Pod & Container — 生命周期 / 探针 / 资源限制 / Init / 亲和性
- [第四章](#第四章-controller-控制器) Controller — Deployment / StatefulSet / DaemonSet / Job
- [第五章](#第五章-service) Service — ClusterIP / NodePort / LoadBalancer / 内部通信
- [第六章](#第六章-存储) 存储 — Volume / PV & PVC / StorageClass 动态供给
- [第七章](#第七章-configmap--secret) ConfigMap & Secret — 配置与敏感信息管理
- [第八章](#第八章-ingress) Ingress — 外部流量路由 / Traefik / Ingress Controller
- [第九章](#第九章-命名空间) 命名空间 — 资源隔离与跨命名空间通信
- [第十章](#第十章-helm) Helm — Chart 包管理 / 自定义模板 / 多环境部署

**进阶生产**（本文档主体）

- [第十一章](#第十一章-rbac-权限控制) RBAC 权限控制 — SA / Role / Binding / 多租户隔离
- [第十二章](#第十二章-hpa-自动扩缩容) HPA 自动扩缩容 — CPU/内存/自定义指标 / 冷却原理
- [第十三章](#第十三章-resourcequota--limitrange) ResourceQuota & LimitRange — 配额 / QoS / OOM Score
- [第十四章](#第十四章-networkpolicy-网络策略) NetworkPolicy — 入站/出站 / 命名空间隔离
- [第十五章](#第十五章-调度高级策略) 调度高级策略 — Taint / 拓扑分布 / PDB
- [第十六章](#第十六章-securitycontext-安全上下文) SecurityContext — Capabilities / seccomp / 只读根文件系统
- [第十七章](#第十七章-滚动更新策略详解) 滚动更新详解 — maxSurge / 金丝雀 / 蓝绿部署
- [第十八章](#第十八章-集群运维操作) 集群运维 — Node 维护 / etcd 备份恢复 / kubeadm 升级
- [第十九章](#第十九章-可观测性) 可观测性 — Prometheus+Grafana / Loki / 告警规则
- [第二十章](#第二十章-ingress-高级用法) Ingress 高级 — TLS / cert-manager / 限流 / Gateway API
- [第二十一章](#第二十一章-crd--operator-模式) CRD & Operator — 自定义资源 / Operator 框架
- [第二十二章](#第二十二章-常见故障排查) 常见故障排查 — Pod 异常速查 / 网络 / 存储
- [第二十三章](#第二十三章-生产最佳实践速查表) 生产最佳实践速查表
- [第二十四章](#第二十四章-gitops--argocd) GitOps & ArgoCD — App of Apps / 多集群
- [第二十五章](#第二十五章-云资源集成) 云资源集成 — CSI / ExternalDNS / ExternalSecrets
- [第二十六章](#第二十六章-sidecar-模式) Sidecar 模式 — 日志 / 热更新 / 1.28+ 原生支持
- [第二十七章](#第二十七章-生产环境网络架构) 生产网络架构 — CNI 选型 / Service Mesh / 多集群
- [第二十八章](#第二十八章-servicemonitor--podmonitor-声明式指标采集) ServiceMonitor & PodMonitor — 声明式采集完整指南
- [第二十九章](#第二十九章-腾讯云-tke-生产实践) 腾讯云 TKE — VPC-CNI / BCS / CLB / SidecarSet / HookTemplate

---

## 第一章 初识 Kubernetes

### 1 简介

Kubernetes（k8s）是一个可移植、可扩展的开源平台，用于**管理容器化的工作负载和服务**。Google 2014 年开源，目前是容器编排的事实标准。

### 2 为什么需要 Kubernetes

| 时代 | 问题 |
|------|------|
| 传统部署 | 资源分配不均，一个应用占满服务器 |
| 虚拟化部署 | VM 太重，启动慢，资源利用率低 |
| 容器部署 | 需要手动管理故障转移、负载均衡、滚动更新 |

Kubernetes 解决的核心问题：**将容器运维自动化**。

### 3 Kubernetes 能做什么

- **服务发现与负载均衡**：DNS 名称或 IP 暴露容器，自动分发流量
- **存储编排**：自动挂载本地存储、云存储等
- **自动部署与回滚**：声明期望状态，控制实际状态向其靠拢
- **自愈能力**：重启失败容器、替换/杀死不健康容器
- **密钥与配置管理**：不重建镜像即可更新配置

### 4 Kubernetes 不是 PaaS

- 不限制应用类型（无状态/有状态/数据处理均可）
- 不提供 CI/CD 流水线（需自行集成）
- 不内置中间件/数据库（可运行在集群上）
- 不内置日志/监控/告警（提供集成机制）

---

## 第二章 组件 & 架构

### 1 控制平面组件

| 组件 | 作用 |
|------|------|
| **kube-apiserver** | 集群统一入口，REST API，水平扩展 |
| **etcd** | 一致且高可用的 KV 存储，集群所有数据后端 |
| **kube-scheduler** | 监听新建 Pod，选择最优节点调度 |
| **kube-controller-manager** | 运行控制器（Node/Job/Endpoint/SA 等） |
| **cloud-controller-manager** | 云平台交互（Node/Route/Service 控制器） |

### 2 Node 组件

| 组件 | 作用 |
|------|------|
| **kubelet** | 每个节点上的代理，保证容器在 Pod 中运行 |
| **kube-proxy** | 网络代理，维护节点网络规则（iptables/IPVS） |
| **Container Runtime** | 容器运行时（containerd/CRI-O） |

### 3 集群搭建方式

| 方式 | 特点 |
|------|------|
| **minikube** | 单节点模拟器，仅测试用 |
| **裸机安装**（kubeadm） | 自定义度高，需手动配置 |
| **云平台 TKE** | 可视化搭建，生态齐全（生产推荐） |
| **k3s** | 轻量级，低配置要求 |

### 4 核心原理：控制器调和循环（Reconciliation Loop）

Kubernetes 以**声明式**运作，核心机制是持续不断的调和循环：

```
┌──────────────────────────────────────┐
│  控制器调和循环（每个 Controller）      │
│                                      │
│  ┌──────────┐    ┌──────────────┐   │
│  │ 观察      │───▶│ 对比          │   │
│  │(当前状态) │    │(期望 vs 实际)  │   │
│  └──────────┘    └──────┬───────┘   │
│        ▲                │ 不一致     │
│        │         ┌──────▼───────┐   │
│        └─────────│ 执行          │   │
│                  │(调至期望状态)  │   │
│                  └──────────────┘   │
└──────────────────────────────────────┘
```

**所有 K8s 资源都遵循此模式**：用户声明期望状态（YAML）→ Controller 观察实际状态 → 发现差异 → 执行操作消除差异。

### 5 Scheduler 调度原理

kube-scheduler 为新 Pod 选择节点分为两阶段：

| 阶段 | 说明 | 示例过滤条件 |
|------|------|-------------|
| **Filter（过滤）** | 剔除不满足条件的节点 | 资源不足、污点冲突、端口冲突、NodeSelector 不匹配 |
| **Score（打分）** | 对剩余节点打分排序 | 资源均衡度（LeastRequested）、镜像本地性（ImageLocality）、亲和性权重 |

最终选择**得分最高**的节点。若 Filter 后无可用节点，Pod 保持 `Pending` 状态。

### 6 kube-proxy 代理模式

| 模式 | 原理 | 性能 | 特点 |
|------|------|------|------|
| **iptables** | 随机 iptables 规则链 | 中（O(n)规则遍历） | K8s 默认，大规模集群性能下降 |
| **IPVS** | 内核级 L4 负载均衡 | 高（Hash 表 O(1)） | 支持多种调度算法（rr/lc/sh/dh），生产推荐 |

> IPVS 模式下 kube-proxy 会在节点创建虚拟服务器（VIP），将 Service ClusterIP 关联到后端 Pod IP，通过 Hash 表快速转发。生产环境建议在 kube-proxy ConfigMap 中设置 `mode: ipvs`。

---

## 第三章 Pod & Container

### 1 什么是 Pod

Pod 是 K8s **最小可部署单元**，是一组（一个或多个）容器的集合，共享网络、存储和上下文环境。

**Pod 内部原理**：每个 Pod 启动时都会先创建一个 **Pause 容器**（`gcr.io/google_containers/pause`），它作为 Pod 的 **基础设施容器（Infra Container）**，承担以下核心职责：

| 作用 | 说明 |
|------|------|
| **网络命名空间锚点** | Pause 最先启动并创建网络命名空间，持有 Pod IP。其余容器通过 `--net=container:pause` 加入该命名空间 |
| **IPC 命名空间锚点** | 同一 Pod 内所有容器共享 IPC 命名空间，可通过 System V 信号量 / POSIX 消息队列通信 |
| **PID 命名空间锚点** | 当设置 `shareProcessNamespace: true` 时，Pod 内所有容器共享 PID 命名空间，可互相看到进程 |
| **生命周期守护** | Pause 启动后执行 `pause()` 系统调用永久挂起，几乎不消耗 CPU/内存。它是 Pod 中**第一个启动、最后一个退出**的容器 |

因此 Pod 内所有容器表现为"同一台机器"：
- 通过 `localhost` 互相通信
- 共享同一个 Pod IP，不能绑定相同端口
- 共享挂载的 Volume（存储命名空间隔离由容器运行时处理）

**Pause 创建流程（CRI 视角）**：

```
kubelet → CRI gRPC → containerd/CRI-O → RunPodSandbox → 创建 Pause 容器 + 网络命名空间
         → 然后逐个创建业务容器，加入 Pause 的网络/IPC 命名空间
```

**国内镜像替换**：
```ini
# containerd 配置 /etc/containerd/config.toml
sandbox_image = "registry.aliyuncs.com/google_containers/pause:3.9"
```

### 2 Pod 基本操作

```shell
kubectl get pods -A                              # 查看所有 Pod
kubectl run nginx --image=nginx:1.19             # 快速创建
kubectl apply -f pod.yaml                        # 声明式创建（推荐）
kubectl delete pod <name>                        # 删除
kubectl exec -it <pod> -- bash                   # 进入容器
kubectl logs -f <pod>                            # 查看日志
kubectl describe pod <pod>                       # 查看详情
```

### 3 Pod 生命周期

| 阶段 | 含义 |
|------|------|
| `Pending` | 已被 API Server 接受，但容器尚未创建（等待调度 / 拉取镜像中） |
| `Running` | 已绑定节点，所有容器已创建，至少一个仍在运行或正在启动/重启 |
| `Succeeded` | 所有容器**以退出码 0 终止**（如 Job 完成），且不会再重启 |
| `Failed` | 所有容器终止，且**至少一个退出码非 0 或被系统杀死（OOM）** |
| `Unknown` | 无法获取 Pod 状态（通常是与所在节点通信失败） |

**容器重启回退算法**：容器崩溃后，kubelet 按指数回退重启（10s → 20s → 40s → 80s → ...），最长延迟上限 5 分钟。如果容器连续稳定运行 10 分钟，回退计时器重置。这就是 `CrashLoopBackOff` 中 "BackOff" 的含义。

### 4 容器探针（健康检查）

| 探针 | 作用 | 失败后果 |
|------|------|----------|
| **livenessProbe** | 容器是否存活 | **重启容器** |
| **readinessProbe** | 容器是否就绪（能接受流量） | **移出 Service 的 Endpoints**，不重启 |
| **startupProbe** | 应用是否已启动完成 | **成功前禁用 liveness/readiness**，保护慢启动应用 |

**探测方式**：`exec`（执行命令）、`httpGet`（HTTP 请求）、`tcpSocket`（TCP 检查）、`gRPC`

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `initialDelaySeconds` | 0 | 容器启动后等待多久才开始探测 |
| `periodSeconds` | 10 | 探测频率（每隔多少秒探测一次） |
| `timeoutSeconds` | 1 | 探测超时时间 |
| `failureThreshold` | 3 | 连续失败多少次才判定为失败 |
| `successThreshold` | 1 | 连续成功多少次才判定为成功 |

**完整示例：三种探针同时使用**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-probes
spec:
  containers:
    - name: web
      image: myapp:latest
      ports:
        - containerPort: 8080
      # ① 启动探针：等应用完全启动后再开启健康检查（Java/Go 等慢启动应用必备）
      startupProbe:
        httpGet:
          path: /healthz
          port: 8080
        initialDelaySeconds: 5    # 首次探测等待 5 秒
        periodSeconds: 10          # 每 10 秒探测一次
        failureThreshold: 30       # 最多等 5 分钟（30×10s=300s）
      # ② 存活探针：应用运行时是否卡死/死锁
      livenessProbe:
        httpGet:
          path: /healthz
          port: 8080
        periodSeconds: 15         # 每 15 秒检查一次
        failureThreshold: 3       # 连续 3 次失败 → 重启容器
        timeoutSeconds: 3         # 3 秒无响应算失败
      # ③ 就绪探针：应用是否准备好接受流量
      readinessProbe:
        httpGet:
          path: /ready
          port: 8080
        periodSeconds: 5          # 每 5 秒检查一次
        failureThreshold: 3       # 连续 3 次失败 → 移出 Service
```

**三种探测方式的写法对照**：

```yaml
# 方式 A：HTTP 检查（最常用）
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
    httpHeaders:                  # 可选：自定义 Header
      - name: X-Custom-Header
        value: probe

# 方式 B：TCP 检查（数据库、Redis 等非 HTTP 服务）
readinessProbe:
  tcpSocket:
    port: 6379
  initialDelaySeconds: 5

# 方式 C：命令检查（最灵活）
livenessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - "pgrep -f myapp || exit 1"
  periodSeconds: 10
```

> **避坑**：livenessProbe 不检查外部依赖（数据库、Redis）。如果 livenessProbe 探测依赖 `SELECT * FROM users`，数据库一挂就把所有 Pod 重启了——雪崩。只检查**进程是否存活**即可。

### 5 资源限制

```yaml
resources:
  requests:          # 调度保障量
    cpu: "200m"
    memory: "128Mi"
  limits:            # 硬上限
    cpu: "500m"
    memory: "256Mi"
```

### 6 Init 容器

在应用容器启动前**按顺序**运行的专用容器，每个 Init 容器必须成功退出（exit 0）后，下一个才会启动。

**使用场景**：
- 等待数据库 / Redis / 上游服务就绪
- 初始化配置文件（从外部拉取模板并渲染）
- 执行数据库迁移（migration）
- 设置文件权限（如 `chown` / `chmod`）

**完整示例：等待 MySQL 就绪 + 初始化数据**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp-with-init
spec:
  initContainers:
    # Init 容器 1：等待 MySQL 就绪
    - name: wait-for-mysql
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "等待 MySQL 就绪..."
          until nc -z mysql 3306; do
            echo "MySQL 尚未就绪，2 秒后重试..."
            sleep 2
          done
          echo "MySQL 已就绪！"
    # Init 容器 2：初始化数据库表结构
    - name: migrate-db
      image: mysql:8.0
      command:
        - mysql
        - -h
        - mysql
        - -u
        - root
        - -p$MYSQL_ROOT_PASSWORD
        - -e
        - "CREATE TABLE IF NOT EXISTS users (id INT PRIMARY KEY, name VARCHAR(100));"
      env:
        - name: MYSQL_ROOT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mysql-secret
              key: password
  # 应用容器：Init 全部完成后才启动
  containers:
    - name: webapp
      image: myapp:latest
      ports:
        - containerPort: 8080
```

**Init 容器 vs 应用容器的区别**：

| 特性 | Init 容器 | 应用容器 |
|------|----------|----------|
| 执行顺序 | 严格按序，前一个成功才启动下一个 | 并行启动 |
| 生命周期 | 执行完就退出，不保持运行 | 持续运行 |
| restartPolicy | 失败后按 Pod 的 restartPolicy 重试 | 同左 |
| 资源限制 | `initContainers[].resources` | `containers[].resources` |
| 探针 | ❌ 不支持 | ✅ 支持三种探针 |

> **最佳实践**：Init 容器不要做长期运行的事（超过 1 分钟）。`activeDeadlineSeconds` 可以限制 Init 容器的总运行时间，超时则终止 Pod。

### 7 节点亲和性

| 方式 | 说明 | 硬/软约束 |
|------|------|----------|
| `nodeSelector` | 简单的标签匹配 | 硬约束（不满足则不调度） |
| `nodeAffinity` | 表达式匹配 | 支持硬/软两种 |
| `podAffinity` / `podAntiAffinity` | 基于其他 Pod 标签的调度 | 支持硬/软两种 |

**示例 1：nodeSelector（简单匹配）**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-job
spec:
  nodeSelector:
    accelerator: nvidia-tesla-v100    # 只调度到有 GPU 标签的节点
  containers:
    - name: cuda-app
      image: nvidia/cuda:12.0
```

**示例 2：nodeAffinity（表达式匹配 + 软硬约束）**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-affinity
spec:
  affinity:
    nodeAffinity:
      # 硬约束：必须满足，否则 Pod 一直 Pending
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: zone
                operator: In          # 必须在 zone-a 或 zone-b
                values:
                  - zone-a
                  - zone-b
              - key: disktype
                operator: NotIn       # 不能是 hdd 磁盘
                values:
                  - hdd
      # 软约束：尽量满足，不满足也能调度（权重 1~100）
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 80
          preference:
            matchExpressions:
              - key: node-type
                operator: In
                values:
                  - high-memory
  containers:
    - name: app
      image: myapp:latest
```

**示例 3：podAntiAffinity（Pod 反亲和——强制分散部署）**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-cluster
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app: web              # 与自己相同标签的 Pod
              topologyKey: kubernetes.io/hostname  # 按节点划分拓扑域
              # 效果：同一节点的 web Pod 数量 ≤ 1（每个节点最多一个）
      containers:
        - name: web
          image: nginx:1.25
```

> **topologyKey 决定调度范围**：`kubernetes.io/hostname` = 按节点分散；`topology.kubernetes.io/zone` = 按可用区分散（跨 AZ 高可用）。

---

## 第四章 Controller 控制器

### 1 什么是 Controller

控制器通过 label 关联 Pod，持续将集群当前状态驱动为期望状态。

**Deployment / ReplicaSet / Pod 三层关系**：

```
Deployment  ──创建并管理──▶  ReplicaSet  ──创建并管理──▶  Pod
(声明式更新策略)            (副本数量保证)               (实际运行容器)
```

- **Deployment** 负责滚动更新策略（`maxSurge` / `maxUnavailable`）。每次更新创建新的 ReplicaSet，逐步将 Pod 从旧 RS 迁移到新 RS
- **ReplicaSet** 只关心副本数量。旧 RS 的 Pod 缩容到 0 后保留（不删除），这是 `kubectl rollout undo` 能回滚的原因——旧 RS 仍存在

### 2 Deployment（最常用）

管理无状态应用的多个副本，支持滚动更新和回滚：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
        - name: nginx
          image: nginx:1.19
```

```shell
kubectl scale deployment nginx --replicas=5     # 扩缩容
kubectl rollout history deployment nginx        # 查看历史
kubectl rollout undo deployment nginx           # 回滚
```

### 3 StatefulSet（有状态应用）

为每个 Pod 维护**粘性 ID 和持久存储**，适合数据库等有状态服务。

**核心特性**：

| 特性 | 说明 |
|------|------|
| 稳定的网络标识 | Pod 名称固定 `<sts-name>-<ordinal>`，DNS 记录不变 |
| 稳定的持久存储 | 每个 Pod 独立 PVC，缩容不删除 PVC |
| 有序部署和缩容 | 从 0 到 N-1 顺序启动，从 N-1 到 0 逆序停止 |
| 有序滚动更新 | 从最大序号开始逆序更新 |

**Headless Service 原理**：StatefulSet 必须关联一个 Headless Service（`clusterIP: None`），DNS 为每个 Pod 生成独立的 A 记录（如 `mysql-0.mysql.default.svc.cluster.local`），客户端可直接连接特定 Pod。普通 Service 只解析为单个 ClusterIP，无法区分后端。

**podManagementPolicy** 控制启停顺序：

| 策略 | 行为 |
|------|------|
| `OrderedReady`（默认） | 严格按序号顺序：启动时 0→1→2，缩容时 2→1→0 |
| `Parallel` | 所有 Pod 并行启动/停止，适合无依赖场景 |

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mysql
spec:
  serviceName: mysql-headless
  replicas: 3
  podManagementPolicy: OrderedReady    # 有序 or Parallel
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0    # 0=全量更新；设为 2 则只更新序号 ≥2 的 Pod（金丝雀）
  selector:
    matchLabels:
      app: mysql
  template:
    ...
  volumeClaimTemplates:                # 每个 Pod 自动创建独立 PVC
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: cbs-ssd
        resources:
          requests:
            storage: 100Gi
```

### 4 DaemonSet（守护进程）

确保**每个（或符合条件的）节点上恰好运行一个 Pod 副本**。

**调度原理**：DaemonSet Controller 不为 Pod 设置 `nodeName`，而是为每个 Pod 自动注入：
- `nodeAffinity`：绑定到目标节点
- 容忍默认节点污点（`node.kubernetes.io/unschedulable` 等），保证即使节点被 cordon 也不被驱逐

**更新策略**：

| 策略 | 行为 |
|------|------|
| `RollingUpdate`（默认） | 逐个节点更新，先删旧 Pod 再创 建新 Pod |
| `OnDelete` | 手动删除旧 Pod 后才创建新 Pod |

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd-logger
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1       # 同一时间最多 1 个节点上的 Pod 不可用
  selector:
    matchLabels:
      app: fluentd
  template:
    ...
```

**典型用途**：每个节点运行日志收集（Fluentd/Filebeat）、监控代理（node-exporter）、网络插件（Calico/Cilium agent）。

### 5 Job

确保**指定数量的 Pod 成功完成并终止**，适用于批处理和一次性任务。

**关键参数**：

| 参数 | 说明 |
|------|------|
| `completions` | 需要成功完成的 Pod 总数 |
| `parallelism` | 并发运行的 Pod 数（默认 1） |
| `backoffLimit` | 失败重试次数上限（默认 6） |
| `activeDeadlineSeconds` | 任务总超时时间 |
| `ttlSecondsAfterFinished` | 完成后自动清理的时间 |
| `completionMode` | `NonIndexed`（默认）或 `Indexed`（每个 Pod 有唯一索引） |

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: data-migration
spec:
  completions: 10            # 成功完成 10 次
  parallelism: 3             # 最多 3 个 Pod 并发
  backoffLimit: 4
  ttlSecondsAfterFinished: 3600   # 1 小时后自动删除
  template:
    spec:
      restartPolicy: Never   # Job 必须用 Never 或 OnFailure
      containers:
        - name: worker
          image: migration-tool:v2
```

**Indexed Job**（`completionMode: Indexed`）：每个 Pod 获得 `JOB_COMPLETION_INDEX` 环境变量（0, 1, 2...），适合"分片处理"场景。例如 10 个 Pod 各处理数据分片 0~9。

### 6 CronJob

在**定时规则**下创建 Job：

| 参数 | 说明 |
|------|------|
| `schedule` | Cron 表达式（5 字段 `分 时 日 月 周`） |
| `concurrencyPolicy` | 并发策略 |
| `startingDeadlineSeconds` | 启动截止时间（超时跳过） |
| `successfulJobsHistoryLimit` | 保留的成功 Job 数（默认 3） |
| `failedJobsHistoryLimit` | 保留的失败 Job 数（默认 1） |

**concurrencyPolicy 三种策略**：

| 策略 | 行为 |
|------|------|
| `Allow`（默认） | 允许并发 Job |
| `Forbid` | 前一个未完成则跳过本次 |
| `Replace` | 前一个未完成则取消旧 Job 启 动新 Job |

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-backup
spec:
  schedule: "0 2 * * *"           # 每天凌晨 2 点
  concurrencyPolicy: Forbid       # 不允许并发
  startingDeadlineSeconds: 300    # 5 分钟内未启动则跳过
  successfulJobsHistoryLimit: 5
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: backup-tool
```

### 7 Controller Manager 内部架构

kube-controller-manager 是一个单一二进制文件，内部运行多个独立控制器，每个控制器有独立的 reconcile 循环：

```
kube-controller-manager 进程
├── Deployment Controller    ← watch Deployment 变化
├── ReplicaSet Controller    ← watch ReplicaSet 变化
├── StatefulSet Controller   ← watch StatefulSet 变化
├── DaemonSet Controller     ← watch DaemonSet 变化
├── Job Controller           ← watch Job 变化
├── Node Controller          ← watch Node 变化（心跳、状态）
├── EndpointSlice Controller ← watch Service → 生成 EndpointSlice
├── ServiceAccount Controller← 自动创建 SA + Token
└── Garbage Collector       ← 清理孤立资源
```

每个 Controller 只关注自己负责的资源，通过 Informer 机制监听 API Server，资源变化时触发 reconcile。

### 8 垃圾回收与 OwnerReference

Kubernetes 通过 **OwnerReference** 机制实现级联删除：

```
Deployment (owner)
  └── ReplicaSet (owner of Pod)
        └── Pod
```

当 Deployment 被删除时，GC Controller 检测到 ReplicaSet 的 owner 不存在，自动删除 ReplicaSet；同理递归删除 Pod。

```yaml
# 查看 Pod 的 owner 链路
$ kubectl get pod nginx-7d8f9c-abc12 -o jsonpath='{.metadata.ownerReferences}'
[{"apiVersion":"apps/v1","kind":"ReplicaSet","name":"nginx-7d8f9c","uid":"xxx"}]

# 阻止级联删除
$ kubectl delete deployment nginx --cascade=orphan   # Pod 保留
```

---

## 第五章 Service

### 1 什么是 Service

将一组 Pod 暴露为网络服务的抽象，通过 label selector 关联 Pod，提供**稳定的虚拟 IP 和 DNS 名称**。

### 2 Service 类型

| 类型 | 访问范围 | 用途 |
|------|----------|------|
| **ClusterIP** | 集群内部 | 内部服务发现（默认） |
| **NodePort** | NodeIP:30000-32767 | 开发测试 |
| **LoadBalancer** | 外部 IP | 生产公网入口 |
| **ExternalName** | DNS CNAME | 代理外部服务 |

### 3 Service 与 Pod 关系

```
Service selector → Pod labels → Pod IP:targetPort
Service IP 固定，Pod 重建后 IP 变化但 Service 不变
```

**Service 流量转发原理**：

```
请求 → ClusterIP (虚拟IP，不对应任何网卡)
            │
            ▼
      kube-proxy 维护的 iptables/IPVS 规则
            │
            ▼
      DNAT 到某个后端 Pod IP:targetPort（随机选择）
```

kube-proxy 通过 watch API Server 的 Service 和 Endpoints 变化来实时更新转发规则。当 Endpoints 为空时（没有健康 Pod），请求会直接失败。

**Endpoint 与 EndpointSlice**：K8s 1.21+ 默认使用 EndpointSlice 替代 Endpoints。原因：单个 Endpoints 对象有大小限制（约 1000 个后端），大规模集群会用 EndpointSlice 自动分片。

**sessionAffinity（会话保持）**：

| 值 | 行为 |
|----|------|
| `None`（默认） | 每次请求随机选择后端 Pod |
| `ClientIP` | 同一客户端 IP 的请求始终转发到同一个 Pod |

> `sessionAffinity` 在内核层（iptables/IPVS）实现，不需要应用层 cookie。配合 `sessionAffinityConfig.clientIP.timeoutSeconds` 设置超时。

**externalTrafficPolicy（外部流量策略）**：

| 值 | 行为 | source IP 可见？ |
|----|------|:---:|
| `Cluster`（默认） | 流量可在集群内任意节点转发 | ❌ SNAT 后丢失 |
| `Local` | 流量只转发到**接收请求的节点**上的 Pod | ✅ 保留真实 IP |

> `Local` 策略适合需要真实客户端 IP 的场景（如日志审计、IP 白名单），但负载可能不均衡——没有 Pod 的节点收到的请求会直接丢弃。

**无头服务（Headless Service）**：设置 `clusterIP: None` 后不分配 ClusterIP，DNS 直接返回所有后端 Pod IP（A 记录）。适用于 StatefulSet、自定义服务发现、客户端侧负载均衡。

### 4 内部通信示例

```yaml
# MySQL Service (ClusterIP)
apiVersion: v1
kind: Service
metadata:
  name: mysql
spec:
  selector:
    app: mysql
  ports:
    - port: 3306
      targetPort: 3306
  type: ClusterIP
```

应用容器内直接通过 `mysql` 服务名访问，DNS 自动解析为 `mysql.default.svc.cluster.local`。

**Service 调试验证命令**：

```shell
# 查看 Service 的 Endpoints（后端 Pod IP 列表）
$ kubectl get endpoints mysql
NAME    ENDPOINTS           AGE
mysql   10.0.1.5:3306       5m

# 追踪 Service → Pod 的链路
$ kubectl get svc mysql -o wide
NAME    TYPE        CLUSTER-IP     PORT(S)    SELECTOR
mysql   ClusterIP   10.96.100.1    3306/TCP   app=mysql

$ kubectl get pods -l app=mysql -o wide
NAME          READY   IP         NODE
mysql-abc12   1/1     10.0.1.5   node-1

# 测试内部 DNS 解析（在任意 Pod 内执行）
$ kubectl run -it --rm debug --image=busybox -- sh
/ # nslookup mysql.default.svc.cluster.local
Server:    10.96.0.10
Address 1: 10.96.0.10 kube-dns.kube-system.svc.cluster.local
Name:      mysql.default.svc.cluster.local
Address 1: 10.96.100.1    # 返回 ClusterIP（非 Headless 时）

# 修改 externalTrafficPolicy（保留客户端 IP）
$ kubectl patch svc myapp -p '{"spec":{"externalTrafficPolicy":"Local"}}'

# 实时监听 Service 事件
$ kubectl describe svc mysql
Events:
  Type    Reason   Message
  Normal  Type     ClusterIP
```

---

## 第六章 存储

### 1 Volume

解决容器文件临时性和多容器共享问题。常用类型：

| 类型 | 持久性 | 用途 |
|------|--------|------|
| **emptyDir** | Pod 生命周期 | 临时共享 |
| **hostPath** | 节点生命周期 | 与节点绑定 |
| **nfs** | 独立于集群 | 网络共享存储 |
| **configMap/secret** | 独立 | 配置文件注入 |

**示例 1：emptyDir（Pod 内容器间共享临时数据）**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: shared-tmp
spec:
  containers:
    - name: writer
      image: busybox
      command: ["sh", "-c", "echo 'hello' > /data/msg.txt && sleep 3600"]
      volumeMounts:
        - name: shared-data
          mountPath: /data        # writer 写入 /data/msg.txt
    - name: reader
      image: busybox
      command: ["sh", "-c", "cat /data/msg.txt && sleep 3600"]
      volumeMounts:
        - name: shared-data
          mountPath: /data        # reader 读取同一个文件
  volumes:
    - name: shared-data
      emptyDir: {}                # Pod 删除时数据丢失
```

**示例 2：hostPath（访问宿主机文件）**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: log-collector
spec:
  containers:
    - name: filebeat
      image: elastic/filebeat:7.17
      volumeMounts:
        - name: docker-logs
          mountPath: /var/log/containers
          readOnly: true
  volumes:
    - name: docker-logs
      hostPath:
        path: /var/log/containers   # 直接挂载宿主机目录
        type: Directory             # 目录必须存在
```

> **安全警告**：hostPath 把容器绑定到特定节点（重启后可能换节点），且能访问宿主机文件，生产环境慎用。

### 2 PV & PVC（核心概念）

- **PV (PersistentVolume)**：管理员预置的存储资源（如 NFS 目录、云盘）。集群级资源，与 Pod 生命周期无关
- **PVC (PersistentVolumeClaim)**：用户对存储的申请（容量 + 访问模式）。命名空间级资源
- **StorageClass**：动态供给，无需预创建 PV，PVC 提交后自动创建 PV

**PV 与 PVC 的供需绑定机制**：

```
管理员                  Kubernetes              用户（开发者）
───────                 ──────────              ────────────
创建 PV                 自动匹配               创建 PVC
(size=50Gi, RWO)    ──▶  ① 容量 ≥ 请求?       (size=30Gi, RWO)
                      ──▶  ② 访问模式匹配?
                      ──▶  ③ StorageClass 相同?
                      ──▶  ④ 标签选择器匹配?（可选）
                           │
                    全部满足 → 绑定（Bound）
                    不满足   → PVC 保持 Pending
```

**一对一绑定**：一个 PV 只能绑定一个 PVC，绑定后即**独占**。即使 PVC 只用 30Gi，50Gi 的 PV 也无法再被其他 PVC 使用（剩余 20Gi 浪费）。

**静态 PV 完整示例（管理员创建 PV + 开发者创建 PVC）**：

```yaml
# ===== 管理员创建 =====
apiVersion: v1
kind: PersistentVolume
metadata:
  name: mysql-pv
spec:
  capacity:
    storage: 100Gi          # 集群中的存储容量
  accessModes:
    - ReadWriteOnce         # 单节点读写
  persistentVolumeReclaimPolicy: Retain  # PVC 删除后保留数据
  storageClassName: cbs-ssd
  # 后端存储：以下任选一种
  nfs:                      # 方式 A：NFS
    server: 10.0.1.100
    path: /data/mysql
  # hostPath:               # 方式 B：本地测试（生产勿用）
  #   path: /mnt/data
  # csi:                    # 方式 C：云盘（通过 CSI 驱动）
  #   driver: ebs.csi.aws.com
  #   volumeHandle: vol-xxxxx

---
# ===== 开发者创建 =====
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: cbs-ssd     # 必须与 PV 一致

---
# ===== Pod 使用 PVC =====
apiVersion: v1
kind: Pod
metadata:
  name: mysql
spec:
  containers:
    - name: mysql
      image: mysql:8.0
      volumeMounts:
        - name: mysql-storage
          mountPath: /var/lib/mysql
  volumes:
    - name: mysql-storage
      persistentVolumeClaim:
        claimName: mysql-data
```

**验证 PV/PVC 绑定状态**：

```shell
$ kubectl get pv
NAME       CAPACITY   STATUS      CLAIM              STORAGECLASS   AGE
mysql-pv   100Gi      Bound       default/mysql-data cbs-ssd         5m

$ kubectl get pvc
NAME         STATUS   VOLUME     CAPACITY   STORAGECLASS   AGE
mysql-data   Bound    mysql-pv   100Gi      cbs-ssd         3m

# 排查：PVC 为什么一直 Pending？
$ kubectl describe pvc mysql-data
# Events 中会提示原因：找不到匹配的 PV / StorageClass 不匹配 / 容量不足
```

**PVC 使用流程**（仅 PVC+YAML，适用于已有 PV 或 StorageClass 动态供给的场景）：
```yaml
# 用户创建 PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-data
spec:
  accessModes:
    - ReadWriteOnce         # 单节点读写
  resources:
    requests:
      storage: 100Gi        # 需求容量
  storageClassName: cbs-ssd # 与 PV 的 StorageClass 一致才绑定

# Pod 引用 PVC（对 PV 无感知）
volumes:
  - name: mysql-storage
    persistentVolumeClaim:
      claimName: mysql-data   # 只管 PVC 名称
```

```
┌───────┐    绑定     ┌───────┐    挂载     ┌─────────┐
│  PV   │◄──────────▶│  PVC  │──────────▶│   Pod    │
│(集群级)│  1:1 独占   │(ns 级)│  引用 PVC   │(ns 级)   │
└───────┘            └───────┘            └─────────┘
  管理员创建            开发者创建             开发者使用
```

**PV 生命周期**：

| 阶段 | 说明 |
|------|------|
| `Available` | 已创建，未被任何 PVC 绑定 |
| `Bound` | 已绑定到某个 PVC |
| `Released` | PVC 已删除，但 PV 尚未回收 |
| `Failed` | 回收失败 |

**回收策略（ReclaimPolicy）**：

| 策略 | PVC 删除后的行为 |
|------|-----------------|
| `Retain` | 保留 PV 和数据，需管理员手动清理（生产推荐） |
| `Delete` | 自动删除 PV 和后端存储（适合测试环境） |
| `Recycle` | 删除 PV 中的数据后重新可用（已弃用） |

**volumeBindingMode 原理**：

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `Immediate` | PVC 创建即绑定 PV（默认） | 不考虑调度位置 |
| `WaitForFirstConsumer` | **Pod 调度后才创建和绑定** | 云盘需与 Pod 在同一 AZ |

> `WaitForFirstConsumer` 是生产必备：Pod 在 AZ-A → PV 也在 AZ-A 创建，避免跨 AZ 挂载云盘的高延迟。

**CSI 驱动原理**：CSI（Container Storage Interface）是标准化接口，将存储供应商插件与 K8s 核心解耦。分为三部分：CSI Controller（创建/删除/快照卷）+ CSI Node Plugin（挂载/卸载卷到节点）+ external-provisioner / external-attacher 等 sidecar 容器。

### 3 访问模式

| 模式 | 含义 |
|------|------|
| `ReadWriteOnce` | 单节点读写 |
| `ReadOnlyMany` | 多节点只读 |
| `ReadWriteMany` | 多节点读写 |

---

## 第七章 ConfigMap & Secret

### 1 ConfigMap

存储非敏感配置数据，与镜像解耦：

```shell
kubectl create configmap app-config --from-literal=DB_HOST=mysql
kubectl create configmap app-config --from-file=config.yaml
```

**使用方式**：环境变量注入、Volume 文件挂载、命令行参数。

**ConfigMap 挂载更新原理**：ConfigMap 通过 Volume 挂载时，kubelet 使用符号链接实现原子更新。实际挂载路径是 `..data` 目录的符号链接，每次更新 ConfigMap 时 kubelet 创建新的 `..data_<timestamp>` 目录并原子替换 symlink。**注意**：如果应用通过 subPath 挂载单个文件而非整个目录，更新不会生效——subPath 方式不享受 symlink 更新机制。

```yaml
# ❌ 使用 subPath 挂载单个文件 → ConfigMap 更新不生效
volumeMounts:
  - name: config
    mountPath: /etc/app/config.yaml
    subPath: config.yaml        # 不走 symlink 更新

# ✅ 挂载整个目录 → ConfigMap 更新自动生效
volumeMounts:
  - name: config
    mountPath: /etc/app/config  # kubelet 原子替换 symlink
```

**immutable ConfigMap/Secret**（K8s 1.21+）：设置 `immutable: true` 后禁止修改，提升安全性和 kubelet 性能（减少对 immutable 资源的 watch）。

### 1.1 ConfigMap 更新机制详解

ConfigMap 被 Pod 引用后，更新行为取决于**注入方式**和**应用是否支持热加载**：

#### 方式一：Volume 文件挂载（支持自动更新）

**更新流程**：

```
kubectl apply ConfigMap
  → apiserver 写入 etcd
  → kubelet watch 到变更（默认 sync period 60s）
  → kubelet 原子写入新文件到 Pod 的 Volume 目录
  → 应用读取新文件（何时生效取决于应用是否 reload）
```

**关键参数**：

| 参数 | 说明 |
|------|------|
| `kubelet --sync-frequency` | kubelet 同步周期，默认 1 分钟 |
| ConfigMap TTL cache | kubelet 内部缓存，默认 1 分钟 |

> 从 `kubectl apply` 到 Pod 内文件更新，**最长约 90 秒**（60s sync + 30s cache TTL）。

**原子写入原理**（kubelet atomic_writer）：

```shell
# Pod 内挂载点实际结构
/etc/app/config/
  ├── ..data -> ..2024_01_15_10_30_45.123456789  # 符号链接
  ├── ..2024_01_15_10_30_45.123456789/
  │   ├── app.properties
  │   └── db.yaml
  ├── app.properties -> ..data/app.properties
  └── db.yaml -> ..data/db.yaml
```

每次 ConfigMap 更新时，kubelet：
1. 创建新的 `..data_<timestamp>` 目录，写入所有文件
2. 原子替换 `..data` symlink → 新目录
3. 应用通过 `app.properties`（→ `..data/...`）透明读取新内容

```yaml
# ✅ Volume 目录挂载 → 文件自动更新
volumeMounts:
  - name: config
    mountPath: /etc/app/config   # 挂载整个目录
```

#### 方式二：subPath 挂载（❌ 不支持自动更新）

```yaml
# ❌ subPath → ConfigMap 更新后文件不会变化
volumeMounts:
  - name: config
    mountPath: /etc/app/config.yaml
    subPath: config.yaml   # 直接挂载文件，不经过 symlink
```

subPath 绕过了 `..data` symlink 机制，kubelet 不会更新该文件。**唯一生效方式**：删除并重建 Pod。

#### 方式三：环境变量注入（❌ 不支持更新）

```yaml
# ❌ env 注入 → ConfigMap 更新后环境变量不变
envFrom:
  - configMapRef:
      name: app-config
```

环境变量在容器启动时一次性注入，后续 ConfigMap 变更**对运行中的容器完全无效**。必须重启 Pod 才能生效。

#### 如何触发 Pod 重启以应用新配置

**方案 1：手动 Rolling Restart**
```shell
kubectl rollout restart deployment/my-app
```

**方案 2：ConfigMap 版本注解（推荐）**

在 Deployment 中注入 ConfigMap 的 checksum 作为 annotation，每次 ConfigMap 变化后自动触发滚动更新：

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    metadata:
      annotations:
        configmap-checksum: "{{ include (print $.Template.BasePath \"/configmap.yaml\") . | sha256sum }}"
```

使用 Helm 或 Kustomize 的 `configMapGenerator` 会自动生成带 hash 的 ConfigMap 名称（如 `app-config-7b5c9f`），Deployment 引用新名称即触发滚动更新。

**方案 3：Reloader（Stakater Reloader）**

```shell
kubectl apply -f https://raw.githubusercontent.com/stakater/Reloader/master/deployments/kubernetes/reloader.yaml
```

```yaml
# Deployment 打上 annotation 即可
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

Reloader 会 watch ConfigMap 变化并自动执行 `rollout restart`。

**方案 4：Sidecar 热更新（应用无需重启）**

```yaml
# Sidecar 监听 ConfigMap 文件变化，通知主容器 reload 配置
containers:
  - name: app
    image: my-app
    volumeMounts:
      - name: config
        mountPath: /etc/app/config
  - name: config-reloader
    image: alpine
    command: ["sh", "-c"]
    args:
      - |
        apk add inotify-tools
        while inotifywait -e modify /etc/app/config/; do
          kill -HUP $(pgrep my-app)   # 发送 SIGHUP 信号
        done
    volumeMounts:
      - name: config
        mountPath: /etc/app/config
```

#### ConfigMap 大小限制

| 限制项 | 值 |
|--------|-----|
| 单个 ConfigMap 最大大小 | **~1 MiB**（etcd 单 key 限制） |
| 单个 key 最大大小 | ~1 MiB |
| 超大配置建议 | 拆分为多个 ConfigMap，或使用 Volume 挂载外部存储 |

#### 总结对比

| 注入方式 | 支持热更新 | Pod 内文件更新 | 生效条件 |
|----------|-----------|---------------|---------|
| Volume 目录挂载 | ✅ 支持 | 最长 ~90s | 应用自行 reload |
| Volume + subPath | ❌ 不支持 | 不更新 | 重建 Pod |
| 环境变量 | ❌ 不支持 | 不更新 | 重启 Pod |
| envFrom | ❌ 不支持 | 不更新 | 重启 Pod |

### 2 Secret

存储敏感信息（密码/密钥/证书），base64 编码（不是加密！）：

```shell
kubectl create secret generic db-secret \
    --from-literal=password=MyPass123
```

**Secret 类型**：

| 类型 | 用途 | 字段格式 |
|------|------|----------|
| `Opaque`（默认） | 任意键值对 | 任意 key/value |
| `kubernetes.io/tls` | TLS 证书 | `tls.crt` + `tls.key` |
| `kubernetes.io/dockerconfigjson` | 镜像仓库凭据 | `.dockerconfigjson` |
| `kubernetes.io/service-account-token` | ServiceAccount Token | `token` + `ca.crt` + `namespace` |

```yaml
# TLS Secret 示例
apiVersion: v1
kind: Secret
metadata:
  name: my-tls
type: kubernetes.io/tls
data:
  tls.crt: LS0tLS1CRUdJTi...  # base64(cert.pem)
  tls.key: LS0tLS1CRUdJTi...  # base64(key.pem)
```

**base64 不是加密**：`echo -n "MyPass123" | base64` → `TXlQYXNzMTIz`，任何人拿到此值可秒解。生产环境必须配合 etcd 静态加密（`EncryptionConfiguration`）或 External Secrets Operator。

使用方式与 ConfigMap 完全相同。
> 生产环境应使用 External Secrets Operator 或云凭据管理服务（见第二十五章）。

---

## 第八章 Ingress

### 1 什么是 Ingress

将集群外部 HTTP/HTTPS 流量路由到集群内 Service 的资源，提供**域名路由、TLS 终止、路径重写**。

**pathType 行为差异**：

| 类型 | 匹配规则 | 示例 `/foo` |
|------|----------|------------|
| `Prefix` | 路径前缀匹配 | 匹配 `/foo`, `/foo/`, `/foo/bar` |
| `Exact` | 精确匹配 | 只匹配 `/foo` |
| `ImplementationSpecific` | 由 Ingress Controller 决定 | Nginx 等同 Prefix |

> 注意：`Prefix` 类型的行为在 K8s 1.18 前后不同——旧版本更宽松，新版本要求正则匹配。为可移植性，建议用 `Prefix` 并确保有分隔符。

### 2 架构

**简化链路**（仅看数据流向）：

```
外部请求 → Ingress Controller (Nginx/Traefik) → Service → Pod
```

**完整链路**（含 kube-proxy / Endpoints / CNI）：

```
外部请求
  │  DNS 解析（ExternalName / 云 LB 域名）
  ▼
LoadBalancer / NodePort（云厂商 CLB 或节点端口）
  │  转发到 Ingress Controller Pod
  ▼
Ingress Controller (Nginx / Traefik)
  │  按 Host + Path 匹配 Ingress 规则
  │  查询 Service 对应的 Endpoints/EndpointSlice，拿到 Pod IP 列表
  │  ⚠ 注意：Ingress Controller 通常直接负载均衡到 Pod IP，不再经过 Service ClusterIP
  ▼
Service (ClusterIP 虚拟 IP)
  │  ClusterIP 本身不可路由，是一个虚拟 VIP
  │  由 kube-proxy 在每个节点维护的 iptables / IPVS 规则做 DNAT
  ▼
kube-proxy（每个节点运行的守护进程）
  │  监听 Endpoints/EndpointSlice 变化，实时刷新转发规则
  │  iptables 模式：随机选 Pod，全链路转发
  │  ipvs 模式：支持 rr / lc / wrr 等多种调度算法，性能更优
  ▼
Pod（CNI 分配的 Pod IP）
  │  跨节点流量由 CNI（Calico / Flannel / Cilium）处理
  │  同节点流量走 docker0 / cni0 网桥直连
  ▼
Container（业务进程监听端口）
```

**关键组件职责**：

| 组件 | 在链路中的作用 |
|------|---------------|
| **Ingress Controller** | L7 路由，按 Host/Path 分流；通过 Endpoints 直接转发到 Pod IP |
| **Service (ClusterIP)** | 提供稳定的虚拟 IP + DNS 名，本身不转发流量 |
| **kube-proxy** | 把 ClusterIP:Port 通过 iptables/IPVS 规则 DNAT 到真实 Pod IP:Port |
| **Endpoints / EndpointSlice** | 记录 Service 背后健康的 Pod IP 列表，kube-proxy 和 Ingress Controller 都依赖它 |
| **CNI** | 负责跨节点 Pod 间网络连通（IPIP / VXLAN / eBPF） |
| **kubelet** | 不在数据链路上，但负责上报 Pod 状态，间接影响 Endpoints |

> 💡 **常见误区**：很多人以为流量是 `Service → Pod` 一步到位，实际上 Service 只是一个"逻辑抽象"，真正的转发由 **kube-proxy 维护的内核态规则**完成；而 Ingress Controller 为了性能，往往会**绕过 ClusterIP**，直接从 EndpointSlice 取 Pod IP 做 L7 负载均衡。

### 3 Ingress 示例

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 8080
```

### 4 Ingress Controller

| Controller | 特点 |
|------------|------|
| **Nginx** | 官方，使用最广 |
| **Traefik** | 自动发现，支持 CRD |
| **Istio** | 服务网格级 Ingress |

**IngressClass 与多 Controller 共存**：当集群中部署了多个 Ingress Controller 时，Ingress 通过 `ingressClassName` 指定由哪个 Controller 处理。

```yaml
# IngressClass 资源定义
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx
spec:
  controller: k8s.io/ingress-nginx
---
# 设置默认 IngressClass（没有显式指定 className 时使用）
metadata:
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
```

```yaml
# Ingress 指定由 nginx controller 处理
spec:
  ingressClassName: nginx    # 匹配 IngressClass.metadata.name
```

> K8s 1.18+ 必须使用 `ingressClassName` 字段，旧的 `kubernetes.io/ingress.class` 注解已弃用。

---

## 第九章 命名空间

### 1 作用

在集群内逻辑隔离资源，实现多团队或多环境共享集群：

```shell
kubectl create namespace team-a
kubectl apply -f app.yaml -n team-a
```

### 2 跨命名空间 vs 命名空间内

| 跨命名空间资源（集群级） | 命名空间内资源 |
|------------------------|---------------|
| Node, Namespace, ClusterRole, ClusterRoleBinding, PV, StorageClass, IngressClass | Pod, Deployment, Service, ConfigMap, Secret, PVC, Role, RoleBinding, SA, Ingress |

> **重要**：`PersistentVolume` 是集群级的，但 `PersistentVolumeClaim` 是命名空间级的。这意味着 PVC 只能绑定到同命名空间的 Pod。

### 3 Service DNS 跨命名空间访问

```shell
# 同命名空间：直接用短名
mysql

# 跨命名空间：全限定域名
mysql.team-a.svc.cluster.local
#  ─┬──  ──┬──  ─┬─  ──────┬─────
#   │      │     │          └── 集群域名（默认 cluster.local）
#   │      │     └── svc（固定）
#   │      └── 命名空间
#   └── Service 名称
```

### 4 命名空间生命周期与删除陷阱

删除命名空间是一个**异步操作**，kube-apiserver 先设置 `deletionTimestamp`，然后后台逐资源清理。常见问题：

```shell
# 命名空间卡在 Terminating 状态
$ kubectl get ns team-a
NAME     STATUS        AGE
team-a   Terminating   10m     # ← 卡住了

# 原因通常是：命名空间内存在无法清理的资源（finalizer 阻止）
$ kubectl get ns team-a -o jsonpath='{.spec.finalizers}'
["kubernetes"]
```

**解决**：找出卡住的资源 → 移除 finalizer → 强制删除：

```shell
# 1. 列出 namespace 中所有资源
$ kubectl api-resources --verbs=list --namespaced -o name | \
    xargs -n1 kubectl get -n team-a --show-kind --ignore-not-found

# 2. 移除特定资源的 finalizers
$ kubectl patch <resource> -n team-a -p '{"metadata":{"finalizers":[]}}' --type=merge

# 3. 最后手段：直接移除 namespace 的 finalizer
$ kubectl get ns team-a -o json | jq '.spec.finalizers = []' | kubectl replace --raw "/api/v1/namespaces/team-a/finalize" -f -
```

### 5 切换命名空间

```shell
kubens kube-system    # 切换（需安装 kubens 工具）
kubectl config set-context --current --namespace=team-a  # 原生方式
```

---

## 第十章 Helm

### 1 简介

Kubernetes 的包管理工具，通过 Chart 打包、分发和管理应用。

**Helm 与 kubectl apply 的本质区别**：kubectl 直接操作 K8s 资源，Helm 通过模板引擎将同一套模板 + 不同 values 渲染为对应的 YAML，再 apply。这意味着同一套模板可部署到 dev/staging/prod 三个环境，只需切换 values 文件。

### 2 核心概念

| 概念 | 说明 |
|------|------|
| **Chart** | 包含 K8s 资源定义的包 |
| **Repository** | Chart 仓库 |
| **Release** | Chart 在集群中的实例 |
| **Revision** | Release 的变更版本（每次 install/upgrade/rollback 增加） |

**Helm 模板渲染内部流程**：

```
values.yaml  ─┐
              ├──▶ 模板引擎（Go template）──▶ 渲染后的 YAML ──▶ kubectl apply
templates/*  ─┘
              ▲
--set key=val 也可以在命令行覆盖 values
```

**值优先级（从低到高）**：
1. Chart 默认 `values.yaml`
2. 父 Chart 的 values（对子 Chart）
3. 用户 `-f custom-values.yaml`
4. `--set` 命令行参数（最高）

### 3 使用

```shell
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install my-nginx bitnami/nginx
helm list
helm upgrade my-nginx bitnami/nginx
helm rollback my-nginx
helm uninstall my-nginx
```

### 4 自定义 Chart

```shell
helm create myapp              # 生成脚手架
# 目录结构: Chart.yaml / values.yaml / templates/
helm lint myapp                # 验证
helm package myapp             # 打包
helm install myapp ./myapp-0.1.0.tgz
```

Template 语法：`{{ .Values.image }}` 引用 values.yaml 中的变量。

---

## 第十一章 RBAC 权限控制

- 什么是 RBAC
- 核心概念：ServiceAccount / Role / ClusterRole / RoleBinding / ClusterRoleBinding
- 生产场景：多租户权限隔离
- 最佳实践

### 1 什么是 RBAC

RBAC（Role-Based Access Control，基于角色的访问控制）是 Kubernetes 1.8+ 的默认授权模式。
通过定义 **谁** 在 **哪个范围** 对 **什么资源** 能执行 **哪些操作**，来实现精细化的权限管理。

### 2 核心概念

#### 2.1 ServiceAccount（服务账号）

Pod 内部与 API Server 交互时使用的身份。每个命名空间都有一个默认的 `default` ServiceAccount。

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-sa
  namespace: app-ns
```

在 Pod 中使用：

```yaml
spec:
  serviceAccountName: my-sa      # Pod 使用指定 SA，而非命名空间的 default
  automountServiceAccountToken: false  # 若不需要访问 API Server，关闭以提升安全
```

> **注意**：Kubernetes 1.24+ 默认不再自动挂载 SA token 到每个 Pod，需显式声明或使用 `automountServiceAccountToken`。

#### 2.2 Role（角色）& ClusterRole（集群角色）

| 类型 | 作用域 | 使用场景 |
|------|--------|----------|
| **Role** | 单个命名空间 | 给开发者在特定 ns 中操作 Pod/Deployment |
| **ClusterRole** | 整个集群 | 访问 Node、PV、Namespace 等集群级资源 |

```yaml
# 命名空间级别 Role
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: app-ns
  name: pod-reader
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
```

```yaml
# 集群级别 ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: node-reader
rules:
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["nodes/metrics"]
    verbs: ["get"]
```

#### 2.3 RoleBinding & ClusterRoleBinding

将 Role/ClusterRole 绑定到 ServiceAccount、User 或 Group 上。

```yaml
# RoleBinding：把 Role 绑定到 SA（命名空间级）
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: app-ns
subjects:
  - kind: ServiceAccount
    name: my-sa
    namespace: app-ns
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

```yaml
# ClusterRoleBinding：把 ClusterRole 绑定到 SA（集群级）
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: read-nodes
subjects:
  - kind: ServiceAccount
    name: my-sa
    namespace: app-ns
roleRef:
  kind: ClusterRole
  name: node-reader
  apiGroup: rbac.authorization.k8s.io
```

> **重要**：`ClusterRoleBinding` 绑定后，SA 对该 ClusterRole 中所有资源的访问覆盖全集群。
> 若只想用 ClusterRole 但限制到特定命名空间，应使用 `RoleBinding` + `ClusterRole`。

#### 2.4 常见 verbs

| Verb | 说明 |
|------|------|
| `get` | 获取单个资源 |
| `list` | 列出资源列表 |
| `watch` | 监听资源变化 |
| `create` | 创建资源 |
| `update` | 更新资源 |
| `patch` | 部分修改资源 |
| `delete` | 删除资源 |
| `deletecollection` | 批量删除 |

### 3 生产场景：多团队权限隔离

**需求**：开发团队 A 只能在 `team-a` 命名空间内操作，且不能查看 Secret。

```yaml
---
# 为团队 A 创建命名空间
apiVersion: v1
kind: Namespace
metadata:
  name: team-a
---
# 创建 ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: team-a-dev
  namespace: team-a
---
# 创建 Role（排除 Secret 的读写）
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: team-a
  name: team-a-developer
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
# 绑定
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-a-dev-binding
  namespace: team-a
subjects:
  - kind: ServiceAccount
    name: team-a-dev
    namespace: team-a
roleRef:
  kind: Role
  name: team-a-developer
  apiGroup: rbac.authorization.k8s.io
```

### 4 快速查看命令

```shell
# 查看某个 SA 的权限
$ kubectl auth can-i get pods --as=system:serviceaccount:team-a:team-a-dev -n team-a

# 查看谁能对某资源执行操作
$ kubectl get rolebindings,clusterrolebindings --all-namespaces -o wide

# 查看当前用户权限
$ kubectl auth can-i --list
```

---

## 第十二章 HPA 自动扩缩容

- HPA 原理
- 基于 CPU / 内存的 HPA
- 基于自定义指标的 HPA
- 生产场景配置

### 1 什么是 HPA

Horizontal Pod Autoscaler（HPA）根据观测到的 CPU 使用率、内存使用率或自定义指标，
自动调整 Deployment、StatefulSet 或 ReplicaSet 的副本数量。

> **前置条件**：集群必须部署 **metrics-server**（已在 K8s.md 第六章安装）。

### 2 工作原理

HPA 控制器每 15 秒（可通过 `--horizontal-pod-autoscaler-sync-period` 调整）
查询 metrics-server，计算目标副本数：

```
期望副本数 = ceil(当前副本数 × (当前指标值 / 目标指标值))
```

### 3 基于 CPU 的 HPA

**Step 1**：确保 Deployment 设置了 CPU requests（HPA 依赖 requests 计算使用率）：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-hpa
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-hpa
  template:
    metadata:
      labels:
        app: nginx-hpa
    spec:
      containers:
        - name: nginx
          image: nginx:1.23
          resources:
            requests:
              cpu: "200m"          # 必须设置
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
```

**Step 2**：创建 HPA 对象：

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nginx-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nginx-hpa
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60  # 目标 CPU 使用率 60%
```

**Step 3**：验证：

```shell
$ kubectl get hpa
NAME        REFERENCE              TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
nginx-hpa   Deployment/nginx-hpa   10%/60%   2         10        2          30s

# 查看详细
$ kubectl describe hpa nginx-hpa
```

### 4 基于内存的 HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nginx-hpa-mem
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nginx-hpa
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80   # 内存目标 80%
```

> **注意**：内存型 HPA 伸缩不及时，因为内存不会像 CPU 那样自然回落。生产环境谨慎使用。

#### 2.1 扩容冷却原理

HPA 内部维护一个**稳定窗口（stabilization window）**机制来防止抖动：

- **扩容计算公式**：`目标副本 = ceil(当前副本 × (当前使用率 / 目标使用率))`
- **缩容冷却**：默认 5 分钟。HPA 会回看过去 5 分钟内**推荐的最大副本数**作为缩容目标，避免因短暂负载下降而错误缩容。

**示例**：假设 Pod 数为 10，CPU 突然从 80% 降到 10%：
```
t=0:  公式建议缩容到 2  → HPA 记住最大值 2
t=1m: 公式建议缩容到 1  → HPA 记住最大值 2（仍保留）
t=5m: 稳定窗口中始终为 2  → HPA 执行缩容到 2
```

这就是为什么缩容看起来"慢"——HPA 在确认负载稳定后才执行。

#### 2.2 基于自定义指标的 HPA（Prometheus）

CPU/内存只反映资源压力，**业务指标**（如在线人数、QPS、消息积压）才是真正的扩缩依据：

```yaml
# 前提：已部署 Prometheus Adapter 或 kube-metrics-adapter
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: combat-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: combat
  minReplicas: 3
  maxReplicas: 50
  metrics:
    # 资源指标（保底）
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    # 自定义业务指标（核心驱动）
    - type: Pods
      pods:
        metric:
          name: game_online_players_per_pod   # Prometheus 指标名
        target:
          type: AverageValue
          averageValue: "200"                  # 每 Pod 平均 200 人在线时扩容
    # 外部指标
    - type: External
      external:
        metric:
          name: kafka_consumer_lag
          selector:
            matchLabels:
              topic: game-events
        target:
          type: AverageValue
          averageValue: "1000"
```

> **关键区别**：Resource 类型使用 `Utilization`（使用率%），Pods/External 类型使用 `AverageValue`（绝对值）。

### 5 HPA 回缩稳定窗口

```yaml
spec:
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300   # 缩容前等待 5 分钟
      policies:
        - type: Percent
          value: 50                     # 每次最多缩 50% 的 Pod
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0     # 扩容立即生效
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 60
      selectPolicy: Max                 # 取最大值
```

### 6 生产建议

| 建议 | 说明 |
|------|------|
| `minReplicas >= 2` | 避免单点故障 |
| `maxReplicas` 合理 | 防止打爆集群 |
| 设置缩容稳定窗口 | 防止抖动（至少 300s） |
| requests ≈ 典型负载 | 否则利用率计算不准确 |
| 配合 PDB 使用 | 保证缩容不中断服务 |
| 预扩容 | 流量高峰前用 CronJob 提前扩容 |

---

## 第十三章 ResourceQuota & LimitRange

- ResourceQuota：命名空间资源配额
- LimitRange：容器资源范围约束
- Pod QoS 等级
- 生产实践

### 1 ResourceQuota（资源配额）

限制一个命名空间可消耗的资源总量，防止某个团队占满集群资源。

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-a-quota
  namespace: team-a
spec:
  hard:
    # 计算资源
    requests.cpu: "10"
    requests.memory: "20Gi"
    limits.cpu: "20"
    limits.memory: "40Gi"
    # 对象数量
    pods: "20"
    services: "10"
    services.nodeports: "2"
    secrets: "20"
    configmaps: "20"
    persistentvolumeclaims: "10"
    # 存储
    requests.storage: "100Gi"
    # 扩展资源（GPU 等）
    requests.nvidia.com/gpu: "2"
```

验证：

```shell
$ kubectl describe resourcequota team-a-quota -n team-a
```

### 2 LimitRange（资源范围约束）

对命名空间内的单个 Pod 或容器设置默认/最小/最大资源约束。

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: team-a-limits
  namespace: team-a
spec:
  limits:
    # 容器级别
    - type: Container
      default:
        cpu: "500m"                # 不声明 limits 时的默认值
        memory: "512Mi"
      defaultRequest:
        cpu: "200m"                # 不声明 requests 时的默认值
        memory: "128Mi"
      max:
        cpu: "4"
        memory: "8Gi"
      min:
        cpu: "50m"
        memory: "64Mi"
      maxLimitRequestRatio:
        cpu: "4"                   # limits/requests 最大 4 倍
        memory: "2"
    # Pod 级别
    - type: Pod
      max:
        cpu: "8"
        memory: "16Gi"
```

### 3 Pod QoS 等级

Kubernetes 根据 Pod 中容器的 requests/limits 自动划分 QoS 等级：

| 等级 | 条件 | 驱逐优先级 |
|------|------|------------|
| **Guaranteed** | 每个容器的 CPU/Memory 的 `requests == limits`（且均设置） | 最低（最后被驱逐） |
| **Burstable** | 至少有一个容器设置了 requests，但不满足 Guaranteed 条件 | 中等 |
| **BestEffort** | 没有任何容器设置 requests 或 limits | 最高（最先被驱逐） |

> **生产关键**：核心服务务必设置为 **Guaranteed** 级别，避免节点资源紧张时被 OOM Killer 杀死。

#### 3.1 OOM Killer 与 QoS 的定量关系

当节点内存不足时，kubelet 按以下 **OOM Score** 机制驱逐 Pod：

| QoS 等级 | OOM Score | 算法 |
|----------|-----------|------|
| **Guaranteed** | -998 | 固定最低分（几乎不会被 OOM Kill） |
| **Burstable** | 2 ~ 999 | `min(max(2, 1000 - 请求内存/节点容量 × 1000), 999)` |
| **BestEffort** | 1000 | 固定最高分（第一个被杀死） |

**举例**：节点 16Gi，Burstable Pod A 请求 1Gi，Pod B 请求 4Gi：
- Pod A OOM Score ≈ `1000 - (1/16 × 1000)` ≈ **937**
- Pod B OOM Score ≈ `1000 - (4/16 × 1000)` ≈ **750**
- Pod B 更"安全"——requests 声明越大，越不容易被杀死。

```yaml
# Guaranteed 示例
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "500m"          # 与 requests 完全相同
    memory: "512Mi"
```

查看 Pod QoS：

```shell
$ kubectl get pod nginx-guaranteed -o jsonpath='{.status.qosClass}'
Guaranteed
```

---

## 第十四章 NetworkPolicy 网络策略

- 什么是 NetworkPolicy
- 入站/出站规则
- 命名空间选择器
- 生产案例

### 1 什么是 NetworkPolicy

NetworkPolicy 定义 Pod 之间以及 Pod 与外部之间的网络访问规则。
**默认情况下，Pod 之间全通**。一旦有 NetworkPolicy 选中该 Pod，则变为 **默认拒绝，显式放行**。

> **重要行为规则**：
> - **Ingress 默认行为**：`podSelector: {}` 且未定义 `ingress` 规则 → 拒绝所有入站（最常用）
> - **Egress 默认行为**：**不写 `policyTypes: [Egress]` 时，出站流量不受任何限制（全通）**。只有明确写了 `policyTypes: [Egress]` 且定义了 egress 规则后，才会限制出站。
> - **规则叠加**：每个 `from`/`to` 条目之间是 OR 关系，同一个条目内的 `podSelector` 和 `namespaceSelector` 是 AND 关系。

> **前置条件**：使用的 CNI 插件必须支持 NetworkPolicy（Calico、Cilium、Weave 支持；Flannel 默认不支持）。

### 2 默认拒绝所有入站流量

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
  namespace: team-a
spec:
  podSelector: {}          # 选中命名空间内所有 Pod
  policyTypes:
    - Ingress
  # 没有 ingress 规则，默认拒绝所有入站
```

### 3 放行特定流量

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-access
  namespace: team-a
spec:
  podSelector:
    matchLabels:
      app: api-server       # 应用于 api-server Pod
  policyTypes:
    - Ingress
  ingress:
    # 允许来自同命名空间 frontend Pod 的 8080 端口流量
    - from:
        - podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8080
    # 允许来自 monitoring 命名空间的流量
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: 8080
```

### 4 限制出站流量

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-egress
  namespace: team-a
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Egress
  egress:
    # 只能访问同命名空间内 db 标签的 Pod 的 5432 端口
    - to:
        - podSelector:
            matchLabels:
              role: database
      ports:
        - protocol: TCP
          port: 5432
    # 允许 DNS 查询（通常需要）
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
```

### 5 生产最佳实践

```
┌──────────────────────────────────────────────┐
│  1. 全局命名空间级 deny-all 策略              │
│  2. 逐个服务声明需要哪些来源和端口            │
│  3. 限制出站至必要目标（防 SSRF/反弹 shell）  │
│  4. DNS 出站规则勿忘                          │
│  5. 使用标签选择器而非 IP                     │
└──────────────────────────────────────────────┘
```

---

## 第十五章 调度高级策略

- Taints & Tolerations（污点与容忍）
- Pod Topology Spread Constraints（拓扑分布）
- Pod Disruption Budget（中断预算）
- 节点亲和性实战总结

### 1 Taints & Tolerations（污点与容忍）

**Taint（污点）** 打在节点上，**排斥** Pod。**Toleration（容忍）** 定义在 Pod 上，**允许** Pod 调度到有对应 Taint 的节点。

#### 1.1 节点加污点

```shell
# 格式：kubectl taint nodes <node> <key>=<value>:<effect>
$ kubectl taint nodes k8s-node2 dedicated=database:NoSchedule
```

#### 1.2 Taint 效果

| Effect | 说明 |
|--------|------|
| `NoSchedule` | 只有带对应容忍的 Pod 才能调度到该节点 |
| `PreferNoSchedule` | 尽量不调度，但不强制（软约束） |
| `NoExecute` | 立即驱逐不匹配的 Pod，且不调度新 Pod |

#### 1.3 Pod 配置容忍

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: db-pod
spec:
  tolerations:
    - key: "dedicated"
      operator: "Equal"
      value: "database"
      effect: "NoSchedule"
    - key: "node.kubernetes.io/not-ready"
      operator: "Exists"
      effect: "NoExecute"
      tolerationSeconds: 300   # 节点 NotReady 后允许再运行 300 秒
  containers:
    - name: mysql
      image: mysql:8.0
```

#### 1.4 生产场景：GPU 节点隔离

```shell
# GPU 节点打污点，防止普通任务占用
$ kubectl taint nodes gpu-node-01 nvidia.com/gpu=true:NoSchedule
```

```yaml
# GPU 任务带上容忍
tolerations:
  - key: "nvidia.com/gpu"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

### 2 Pod Topology Spread Constraints（拓扑分布约束）

将同一应用的 Pod 均匀分布到不同的拓扑域（可用区、节点、机架），提升高可用性。

#### 2.1 基本用法

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-server
spec:
  replicas: 6
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      topologySpreadConstraints:
        # 跨可用区均匀分布
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule   # 或 ScheduleAnyway（软约束）
          labelSelector:
            matchLabels:
              app: web
        # 同时跨节点均匀分布
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: web
      containers:
        - name: nginx
          image: nginx:1.23
```

> **参数说明**：
> - `maxSkew`：任意两个拓扑域中 Pod 数量的最大差值
> - `topologyKey`：拓扑域的标签 key
> - `whenUnsatisfiable`：无法满足时是硬拒绝还是软允许

### 3 Pod Disruption Budget（PDB）

保护应用在**主动驱逐**（节点维护、集群升级、HPA 缩容）时不低于最少可用副本数。

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-pdb
spec:
  # minAvailable 或 maxUnavailable 二选一
  minAvailable: 2        # 至少保持 2 个 Pod 可用
  selector:
    matchLabels:
      app: api-server
```

```yaml
# 或使用百分比
spec:
  maxUnavailable: 25%    # 最多 25% 的 Pod 不可用
  selector:
    matchLabels:
      app: api-server
```

```shell
# 查看 PDB 状态
$ kubectl get pdb
NAME      MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
api-pdb   2               N/A               1                     5m
```

> **生产关键**：节点维护前执行 `kubectl drain` 时，若违反 PDB 限制，drain 会失败。

---

## 第十六章 SecurityContext 安全上下文

- Pod 安全上下文
- 容器安全上下文
- capabilities 管理
- 只读根文件系统
- seccomp / AppArmor

### 1 Pod 级安全上下文

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-pod
spec:
  securityContext:
    runAsNonRoot: true           # 禁止 root 运行
    runAsUser: 1000              # 指定 UID
    runAsGroup: 3000
    fsGroup: 2000                # volume 挂载时文件系统组
    seccompProfile:
      type: RuntimeDefault       # 使用容器运行时默认 seccomp
  containers:
    - name: app
      image: myapp:latest
```

### 2 容器级安全上下文

```yaml
containers:
  - name: app
    image: nginx:1.23
    securityContext:
      allowPrivilegeEscalation: false    # 禁止提权
      readOnlyRootFilesystem: true       # 根文件系统只读
      capabilities:
        drop:
          - ALL                           # 删除所有 capabilities
        add:
          - NET_BIND_SERVICE              # 只添加绑定低端口能力
      runAsUser: 1000
      runAsNonRoot: true
```

### 3 Capabilities 常用列表

| Capability | 说明 |
|------------|------|
| `NET_BIND_SERVICE` | 绑定 < 1024 端口 |
| `NET_ADMIN` | 网络管理操作 |
| `SYS_TIME` | 修改系统时间 |
| `NET_RAW` | 使用 RAW 和 PACKET socket |

> **最佳实践**：始终 `drop: [ALL]`，再按需 `add`。

### 4 只读根文件系统 + emptyDir

Nginx 需要可写临时目录的情况：

```yaml
containers:
  - name: nginx
    image: nginx:1.23
    securityContext:
      readOnlyRootFilesystem: true
    volumeMounts:
      - name: nginx-run
        mountPath: /var/run
      - name: nginx-cache
        mountPath: /var/cache/nginx
      - name: nginx-tmp
        mountPath: /tmp
  volumes:
    - name: nginx-run
      emptyDir: {}
    - name: nginx-cache
      emptyDir: {}
    - name: nginx-tmp
      emptyDir: {}
```

---

## 第十七章 滚动更新策略详解

- maxSurge / maxUnavailable
- 蓝绿部署
- 金丝雀部署
- 生产配置建议

### 1 滚动更新参数

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1            # 更新期间最多多出几个 Pod
      maxUnavailable: 1       # 更新期间最多几个 Pod 不可用
  minReadySeconds: 10         # Pod 就绪后等待 10 秒才认为可用
  revisionHistoryLimit: 5     # 保留最近 5 个 ReplicaSet 用于回滚
  template:
    ...
```

#### 参数含义

| 参数 | 说明 | 推荐值（生产）|
|------|------|---------------|
| `maxSurge` | 超出期望副本数的最大值（数字或百分比） | 25% |
| `maxUnavailable` | 最大不可用副本数（数字或百分比） | 0（核心服务）或 25% |
| `minReadySeconds` | Pod Ready 后还需等待的秒数 | 10-30s |
| `progressDeadlineSeconds` | 更新超时时间（默认 600s） | 根据应用启动时间调整 |

### 2 生产推荐配置

```yaml
# 核心高可用服务
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 2
    maxUnavailable: 0      # 零停机
  minReadySeconds: 30

# 一般服务
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 25%
    maxUnavailable: 25%
  minReadySeconds: 10
```

**滚动更新过程观察**：

```shell
# 发起更新
$ kubectl set image deployment/api-server api-server=myapi:v2

# 实时观察 Pod 更替过程
$ kubectl rollout status deployment/api-server
Waiting for deployment "api-server" rollout to finish: 2 out of 5 new replicas updated...
deployment "api-server" successfully rolled out

# 查看滚动版本历史
$ kubectl rollout history deployment/api-server
REVISION  CHANGE-CAUSE
1         <none>
2         <none>

# 查看具体某次修订的详情
$ kubectl rollout history deployment/api-server --revision=2

# 回滚到上一版本
$ kubectl rollout undo deployment/api-server

# 回滚到指定版本
$ kubectl rollout undo deployment/api-server --to-revision=1

# 暂停/恢复滚动更新（金丝雀验证时常用）
$ kubectl rollout pause deployment/api-server
$ kubectl rollout resume deployment/api-server
```

### 3 金丝雀发布（Canary）

通过创建第二个 Deployment 实现按比例分流：

```yaml
# 稳定版 Deployment，replicas: 9
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-stable
  labels:
    app: api
    version: stable
spec:
  replicas: 9
  selector:
    matchLabels:
      app: api
      version: stable
  template:
    metadata:
      labels:
        app: api
        version: stable
    spec:
      containers:
        - name: api
          image: myapi:v1.0.0
---
# 金丝雀版 Deployment，replicas: 1（10% 流量）
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-canary
  labels:
    app: api
    version: canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
      version: canary
  template:
    metadata:
      labels:
        app: api
        version: canary
    spec:
      containers:
        - name: api
          image: myapi:v2.0.0-rc1
---
# Service 选择器同时匹配两个版本
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api            # 匹配 stable + canary 的所有 Pod
  ports:
    - port: 80
      targetPort: 8080
```

> 配合 Ingress 使用 `canary` 注解可实现更精细的金丝雀分流（基于 Header、Cookie、权重）。

### 4 蓝绿部署概念

```
Blue（当前版本）:  replicas=5, 标签 version=blue
Green（新版本）:    replicas=5, 标签 version=green

切换方式: 修改 Service selector: version=blue → version=green
回滚方式: 改回 version=blue
```

---

## 第十八章 集群运维操作

- Node 维护操作
- etcd 备份与恢复
- kubeadm 集群升级
- 证书管理

### 1 Node 维护操作

```shell
# 1. 封锁节点（不再调度新 Pod）
$ kubectl cordon k8s-node2

# 2. 驱逐现有 Pod 到其他节点
$ kubectl drain k8s-node2 \
    --ignore-daemonsets \       # DaemonSet Pod 无法驱逐
    --delete-emptydir-data \    # 允许清理 emptyDir 数据
    --grace-period=60           # 优雅终止等待时间

# 3. 执行维护操作（升级内核、换硬盘等）

# 4. 恢复调度
$ kubectl uncordon k8s-node2
```

> **注意**：`drain` 操作会触发 PDB 检查，若违反 PDB 则 drain 会阻塞。

### 2 etcd 备份与恢复

etcd 是 Kubernetes 所有数据的存储后端，**备份 etcd 是灾难恢复的核心**。

#### 2.1 备份

```shell
# 通过 etcdctl 备份
$ ETCDCTL_API=3 etcdctl snapshot save /backup/etcd-snapshot-$(date +%Y%m%d).db \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key

# 验证备份
$ ETCDCTL_API=3 etcdctl snapshot status /backup/etcd-snapshot-20240601.db --write-out=table
```

> **生产建议**：每天至少备份一次，备份文件存放到远程安全位置。

#### 2.2 恢复

```shell
# 在所有控制平面节点停止 kube-apiserver
$ mkdir -p /var/lib/etcd-restore
$ ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd-snapshot-20240601.db \
    --data-dir=/var/lib/etcd-restore \
    --name=k8s-node1 \
    --initial-cluster=k8s-node1=https://10.15.0.5:2380 \
    --initial-advertise-peer-urls=https://10.15.0.5:2380

# 修改 etcd.yaml 的 data-dir 指向 /var/lib/etcd-restore
$ vim /etc/kubernetes/manifests/etcd.yaml
# 修改:
#   volumes:
#     - hostPath:
#         path: /var/lib/etcd-restore    # 原为 /var/lib/etcd
```

> **警告**：恢复 etcd 是高风险操作，务必在维护窗口内执行，并先在测试环境验证流程。

### 3 kubeadm 集群升级

升级遵循 **一次跨一个次版本号** 的原则（如 1.26 → 1.27 → 1.28）。

#### 3.1 升级控制平面节点

```shell
# 1. 查看当前版本和可用升级
$ kubeadm version
$ apt-cache madison kubeadm    # Debian/Ubuntu
$ yum list --showduplicates kubeadm    # CentOS/RHEL

# 2. 升级 kubeadm
$ yum install -y kubeadm-1.28.0-0 --disableexcludes=kubernetes

# 3. 验证升级计划
$ kubeadm upgrade plan

# 4. 执行升级
$ kubeadm upgrade apply v1.28.0

# 5. 驱逐该节点上的工作负载
$ kubectl drain k8s-node1 --ignore-daemonsets

# 6. 升级 kubelet 和 kubectl
$ yum install -y kubelet-1.28.0-0 kubectl-1.28.0-0 --disableexcludes=kubernetes
$ systemctl daemon-reload && systemctl restart kubelet

# 7. 恢复调度
$ kubectl uncordon k8s-node1
```

#### 3.2 升级工作节点

```shell
# 在每个 Worker 节点执行
$ yum install -y kubeadm-1.28.0-0 --disableexcludes=kubernetes
$ kubeadm upgrade node
$ kubectl drain <node-name> --ignore-daemonsets
$ yum install -y kubelet-1.28.0-0 kubectl-1.28.0-0 --disableexcludes=kubernetes
$ systemctl daemon-reload && systemctl restart kubelet
$ kubectl uncordon <node-name>
```

### 4 证书管理

```shell
# 查看证书到期时间
$ kubeadm certs check-expiration

# 手动续期证书（到期前执行）
$ kubeadm certs renew all

# 续期后重启控制平面组件
$ systemctl restart kubelet
$ # 静态 Pod (apiserver/controller-manager/scheduler) 会自动重启
```

---

## 第十九章 可观测性

- Prometheus + Grafana 监控
- 日志收集（Loki / EFK 方案介绍）
- 常用告警规则

### 1 Prometheus + Grafana 监控栈

#### 1.1 架构概览

```
┌──────────────┐         ┌──────────────┐
│  Prometheus  │──scrape─▶│  Targets     │
│   (采集+存储) │         │  (Pod/Node)  │
└──────┬───────┘         └──────────────┘
       │
       ├──▶ Grafana     (可视化查询)
       │
       └──▶ AlertManager (告警评估后推送)
              │
              ▼
         企业微信 / 钉钉 / Slack
```
> 注意：Grafana 和 AlertManager 都直连 Prometheus，二者互不依赖。AlertManager 只负责告警路由，不存储数据。

#### 1.2 快速部署（使用 Helm）

```shell
# 添加 Prometheus Community 仓库
$ helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
$ helm repo update

# 安装 kube-prometheus-stack（包含 Prometheus + Grafana + AlertManager）
$ helm install monitoring prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set grafana.adminPassword=admin123 \
    --set prometheus.prometheusSpec.retention=15d \
    --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName=nfs-client \
    --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=50Gi

# 查看 Grafana 密码
$ kubectl get secret monitoring-grafana -n monitoring -o jsonpath="{.data.admin-password}" | base64 -d
```

#### 1.3 访问 Grafana

```shell
# 端口转发
$ kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80

# 浏览器访问 http://localhost:3000
# 用户名：admin  密码：admin123
```

### 2 常用 PromQL 查询

```promql
# 集群 CPU 使用率
sum(rate(container_cpu_usage_seconds_total{container!=""}[5m])) by (namespace)

# Pod 内存使用 Top 10
topk(10, sum(container_memory_working_set_bytes{container!=""}) by (pod, namespace))

# 节点磁盘使用率
(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100

# Pod 重启速率
rate(kube_pod_container_status_restarts_total[15m]) > 0

# Deployment 副本不匹配
kube_deployment_spec_replicas{job="kube-state-metrics"}
  !=
kube_deployment_status_replicas_available{job="kube-state-metrics"}
```

### 3 关键告警规则

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: custom-alerts
  namespace: monitoring
data:
  alerts.yml: |
    groups:
      - name: kubernetes-apps
        rules:
          - alert: PodCrashLooping
            expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
            for: 5m
            labels:
              severity: warning
            annotations:
              summary: "Pod {{ $labels.pod }} is crash looping"

          - alert: DeploymentReplicasMismatch
            expr: kube_deployment_spec_replicas != kube_deployment_status_replicas_available
            for: 10m
            labels:
              severity: critical
            annotations:
              summary: "Deployment {{ $labels.deployment }} replicas mismatch"

          - alert: NodeHighCPU
            expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
            for: 5m
            labels:
              severity: warning
            annotations:
              summary: "Node {{ $labels.instance }} CPU > 80%"

          - alert: PersistentVolumeFilling
            expr: kubelet_volume_stats_available_bytes / kubelet_volume_stats_capacity_bytes < 0.1
            for: 5m
            labels:
              severity: critical
            annotations:
              summary: "PV {{ $labels.persistentvolumeclaim }} < 10% free"
```

### 4 日志收集方案

#### 方案对比

| 方案 | 组成 | 适用场景 |
|------|------|----------|
| **EFK** | Elasticsearch + Fluentd + Kibana | 大规模日志，需要强大搜索 |
| **PLG** | Promtail + Loki + Grafana | 轻量级，与 Prometheus 生态融合 |

#### Loki 快速部署

```shell
$ helm repo add grafana https://grafana.github.io/helm-charts
$ helm install loki grafana/loki-stack \
    --namespace logging \
    --create-namespace \
    --set fluent-bit.enabled=true \
    --set grafana.enabled=true
```

---

## 第二十章 Ingress 高级用法

- TLS/HTTPS 证书配置
- 路径重写
- 金丝雀发布
- 限流与白名单
- Gateway API 简介

以下示例基于 **Nginx Ingress Controller**：

```shell
# 安装 Nginx Ingress Controller
$ kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.0/deploy/static/provider/cloud/deploy.yaml
```

### 1 TLS/HTTPS 证书配置

```shell
# 创建 Secret 存放证书
$ kubectl create secret tls my-tls-secret \
    --cert=/path/to/fullchain.pem \
    --key=/path/to/privkey.pem \
    -n app-ns
```

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
  namespace: app-ns
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"    # HTTP 强制跳转 HTTPS
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
      secretName: my-tls-secret
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 8080
```

#### 排查案例：证书过期导致 HTTPS 不可用

```shell
# 1. 现象：浏览器报 SSL 错误，curl 返回 certificate expired
# 2. 定位：检查 Secret 中的证书过期时间
$ kubectl get secret my-tls-secret -n app-ns -o jsonpath='{.data.tls\.crt}' | \
    base64 -d | openssl x509 -noout -dates
notAfter=Jun 14 00:00:00 2026 GMT  # ← 已过期

# 3. 应急恢复
$ kubectl create secret tls my-tls-secret \
    --cert=/path/to/new-cert.pem --key=/path/to/new-key.pem \
    -n app-ns --dry-run=client -o yaml | kubectl apply -f -
# Ingress Controller 检测到 Secret 变化后热加载，约 30s 生效

# 4. 长期方案：设置 Prometheus 告警监控剩余天数
# probe_ssl_earliest_cert_expiry - time()) / 86400 < 30
```

> **原理**：Ingress Controller 通过 watch API Server 监听 Secret 变化，秒级自动重载。无需重启 Pod。

### 2 自动证书（cert-manager + Let's Encrypt）

```shell
# 安装 cert-manager
$ kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

```yaml
# 创建 ClusterIssuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

```yaml
# Ingress 使用自动证书
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
      secretName: auto-tls-secret      # cert-manager 自动创建
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 8080
```

### 3 路径重写

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rewrite-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /api(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: api-service
                port:
                  number: 8080
# 请求 /api/users → 后端收到 /users
```

### 4 金丝雀分流（Canary by Weight）

```yaml
# 稳定版 Ingress
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-stable
spec:
  ingressClassName: nginx
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: app-stable
                port:
                  number: 80
---
# 金丝雀版 Ingress（分流 10% 流量）
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"   # 10% 流量
spec:
  ingressClassName: nginx
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: app-canary
                port:
                  number: 80
```

### 5 限流

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/limit-rps: "100"          # 每秒请求数
    nginx.ingress.kubernetes.io/limit-connections: "50"    # 并发连接数
    nginx.ingress.kubernetes.io/limit-rate: "512k"         # 每个连接速率
```

### 6 IP 白名单

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/whitelist-source-range: "10.0.0.0/8,172.16.0.0/12"
```

### 7 Gateway API 简介

Gateway API 是 Kubernetes 社区推进的下一代 Ingress 标准，提供了更灵活、面向角色的路由模型：

```
Ingress (当前)              Gateway API (未来)
─────────────              ─────────────────
单个 Ingress 资源            GatewayClass → Gateway → HTTPRoute
注解满天飞                  原生字段表达
路由规则混杂                面向角色（基础设施 / 应用开发者分离）
```

**资源层级**：

| 资源 | 角色 | 说明 |
|------|------|------|
| `GatewayClass` | 基础设施管理员 | 定义可用的 Gateway 控制器类型 |
| `Gateway` | 集群管理员 | 定义具体的网关实例（监听端口等） |
| `HTTPRoute` | 应用开发者 | 定义路由规则 |

```yaml
# Gateway + HTTPRoute 示例（需先安装 Gateway API CRD）
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: app-route
spec:
  parentRefs:
    - name: my-gateway
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: api-service
          port: 8080
```

---

## 第二十一章 CRD & Operator 模式

> 本章以一条完整资源生命周期为主线：**设计 CR API → 请求准入 → 事件分发 → Reconcile 调和 → 状态反馈 → 删除清理**。随后再展开各组件实现、生产保障与真实案例。

### 先建立全局链路

```text
用户提交 CR
    │
    ▼
① API 契约：CRD Schema / 默认值 / 版本转换 / Status
    │
    ▼
② 请求准入：Mutating / Validating Webhook（可选）
    │
    ▼
API Server 持久化 CR
    │
    ▼
③ 事件分发：Informer(List + Watch) → 本地缓存 → WorkQueue
    │
    ▼
④ 调和：Reconcile 读取 Spec（期望）+ K8s/外部系统状态（实际）
    │
    ├── 计算差异 → 创建 / 更新 / 删除子资源，或调用外部 API
    └── 写入 Status / Conditions / Events / Metrics
    │
    ▼
⑤ 生命周期结束：DeletionTimestamp → Finalizer 清理外部资源 → GC 回收子资源
```

**阅读框架**：

| 阶段 | 本章回答的问题 | 对应章节 |
|---|---|---|
| 定义 API | 用户能声明什么，哪些状态对外可见，如何演进版本 | 1、2 |
| 运行调和 | CR 变更如何被感知并收敛为实际资源状态 | 3、4、5 |
| API 准入 | 哪些规则在写入 API Server 前默认化或拒绝 | 6 |
| 生产交付 | 如何保证正确性、性能、可观测性和故障可恢复 | 7 |
| 业务映射 | 如何将通用模型落到 SidecarSet 与 Tcaplus | 8 |

> **不要把事件当作事实本身。**事件只负责触发调和；Reconcile 始终以 CR、下游资源和外部系统的当前状态为准。Webhook 位于请求写入前，Controller 位于资源持久化后，二者共同构成 Operator 的 API 边界和运行闭环。

---

### 目录

- [1 CustomResourceDefinition（CRD）详解](#1-customresourcedefinitioncrd-详解)：定义 API 契约
- [2 CRD 高级特性](#2-crd-高级特性)：完善状态与版本演进
- [3 Operator 核心原理](#3-operator-核心原理)：建立事件与调和模型
- [4 Controller 开发全流程](#4-controller-开发全流程)：将模型落为代码
- [5 控制器关键组件深入](#5-控制器关键组件深入)：理解可靠性机制
- [6 Admission Webhook](#6-admission-webhook)：补齐 API 请求准入
- [7 生产级实践与反模式](#7-生产级实践与反模式)：验证生产质量
- [8 真实案例](#8-真实案例)：回到完整业务链路

---

### 1 CustomResourceDefinition（CRD）详解

CRD 是扩展 K8s API 的入口。定义一个 CRD 需要考虑以下维度：

#### 1.1 基础结构

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: gametasks.example.com    # <plural>.<group>
spec:
  group: example.com             # API Group
  scope: Namespaced              # Namespaced 或 Cluster
  names:
    plural: gametasks            # kubectl get gametasks
    singular: gametask           # kubectl get gametask
    kind: GameTask               # Go 类型名
    shortNames: [gt, gtsk]       # kubectl get gt
    categories: [all]            # kubectl get all 也显示此资源
  versions:
    - name: v1
      served: true               # 此版本可通过 API 访问
      storage: true              # 持久化存储版本（只有一个为 true）
      deprecated: false          # 标记为废弃
      schema:
        openAPIV3Schema: {...}   # OpenAPI v3 Schema 校验
      subresources:
        status: {}               # 启用 /status 子资源
        scale: {}                # 启用 /scale 子资源（需配合 spec.replicas）
      additionalPrinterColumns:  # kubectl get 的额外列
        - name: Status
          type: string
          jsonPath: .status.phase
```

#### 1.2 OpenAPI Schema 校验（生产必备）

**schema 是什么**：定义 CR 字段的类型、必填项、默认值、枚举、正则、最小值/最大值。kube-apiserver 在接收 CR 时会自动校验，不合法的请求直接被拒绝，省去 Controller 中大量校验代码。

```yaml
schema:
  openAPIV3Schema:
    type: object
    required: [spec]             # spec 必填
    properties:
      spec:
        type: object
        required: [image]        # spec 下 image 必填
        properties:
          image:
            type: string
            minLength: 1
            pattern: '^[a-z0-9._/:-]+$'
          replicas:
            type: integer
            minimum: 1
            maximum: 10000
            default: 1
          mode:
            type: string
            enum: [Snapshot, Dynamic]
            default: Snapshot
          selector:
            type: object
            properties:
              matchLabels:
                type: object
                additionalProperties:
                  type: string
              matchExpressions:
                type: array
                items:
                  type: object
                  required: [key, operator]
                  properties:
                    key:
                      type: string
                    operator:
                      type: string
                      enum: [In, NotIn, Exists, DoesNotExist]
                    values:
                      type: array
                      items:
                        type: string
          volumes:
            type: array
            maxItems: 20         # 限制数组长度
            items:
              type: object
```

**面试重点**：Schema 校验在 API Server 层完成，不符合 Schema 的请求直接返回 422，Controller 永远看不到非法数据。这是**声明式防护的第一道防线**。

#### 1.3 Scope：Namespaced vs Cluster

| Scope | 含义 | URL | 示例 |
|---|---|---|---|
| `Namespaced` | 资源属于某个命名空间 | `/apis/<group>/<version>/namespaces/<ns>/<plural>/<name>` | Deployment、Service、Tcaplus CR |
| `Cluster` | 全局资源 | `/apis/<group>/<version>/<plural>/<name>` | Node、Namespace、SidecarSet CR |

**选型原则**：
- 多数 Operator 用 `Namespaced`，天然实现多租户隔离
- `Cluster` 适用于集群级别能力，如 SidecarSet（需要对所有命名空间的 Pod 生效）
- 一旦设为 Cluster 就很难改回 Namespaced（需要删除 CRD 重建，数据丢失）

#### 1.4 Subresources（子资源）

```yaml
subresources:
  status: {}          # 启用 /status 端点
  scale:              # 启用 /scale 端点
    specReplicasPath: .spec.replicas
    statusReplicasPath: .status.replicas
    labelSelectorPath: .status.labelSelector
```

| 子资源 | 作用 | 为什么重要 |
|---|---|---|
| `/status` | 读写分离 | 用户不能直接修改 Status，只有 Controller 能写；避免用户伪造部署状态 |
| `/scale` | 扩缩容 | 供 HPA 使用，需 CR 有 `spec.replicas` 和 `status.replicas` 字段 |

**内存视角理解 /status 分离**：

```text
用户 kubectl apply CR                   Controller Reconcile
      │                                        │
      ▼                                        ▼
  PUT /apis/.../gametask              PUT /apis/.../gametask/status
      │                                        │
      └── spec.image: v2 ──────────────────► 读取 spec
      └── spec.replicas: 5 ────────────────► 计算期望
                                              │
                                              ▼
                                             创建/更新下游资源
                                              │
                                              ▼
                                         写入 status.phase: Running
                                         写入 status.succeeded: 3
```

### 2 CRD 高级特性

#### 2.1 AdditionalPrinterColumns（kubectl 显示列）

```yaml
additionalPrinterColumns:
  - name: Image        # 列标题
    type: string        # date / integer / boolean / string
    jsonPath: .spec.image
    priority: 0         # 0=始终显示, 1=-o wide 时显示
  - name: Phase
    type: string
    jsonPath: .status.phase
  - name: Succeeded
    type: integer
    jsonPath: .status.succeeded
  - name: Age
    type: date
    jsonPath: .metadata.creationTimestamp
```

效果：
```shell
$ kubectl get gt
NAME       IMAGE        PHASE       SUCCEEDED   AGE
agent-up   agent:v2     Running     3           5m
```

#### 2.2 多版本支持与 Conversion

当 CRD 需要从 v1alpha1 演进到 v1beta1 再到 v1 时：

```yaml
versions:
  - name: v1alpha1
    served: true       # 仍可通过 API 访问（旧用户可继续用）
    storage: false     # 不存储（存储统一用 v1）
    deprecated: true
    deprecationWarning: "v1alpha1 is deprecated, use v1 instead"
  - name: v1
    served: true
    storage: true      # 持久化版本
```

**版本转换（Conversion）**：不同 storage 版本之间需要转换逻辑。

```yaml
conversion:
  strategy: Webhook
  webhook:
    conversionReviewVersions: [v1]
    clientConfig:
      service:
        name: game-operator-webhook
        namespace: game-system
        path: /convert
```

```go
// Webhook 中实现 Convert 接口，把 v1alpha1 的字段映射到 v1
func (h *ConversionHandler) Convert(req *apiextensionsv1.ConversionRequest) *apiextensionsv1.ConversionResponse {
    // v1alpha1.imageRef → v1.image
    // v1alpha1.completions (int) → v1.completions (int32)
    // v1alpha1.status.phase → v1.status.conditions
}
```

**面试要点**：
- `served: true` + `deprecated: true`：旧版本仍可读但不能创建
- `served: false`：版本完全下线，旧 CR 无法通过 API 访问
- `storage: true`：只有一个版本是存储版本，etcd 中只存一份
- Conversion Webhook 是双向的（v1alpha1↔v1 互相转），Controller 必须实现

#### 2.3 Status 与 Conditions（结构化状态）

单个 `phase` 字段不足以描述复杂状态。生产级 CR 应使用 **Conditions** 标准模式：

```yaml
# ❌ 单一 phase
status:
  phase: Running
  message: "3/5 jobs done"

# ✅ 结构化 Conditions（推荐）
status:
  conditions:
    - type: Ready
      status: "False"
      reason: Progressing
      message: "Processing: 3/5 nodes completed"
      lastTransitionTime: "2024-01-15T10:30:00Z"
      observedGeneration: 5
    - type: Degraded
      status: "False"
      reason: Running
      message: "No errors"
    - type: Available
      status: "True"
      reason: MinimumNodesReady
      message: "Minimum nodes are ready"
```

**Conditions 设计原则**：
- 每个 Condition 表示一个布尔状态维度
- `observedGeneration` 标记该条件对应哪个 spec 版本（防止旧 condition 覆盖新状态）
- `lastTransitionTime` 记录状态切换时间（告警和 SLO 计时的依据）
- 只由 Controller 写入，用户只读

---

### 3 Operator 核心原理

前两节定义了 CR 的 API 契约；本节开始说明该契约在资源写入 API Server 后，如何经由事件、队列与调和逻辑转化为真实世界的状态。

#### 3.1 Operator = CRD + Controller

Operator 的本质是通过 **CRD 扩展 Kubernetes API** + **Controller 持续调和** 将业务运维知识编码为声明式自动化：

```
┌─────────────────────────────────────────────────────┐
│                     Operator                         │
│                                                     │
│  CRD（声明式 API）                                     │
│  ├── Spec: 用户声明的期望状态（image、replicas、...）  │
│  ├── Status: 控制器观察到的实际状态（phase、conditions）│
│  └── Schema: OpenAPI 校验 + 默认值 + 枚举约束           │
│                                                     │
│  Controller（调和引擎）                                │
│  ├── Informer: List + Watch → Indexer 本地缓存        │
│  ├── WorkQueue: 事件缓冲 + RateLimiter 指数退避       │
│  ├── Reconcile: 以单个 CR 为粒度，对比期望与实际        │
│  │               → 差量调和（Get + Compare + Act）     │
│  └── 关键机制: OwnerReference / Finalizer / Condition │
│                                                     │
│  业务编排（通过 CRD Spec 字段 + Reconcile 策略实现）    │
│  ├── 批量任务: 分片 + 并发控制 + 失败阈值 + 断点续作    │
│  ├── 灰度发布: 批次 + 审批 + 健康检查 + 回滚           │
│  └── 外部集成: 调用第三方 API + 异步轮询 + 状态反馈    │
└─────────────────────────────────────────────────────┘
```

> **注意**：游戏服热更新、Tcaplus DDL 变更、ODM 审批等是**具体业务场景**，通过 CRD Spec 字段设计和 Reconcile 中的策略分支来体现，而不是 Operator 框架的第三个独立模块。此处用「业务编排」表示它们属于 Operator 要解决的问题域，而非架构组成部分。

#### 3.2 调和循环（Reconciliation Loop）

Reconcile 是**基于当前状态的差量驱动**，而非事件驱动。每次收到的只是触发信号，真正的调和以 API Server 当前状态为唯一事实来源：

```text
┌──────────────────────────────────────────────────────────┐
│                    Reconcile Loop                          │
│                                                          │
│  触发源（Informer 事件 / RequeueAfter 定时 / List 初始化） │
│        │                                                 │
│        ▼                                                 │
│  ① 获取 CR —— 读取期望状态（Spec）                        │
│        │                                                 │
│        ▼                                                 │
│  ② 获取实际状态 —— List/Get 下游 K8s 资源 + 查询外部系统  │
│        │                                                 │
│        ▼                                                 │
│  ③ 计算差异（diff: desired vs actual）                    │
│        │                       │                         │
│     无差异                   有差异                        │
│        │                       │                         │
│        ▼                       ▼                         │
│  返回 success          ④ 执行调和操作                    │
│  返回 {} 或                Create / Update / Delete       │
│  {RequeueAfter}               │                          │
│   (轮询异步状态)               ▼                         │
│                         ⑤ 更新 Status + Condition         │
│                         ⑥ 记录 Event                     │
│                               │                          │
│                      ┌────────┴────────┐                 │
│                   全部完成           未完成                │
│                      │                 │                  │
│                      ▼                 ▼                  │
│                 return {}     return {RequeueAfter}        │
│                 (Forget)      (定时重入队)                 │
└──────────────────────────────────────────────────────────┘
```

**调和三原则**：
1. **幂等**：执行一次和执行多次，最终结果一致。创建操作使用确定性名称 + AlreadyExists 处理，不依赖内存状态
2. **不依赖事件顺序**：以 API Server 当前状态为唯一事实来源，事件丢失/重复/乱序不影响正确性
3. **最终一致**：不保证立即同步，但保证最终收敛到期望状态。这正是 Reconcile 必须幂等的原因——因为可能有延迟、事件丢失或重复执行

#### 3.3 事件分发链路

Informer → WorkQueue → Reconcile 的完整数据流：

```text
API Server
    │
    ▼ (List + Watch)
Reflector ──▶ Indexer (本地线程安全缓存，避免每次 List API Server)
    │
    ▼ (对象变更时按需触发，不阻塞)
EventHandler ──▶ WorkQueue (key = namespace/name)
    │                │
    │           RateLimitingQueue
    │           ├── 指数退避 (1s → 2s → 4s → 8s → ...)
    │           ├── 最大重试次数 (超过则丢弃)
    │           └── 令牌桶限速 (控制 API Server 写入频率)
    │
    ▼
Worker Pool (MaxConcurrentReconciles 并发)
    │
    ▼
Reconcile(key)
    ├── 成功 → Forget (从队列移除该 key)
    └── 失败 → AddRateLimited (延迟重新入队)
```

> **关键约束**：EventHandler 中**严禁执行重活**（网络请求、批量更新），只负责把 key 快速推入 WorkQueue。否则会阻塞 Informer 事件处理，导致 Watch 超时断开。

#### 3.4 三项关键机制

**OwnerReference（子资源生命周期绑定）**

```go
// 子 Job 通过 OwnerReference 绑定父 CR
// 父 CR 删除时 K8s GC 自动清理所有子资源
ownerRef := metav1.NewControllerRef(cr, schema.GroupVersionKind{...})
job.OwnerReferences = []metav1.OwnerReference{*ownerRef}
```

| 特性 | 说明 |
|---|---|
| 级联删除 | 父 CR 删除 → K8s 回收所有 OwnerReference 指向的子资源 |
| 反向触发 | 子资源变更 → `Owns()` 自动 enqueue 父 CR 到 WorkQueue |
| blockOwnerDeletion | 阻止父资源在子资源完成删除前被移除 |

**Finalizer（删除前清理钩子）**

```text
用户执行 kubectl delete
    │
    ▼
API Server 设置 DeletionTimestamp（不立即删除，等待 Finalizer 清空）
    │
    ▼
Controller 检测到 DeletionTimestamp ≠ nil
    │
    ├── 清理外部资源（Tcaplus 表、外部任务、云资源...）
    ├── 删除下游子资源
    └── 移除 Finalizer（controllerutil.RemoveFinalizer）
    │
    ▼
K8s 完成资源删除
```

> 必须设计超时和告警兜底，否则 Controller 故障会导致资源长期处于 `Terminating`。

**Condition（结构化多维度状态）**

单一 `phase` 字段无法同时表达多个维度的状态，Condition 支持并行生效：

```yaml
status:
  phase: Running
  conditions:
    - type: Progressing     # 正在推进
      status: "True"
      reason: TasksRunning
      message: "3/10 tasks running"
      observedGeneration: 5
    - type: Degraded        # 部分失败（可与 Progressing 同时为 True）
      status: "False"
      reason: AllHealthy
    - type: Available       # 可对外服务
      status: "True"
```

与 `phase` 的对比：

| | phase | conditions |
|---|---|---|
| 表达能力 | 单一值，互斥 | 多维度，并行 |
| 典型用途 | 整体阶段的快照 | 各子维度的详细状态 |
| 示例 | `Pending / Running / Succeeded / Failed` | `Progressing + Degraded + Available` 可同时存在 |

---

### 4 Controller 开发全流程

第 3 节解释了 Controller 为什么能够收敛状态；本节将该模型落实为 `controller-runtime` 中的 Manager、Watch 注册和 Reconcile 代码。开发顺序应始终是：先定义期望/实际状态，再编写调和逻辑，最后补齐运行时注册。

#### 4.1 controller-runtime 核心组件关系

```text
┌──────────────────────────────────────────────────────────┐
│                    controller-runtime                     │
│                                                          │
│  Manager ──▶ 管理所有 Controller 的生命周期               │
│     │                                                    │
│     ├──▶ Informer (per Controller)                       │
│     │    ├── Reflector: List + Watch API Server          │
│     │    ├── Indexer: 本地线程安全缓存                    │
│     │    └── EventHandler: 把事件 Push 到 WorkQueue      │
│     │                                                    │
│     ├──▶ WorkQueue                                       │
│     │    ├── 生产者: EventHandler                        │
│     │    ├── 消费者: Worker goroutine(s)                 │
│     │    └── RateLimiter: 指数退避 + 令牌桶              │
│     │                                                    │
│     ├──▶ Worker Pool                                     │
│     │    └── 并发执行 Reconcile(key)                     │
│     │                                                    │
│     ├──▶ Leader Election                                 │
│     │    └── Lease 资源保证单 Leader                     │
│     │                                                    │
│     └──▶ Metrics / Health / EventRecorder                │
└──────────────────────────────────────────────────────────┘
```

#### 4.2 Manager

Manager 是控制器运行时的顶层管理器：

```go
mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
    Scheme:                 scheme,          // 注册已知资源类型
    MetricsBindAddress:     ":8080",         // Prometheus metrics
    HealthProbeBindAddress: ":8081",         // 健康检查
    LeaderElection:         true,            // 多副本选主
    LeaderElectionID:       "game-operator",
    Port:                   9443,            // Webhook 端口
})
```

#### 4.3 Scheme 注册

```go
var scheme = runtime.NewScheme()

func init() {
    // 注册 K8s 内置资源
    utilruntime.Must(clientgoscheme.AddToScheme(scheme))
    // 注册自定义 CRD
    utilruntime.Must(gamev1.AddToScheme(scheme))
    // 注册依赖的外部资源（如 Job）
    utilruntime.Must(batchv1.AddToScheme(scheme))
}
```

**如果没有注册 Scheme**：controller-runtime 的 client 无法对该类型的对象进行 Get/List/Create/Update，Reconcile 中任何操作都会 panic。

#### 4.4 Controller 注册

```go
func (r *GameTaskReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&gamev1.GameTask{}).        // ① 主资源
        Owns(&batchv1.Job{}).           // ② 子资源（OwnerReference 关联）
        Watches(                         // ③ 外部资源
            &source.Kind{Type: &corev1.ConfigMap{}},
            handler.EnqueueRequestsFromMapFunc(r.findObjectsForConfigMap),
        ).
        WithOptions(controller.Options{
            MaxConcurrentReconciles: 4,  // ④ 并发 Worker 数
        }).
        WithEventFilter(predicate.Funcs{ // ⑤ 事件过滤
            UpdateFunc: func(e event.UpdateEvent) bool {
                // 只在 Spec 变化时触发（Status 变化不触发）
                return e.ObjectOld.GetGeneration() != e.ObjectNew.GetGeneration()
            },
        }).
        Complete(r)
}
```

| 配置项 | 作用 |
|---|---|
| `For()` | 主 CR，Controller 的核心监听目标 |
| `Owns()` | 子资源，子资源变化会通过 OwnerReference 反向触发父资源的 Reconcile |
| `Watches()` | 监听与主 CR 没有 OwnerReference 的外部资源 |
| `MaxConcurrentReconciles` | 并发 Worker 数，默认 1。数据库写密集型可设为 1，计算密集型可增加 |
| `WithEventFilter` | 按需过滤事件，避免无效 Reconcile |

#### 4.5 Reconcile 实现模板

```go
func (r *GameTaskReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    logger := log.FromContext(ctx)

    // ========== 1. 获取 CR ==========
    var task gamev1.GameTask
    if err := r.Get(ctx, req.NamespacedName, &task); err != nil {
        // CR 已被删除，返回 nil（不要 Requeue）
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // ========== 2. 处理 Finalizer ==========
    if !task.DeletionTimestamp.IsZero() {
        return r.handleFinalizer(ctx, &task)
    }
    if !controllerutil.ContainsFinalizer(&task, finalizerName) {
        controllerutil.AddFinalizer(&task, finalizerName)
        return ctrl.Result{}, r.Update(ctx, &task)
    }

    // ========== 3. 获取实际状态 ==========
    var childJobs batchv1.JobList
    if err := r.List(ctx, &childJobs,
        client.InNamespace(req.Namespace),
        client.MatchingLabels{"parent": task.Name},
    ); err != nil {
        return ctrl.Result{}, err
    }

    // ========== 4. 计算差异 ==========
    desired := r.buildDesiredJobs(&task)
    toCreate, toDelete := diff(childJobs.Items, desired)

    // ========== 5. 执行变更 ==========
    for _, job := range toCreate {
        if err := r.Create(ctx, job); err != nil {
            logger.Error(err, "Failed to create Job")
            return ctrl.Result{}, err
        }
        logger.Info("Created Job", "jobName", job.Name)
    }

    // ========== 6. 更新 Status ==========
    task.Status.Phase = computePhase(childJobs.Items)
    task.Status.Succeeded = countSucceeded(childJobs.Items)
    if err := r.Status().Update(ctx, &task); err != nil {
        return ctrl.Result{}, err
    }

    // ========== 7. 决定是否 Requeue ==========
    if task.Status.Phase == "Running" {
        return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
    }
    return ctrl.Result{}, nil // 不 Requeue
}
```

---

### 5 控制器关键组件深入

第 4 节给出的是实现骨架；本节回到其中最影响正确性与可靠性的机制：缓存如何同步、队列如何限速、资源如何级联删除、控制器如何选主并向用户反馈状态。

#### 5.1 Informer：List + Watch 机制

```
时间线：
  T0: Controller 启动
  T1: Reflector 发起 LIST → API Server 返回全量 Pod
  T2: Reflector 将每个 Pod 写入 DeltaFIFO 队列
  T3: Indexer 消费队列 → 存入本地缓存（内存 Map）
  T4: EventHandler 根据事件类型触发 → 写入 WorkQueue
  T5: Reflector 转为 WATCH → 只接收增量变更
  T6: 网络断开 → Reflector 从 resourceVersion 重新 LIST + WATCH
```

| 组件 | 职责 |
|---|---|
| **Reflector** | 与 API Server 交互，做 List + Watch |
| **DeltaFIFO** | 先进先出队列，缓冲 Watch 收到的增量事件 |
| **Indexer** | 线程安全的本地缓存，支持按 key/field 检索 |
| **EventHandler** | 将事件转为 WorkQueue 条目 |
| **WorkQueue** | 生产者-消费者队列，支持重试和限速 |

**为什么不能直接 EventHandler 中处理**：
- EventHandler 是同步回调，阻塞会丢失后续事件
- Watch 连接不稳定，需要 WorkQueue 的重试和限流能力
- 多个 Worker goroutine 并发处理需要 WorkQueue 解耦

#### 5.2 WorkQueue 与 RateLimiter

```go
// controller-runtime 内置三种 RateLimiter
// 1. BucketRateLimiter: 令牌桶
// 2. ItemExponentialFailureRateLimiter: 失败指数退避
// 3. MaxOfRateLimiter: 组合限流器

// 默认：指数退避 + 令牌桶组合
// 第1次失败 → 5ms 后重试
// 第2次失败 → 10ms
// 第3次失败 → 20ms
// ...
// 最大 1000s
```

```go
// 手动 Requeue
return ctrl.Result{Requeue: true}, nil               // 立即重试
return ctrl.Result{RequeueAfter: 30 * time.Second}, nil // 30 秒后重试
return ctrl.Result{}, err                            // 用 RateLimiter 重试
return ctrl.Result{}, nil                            // 不重试
```

#### 5.3 Finalizer：资源删除保护

**Finalizer 机制**：防止 CR 在 Controller 完成清理前被彻底删除。

```text
用户 kubectl delete cr
  │
  ▼
API Server 收到 DELETE 请求
  │
  ├── CR 有 Finalizer？
  │   ├── YES → 设置 DeletionTimestamp，不删除
  │   │          │
  │   │          ▼
  │   │     Controller Reconcile:
  │   │     ① 检测 DeletionTimestamp != nil
  │   │     ② 执行清理逻辑（删除外部表、子资源、DNS 记录）
  │   │     ③ 移除 Finalizer
  │   │     ④ return（API Server 自动完成删除）
  │   │
  │   └── NO → 直接从 etcd 删除
```

**生产案例**（kubegame-operator/tcaplus）：
```go
const (
    workdirFinalizer  = "tcaplus.apps.power.dev/workdir"
    zonetagFinalizer  = "tcaplus.apps.power.dev/zone-tag"
    barrierFinalizer  = "tcaplus.apps.power.dev/barrier"
)
// 删除 CR 时依次：
// ① 清理临时工作目录 Pod
// ② 移除 Tcaplus Zone 标签
// ③ 解除 Pod 启动屏障 ConfigMap
// ④ 移除对应 Finalizer
```

**注意事项**：
- 必须设计超时和告警（Controller 故障会导致 CR 永久 Terminating）
- 清理逻辑必须可重入（失败后下次 Reconcile 继续）
- 建议实现 admin 清理工具作为兜底

#### 5.4 OwnerReference：子资源管理

```go
// 父 CR 删除时，K8s 自动级联删除子资源
ownerRef := metav1.NewControllerRef(
    task,
    gamev1.GroupVersion.WithKind("GameTask"),
)
job.ObjectMeta.OwnerReferences = []metav1.OwnerReference{*ownerRef}
```

```text
GameTask CR (owner)
    │
    ├── Job-1 (OwnerReference → GameTask)
    ├── Job-2 (OwnerReference → GameTask)
    └── ConfigMap (OwnerReference → GameTask)

删除 GameTask → GC Controller 自动删除 Job-1、Job-2、ConfigMap
```

**注意**：`BlockOwnerDeletion: true` 可阻止 Owner 在子资源删除前被删除。

#### 5.5 Leader Election

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Controller-0 │     │ Controller-1 │     │ Controller-2 │
│   (Leader)   │     │  (Follower)  │     │  (Follower)  │
│              │     │              │     │              │
│  执行 Reconcile │     │  等待        │     │  等待        │
│  更新 Lease   │     │  监听 Lease  │     │  监听 Lease  │
└──────┬───────┘     └──────────────┘     └──────────────┘
       │ 宕机
       ▼
┌──────────────┐
│ Controller-1 │ ← 检测到 Lease 超时
│   (Leader)   │   成为新 Leader，开始 Reconcile
└──────────────┘
```

```go
// kubebuilder 自动生成
ctrl.NewManager(ctrl.Options{
    LeaderElection:   true,
    LeaderElectionID: "game-operator.example.com",  // 全局唯一
    LeaseDuration:    15 * time.Second,              // Leader 心跳超时
    RenewDeadline:    10 * time.Second,              // 续约超时
    RetryPeriod:      2 * time.Second,               // 重试间隔
})
```

**即使有 Leader Election，Controller 也必须幂等**：
- 网络分区可能导致双 Leader
- 旧 Leader 的事务可能在选举完成后仍执行

#### 5.6 Event 与 Condition

```go
// Event：用户通过 kubectl describe 可见
r.Recorder.Eventf(task, corev1.EventTypeNormal, "JobCreated",
    "Created Job %s for node %s", job.Name, nodeName)

r.Recorder.Eventf(task, corev1.EventTypeWarning, "SyncFailed",
    "Failed to sync tcaplus: %v", err)

// Condition：结构化状态
meta.SetStatusCondition(&task.Status.Conditions, metav1.Condition{
    Type:               "Progressing",
    Status:             metav1.ConditionTrue,
    Reason:             "JobsRunning",
    Message:            "3/5 jobs running",
    ObservedGeneration: task.Generation,
})
```

---

### 6 Admission Webhook

Webhook 位于全局链路的**请求准入阶段**：对象尚未持久化，也尚未进入 Informer 与 Reconcile。本章在 Controller 机制之后再展开它，是为了清楚区分两类职责：Webhook 负责默认化和拒绝不合法请求；Controller 负责持久化后的持续调和。

Webhook 在 API Server 处理请求的特定阶段拦截并修改/拒绝请求。

#### 6.1 Mutating vs Validating

| Webhook | 时机 | 作用 | 请求类型 |
|---|---|---|---|
| **Mutating** | 对象持久化前 | 修改对象（注入 sidecar、设置默认值） | AdmissionReview |
| **Validating** | Mutating 之后 | 校验对象（拒绝非法请求） | AdmissionReview |

**执行顺序**：Mutating Webhook → Schema Validation → Validating Webhook → etcd 写入

#### 6.2 生产案例：SidecarSet Pod 注入（Mutating）

```go
// Pod Mutating Webhook - 在 Pod 创建时注入 sidecar 容器
func (h *PodCreateHandler) Handle(ctx context.Context, req admission.Request) admission.Response {
    pod := &corev1.Pod{}
    json.Unmarshal(req.Object.Raw, pod)

    // ① 查找匹配的 SidecarSet
    sidecarSets := h.listMatchedSidecarSets(pod)

    // ② 注入 sidecar 容器
    for _, ss := range sidecarSets {
        for _, container := range ss.Spec.Containers {
            container.Image = h.resolveImage(container.Image)
            switch container.PodInjectPolicy {
            case BeforeAppContainer:
                pod.Spec.Containers = append([]corev1.Container{container}, pod.Spec.Containers...)
            case AfterAppContainer:
                pod.Spec.Containers = append(pod.Spec.Containers, container)
            }
        }
        // 合并 Volume
        pod.Spec.Volumes = mergeVolumes(pod.Spec.Volumes, ss.Spec.Volumes)
    }

    // ③ 返回修改后的 Pod（JSON Patch 或完整对象）
    marshaled, _ := json.Marshal(pod)
    return admission.PatchResponseFromRaw(req.Object.Raw, marshaled)
}
```

#### 6.3 生产案例：SidecarSet 校验（Validating）

```go
func (h *SidecarSetCreateUpdateHandler) Handle(ctx context.Context, req admission.Request) admission.Response {
    ss := &sidecarsetv1alpha1.SidecarSet{}
    json.Unmarshal(req.Object.Raw, ss)

    // ① 校验容器名称唯一
    names := make(map[string]bool)
    for _, c := range ss.Spec.Containers {
        if names[c.Name] {
            return admission.Denied(fmt.Sprintf("duplicate container name: %s", c.Name))
        }
        names[c.Name] = true
    }

    // ② 校验 updateStrategy
    if ss.Spec.UpdateStrategy.Type == "RollingUpdate" {
        if ss.Spec.UpdateStrategy.MaxUnavailable == nil {
            return admission.Denied("MaxUnavailable is required for RollingUpdate")
        }
    }

    return admission.Allowed("")
}
```

#### 6.4 Webhook 部署

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: MutatingWebhookConfiguration
metadata:
  name: sidecarset-mutating-webhook
webhooks:
  - name: mpod.kb.io
    clientConfig:
      service:
        name: sidecarset-webhook-service
        namespace: game-system
        path: /mutate-pod
      caBundle: <base64-encoded-ca-cert>
    rules:
      - operations: [CREATE]
        apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["pods"]
    failurePolicy: Fail       # Ignore（允许失败）/ Fail（拒绝请求）
    sideEffects: None
    admissionReviewVersions: [v1]
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: sidecarset-validating-webhook
webhooks:
  - name: vsidecarset.kb.io
    clientConfig:
      service:
        name: sidecarset-webhook-service
        namespace: game-system
        path: /validate-tkex-tencent-com-v1alpha1-sidecarset
    rules:
      - operations: [CREATE, UPDATE]
        apiGroups: [tkex.tencent.com]
        apiVersions: [v1alpha1]
        resources: [sidecarsets]
    failurePolicy: Fail
```

---

### 7 生产级实践与反模式

到这里已经具备从 CRD 到 Controller 的功能链路；生产环境的验收标准不只是“能创建资源”，还包括幂等、可重试、限流、可观测、权限隔离，以及在重启、选主切换和外部 API 失败时仍能恢复。

#### 7.1 必须遵守的原则

| 原则 | 说明 | 反例 |
|---|---|---|
| **幂等性** | 同一操作执行多次结果相同 | 用 Create 不处理 AlreadyExists |
| **可重入** | 进程重启后能从上次状态继续 | 用内存 map 存任务进度 |
| **最终一致** | 不依赖事件顺序 | 依赖 Update 事件先于 Delete 到达 |
| **最小权限** | SA 只授予需要的 RBAC | Role 中 verbs: ["*"] |
| **速率限制** | 控制 API Server 调用频率 | 循环中无条件 List |
| **错误分类** | 区分可重试/永久错误 | 所有错误都 Requeue |

#### 7.2 常见反模式

```go
// ❌ 反模式 1：在 Reconcile 中无过滤地 Update
func (r *Reconciler) Reconcile(ctx, req) (ctrl.Result, error) {
    task := r.Get(ctx, req)
    task.Status.Phase = "Running"
    r.Status().Update(ctx, task)           // 每次 Reconcile 都写 → 死循环
    return ctrl.Result{}, nil
}

// ✅ 正确：只在状态变化时 Update
if task.Status.Phase != "Running" {
    task.Status.Phase = "Running"
    r.Status().Update(ctx, task)
}

// ❌ 反模式 2：用内存缓存替代 API Server
var jobCache = make(map[string]*batchv1.Job)  // Controller 重启丢失

// ✅ 正确：从 API Server 获取实际状态
var job batchv1.Job
r.Get(ctx, client.ObjectKey{Name: jobName, Namespace: ns}, &job)

// ❌ 反模式 3：一次性处理所有资源
func (r *Reconciler) Reconcile(ctx, req) {
    var allPods corev1.PodList
    r.List(ctx, &allPods)                     // 8w Pod 全量加载
    for _, pod := range allPods.Items {
        r.processPod(pod)                     // 同步处理 → Reconcile 超时
    }
}

// ✅ 正确：分片 + WorkQueue + 只处理相关资源
// 每个 Reconcile 只处理一个 key 对应的单个 CR 及其子资源

// ❌ 反模式 4：不处理 AlreadyExists
func (r *Reconciler) createJob(task, job) error {
    return r.Create(ctx, job)                 // 重入时 panic
}

// ✅ 正确：
if err := r.Create(ctx, job); err != nil {
    if !apierrors.IsAlreadyExists(err) {
        return err
    }
    // 已存在，比较是否需要 Update
}
```

#### 7.3 性能考量

| 场景 | 问题 | 解决 |
|---|---|---|
| 大量 CR（>10k）| 全量 List 内存爆炸 | 使用 fieldSelector 或 labelSelector 限定范围 |
| 高频 Reconcile | API Server QPS 过载 | 合理设置 RequeueAfter，用 RateLimiter 控制 |
| CR Status 膨胀 | etcd 对象 > 1MB 限制 | Status 只存汇总，详细结果存外部 |
| Informer 缓存过大 | Controller 内存 OOM | 按需 Watch，用 predicate 过滤 |
| 多副本竞态 | 并行 Reconcile 同 CR | Leader Election + 幂等逻辑 |

#### 7.4 可观测性

```go
// Prometheus 指标
var (
    reconcileTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "controller_reconcile_total",
            Help: "Total number of reconciliations",
        },
        []string{"controller", "result"},  // success / error / requeue
    )
    reconcileDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "controller_reconcile_duration_seconds",
            Help:    "Reconcile duration distribution",
            Buckets: prometheus.ExponentialBuckets(0.001, 2, 15),
        },
        []string{"controller"},
    )
    workqueueDepth = prometheus.NewGaugeVec(
        prometheus.GaugeOpts{
            Name: "controller_workqueue_depth",
            Help: "Current depth of workqueue",
        },
        []string{"controller", "queue"},
    )
    workqueueLatency = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "controller_workqueue_latency_seconds",
            Help:    "Latency from event to reconcile start",
            Buckets: prometheus.ExponentialBuckets(0.001, 2, 15),
        },
        []string{"controller"},
    )
)
```

```
告警规则（Prometheus）：

# Reconcile 错误率 > 1%
rate(controller_reconcile_total{result="error"}[5m])
  /
rate(controller_reconcile_total[5m]) > 0.01

# WorkQueue 深度 > 100 且持续 10 分钟
controller_workqueue_depth > 100

# Reconcile P99 > 30 秒
histogram_quantile(0.99,
  rate(controller_reconcile_duration_seconds_bucket[5m])) > 30
```

---

### 8 真实案例

以下案例按本章主线阅读：先确认 CRD 如何表达意图，再看 Webhook 如何约束请求、Controller 如何创建或协调下游资源，最后关注 Status、Finalizer 和生产保障如何形成闭环。不要把案例理解为孤立代码片段。

#### 8.1 SidecarSet Operator（kubegame-operator/sidecarset）

**API Group**: `tkex.tencent.com/v1alpha1`，Cluster-scoped，127 文件，3 个 Webhook

**CR Spec 核心字段**：
```yaml
apiVersion: tkex.tencent.com/v1alpha1
kind: SidecarSet
metadata:
  name: game-hotfix-sidecar
spec:
  selector:
    matchLabels:
      app: gamesvr
  containers:
    - name: hotfix-agent
      image: hotfix:v2
      podInjectPolicy: AfterAppContainer    # 注入到业务容器之后
      upgradeStrategy: HotUpgrade            # 热升级模式（不着重 Pod）
  updateStrategy:
    type: RollingUpdate
    partition: 90         # 保留 90% 旧版本（金丝雀 10%）
    maxUnavailable: 20%
    paused: false
```

**Controller 核心逻辑**（`sidecarset_controller.go`，约 600 行）：

1. 监听 SidecarSet 和 Pod 资源
2. 按 selector 匹配 Pod → 计算 matchedPods / updatedPods / readyPods
3. 通过 ControllerRevision 管理版本（供回滚使用）
4. 按 updateStrategy 分批更新 Pod 的 sidecar 容器
5. 更新时操作 Pod 的 spec.containers 字段（原地更新，不重建 Pod）

**3 个 Webhook**：
- Pod Mutating Webhook：Pod 创建时自动注入匹配的 sidecar 容器
- SidecarSet Mutating Webhook：设置默认值
- SidecarSet Validating Webhook：校验容器名称唯一性、更新策略合法性

#### 8.2 Tcaplus Operator（kubegame-operator/tcaplus）

**API Group**: `apps.power.dev/v1alpha1`，Namespaced，3 个 Finalizer

**CR Spec 核心字段**：
```yaml
apiVersion: apps.power.dev/v1alpha1
kind: Tcaplus
spec:
  config:
    host: tcaplus-api.internal
    zoneId: "1001"
    appId: "2001"
  sourceRef:
    xml:
      configmap: tcaplus-configmap-world1001
  autoApprove: true
  rebuildInValid: false
  tcaplusHook:
    order: true          # 变更期间阻止 Pod 启动
    podDelete: true      # 变更前删除 Pod
  alert:
    wechat:
      webhook: https://qyapi.weixin.qq.com/...
```

**Controller 核心逻辑**（约 535 行）：

1. 监听 Tcaplus CR 和关联 ConfigMap
2. 检测 ConfigMap 变化（通过 ResourceVersion 差异判断）
3. Barrier 机制：写入特殊 ConfigMap key 阻止 Pod 启动
4. 调用 Tcaplus WebService API 执行表 DDL（创建/修改/删除）
5. 重试机制（最多 3 次）
6. 变更完成后写入 ConfigMap key 解除 Pod 启动屏障
7. 企微通知变更结果

**3 个 Finalizer**：
- `workdir`：清理临时工作目录
- `zonetag`：清理 Tcaplus Zone 标签
- `barrier`：清理 Pod 启动屏障

---

> **面试一句话总结**：Operator 不是"写了一个 CRD 和 Controller"，而是把运维知识（游戏热更新、Tcaplus DDL、ODM 审批）编码为声明式 API + 调和循环 + Webhook + Finalizer 的完整自动化体系。Controller 要做到幂等、可重入、最终一致、速率友好、错误可恢复。
>
> **相关文档**：`operator-csi-guide/` 目录下 01~04 系列文档（Operator/CSI 开发全流程）。

**相关阅读**：
- [kubebuilder 官方文档](https://book.kubebuilder.io/)
- [controller-runtime 源码](https://github.com/kubernetes-sigs/controller-runtime)
- [kubegame-operator 源码](https://git.woa.com/KubeGame/kubegame-operator) — 本章案例的真实项目

---

## 第二十二章 常见故障排查

- Pod 启动失败
- 网络问题
- 存储问题
- 性能排查

### 1 Pod 状态异常速查

| 状态 | 常见原因 | 排查命令 |
|------|----------|----------|
| `Pending` | 资源不足、镜像拉取、调度失败 | `kubectl describe pod` |
| `CrashLoopBackOff` | 应用启动失败、探针失败 | `kubectl logs -f --previous` |
| `ImagePullBackOff` | 镜像不存在、仓库认证失败 | `kubectl describe pod` |
| `Evicted` | 节点资源耗尽被驱逐 | `kubectl describe pod` |
| `Terminating` | 卡在终止过程 | `kubectl delete pod --force --grace-period=0` |
| `Init:Error` | Init 容器失败 | `kubectl logs <pod> -c <init-container>` |

### 2 常用排查命令

```shell
# 1. Pod 详情（看 Events 最关键）
$ kubectl describe pod <pod-name> -n <ns>

# 2. 查看当前日志
$ kubectl logs <pod-name> -n <ns> --tail=100

# 3. 查看上一次崩溃的日志
$ kubectl logs <pod-name> -n <ns> --previous

# 4. 进入 Pod 排查
$ kubectl exec -it <pod-name> -n <ns> -- /bin/sh

# 5. 使用 debug 容器（1.23+）
$ kubectl debug -it <pod-name> -n <ns> --image=busybox --target=<container-name>

# 6. 查看 Node 资源
$ kubectl describe node <node-name>
$ kubectl top node
$ kubectl top pod -A

# 7. 查看事件
$ kubectl get events -n <ns> --sort-by='.lastTimestamp'

# 8. 查看 API Server 日志（控制平面节点）
$ kubectl logs -n kube-system kube-apiserver-k8s-node1

# 9. 验证 DNS 解析
$ kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes.default
```

### 3 ImagePullBackOff 排查

```shell
# 1. 确认镜像名是否正确
$ kubectl describe pod <pod> | grep -A5 "Events"

# 2. 确认私有仓库的 imagePullSecrets 已配置
$ kubectl get pod <pod> -o jsonpath='{.spec.imagePullSecrets}'

# 3. 创建 imagePullSecrets
$ kubectl create secret docker-registry regcred \
    --docker-server=<registry> \
    --docker-username=<user> \
    --docker-password=<pass> \
    -n <ns>
```

```yaml
# 在 Pod/Deployment 中引用
spec:
  imagePullSecrets:
    - name: regcred
```

### 4 CrashLoopBackOff 排查流程

```
1. kubectl logs --previous → 看有没有应用错误
2. kubectl describe pod → 看探针是否失败（Liveness/Readiness）
3. kubectl exec 进入容器 → 检查文件、权限、环境变量
4. 检查资源限制 → limits 是否太小导致 OOM
5. 检查挂载的 ConfigMap/Secret → 是否存在、格式是否正确
```

### 5 Service 网络不通的诊断顺序

当 Pod 间通信失败时，按以下链路逐层排查：

```
客户端 Pod → DNS 解析 → Service ClusterIP → kube-proxy 规则 → 后端 Pod
   │            │              │                  │                │
   ▼            ▼              ▼                  ▼                ▼
Step 1      Step 2          Step 3            Step 4          Step 5
```

| Step | 检查项 | 命令 |
|------|--------|------|
| 1 | 客户端 Pod 网络正常 | `kubectl exec <pod> -- ping 8.8.8.8` |
| 2 | DNS 能解析 Service 名 | `kubectl exec <pod> -- nslookup <svc>.<ns>` |
| 3 | Service 有 Endpoints | `kubectl get endpoints <svc> -n <ns>` |
| 4 | kube-proxy 规则正常 | `kubectl logs -n kube-system -l k8s-app=kube-proxy` |
| 5 | 后端 Pod 端口监听 | `kubectl exec <pod> -- netstat -tlnp` |

### 6 Service 网络不通排查

```shell
# 1. 确认 Service 是否有 Endpoints
$ kubectl get endpoints <svc> -n <ns>
# 若为空，检查 selector 是否匹配 Pod 的 labels

# 2. 创建临时 Pod 测试
$ kubectl run test-curl --image=curlimages/curl --rm -it --restart=Never -- \
    curl -v http://<service>.<namespace>:<port>

# 3. 测试 DNS 解析
$ kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup <service>

# 4. 检查 NetworkPolicy 是否阻止了流量
$ kubectl get networkpolicy -A

# 5. 检查 kube-proxy 状态
$ kubectl get pods -n kube-system -l k8s-app=kube-proxy
$ kubectl logs -n kube-system -l k8s-app=kube-proxy --tail=50
```

### 7 节点资源压力

```shell
# 查看节点状况
$ kubectl describe node <node> | grep -A5 "Conditions"
# MemoryPressure / DiskPressure / PIDPressure → 节点即将驱逐 Pod

# 查看哪些 Pod 消耗资源最多
$ kubectl top pod -A --sort-by=cpu
$ kubectl top pod -A --sort-by=memory
```

---

## 第二十三章 生产最佳实践速查表

### 1 Deployment

| 配置项 | 推荐值 | 原因 |
|--------|--------|------|
| `replicas` | ≥ 2 | 避免单点故障 |
| `maxUnavailable` | 0 | 零停机发布（核心服务） |
| `minReadySeconds` | 10-30 | 给健康检查缓冲时间 |
| `revisionHistoryLimit` | 5 | 保留回滚历史 |
| `resources.requests` | 真实典型值 | 调度和 HPA 的基础 |
| `livenessProbe` | 必须 | 自动重启异常容器 |
| `readinessProbe` | 必须 | 流量只打到健康 Pod |
| `startupProbe` | 慢启动应用必备 | 避免初始化期间被误杀 |
| `terminationGracePeriodSeconds` | 30-60 | 优雅停机缓冲 |

### 2 Pod

| 配置项 | 推荐值 | 原因 |
|--------|--------|------|
| `runAsNonRoot` | `true` | 安全合规 |
| `allowPrivilegeEscalation` | `false` | 安全合规 |
| `readOnlyRootFilesystem` | `true`（尽量） | 安全合规 |
| `resources.limits` | ≥ 2× requests | 允许突发负载 |
| `topologySpreadConstraints` | 必须（多 AZ） | 跨可用区高可用 |
| `affinity.podAntiAffinity` | 推荐 | 同类 Pod 分散部署 |

### 3 安全

| 配置项 | 推荐值 |
|--------|--------|
| Secrets 加密 | 使用 etcd encryption at rest 或 external secrets |
| NetworkPolicy | 全局拒绝 + 按需放行 |
| RBAC | 最小权限原则 |
| 镜像扫描 | CI 流水线集成 Trivy / Clair |

### 4 运维

| 操作 | 频率 |
|------|------|
| etcd 备份 | 每日 |
| 证书检查 | 每月 |
| 集群升级 | 紧跟社区补丁版本 |
| 资源容量规划 | 每月 |
| 安全审计日志 | 持续 |

---

## 第二十四章 GitOps & ArgoCD

- GitOps 理念
- ArgoCD 架构与核心概念
- 安装与配置
- 多环境管理
- 生产最佳实践

### 1 什么是 GitOps

GitOps 是一种持续交付方法论，以 **Git 仓库作为单一事实来源（Single Source of Truth）**。
集群的期望状态由 Git 中存储的 YAML 清单定义，控制器自动将集群实际状态对齐到 Git 中的期望状态。

```
┌─────────┐    git push    ┌─────────┐    sync    ┌──────────────┐
│  开发者  │───────────────▶│ Git 仓库 │──────────▶│ Kubernetes   │
│  /CI系统 │                │ (清单)   │            │  集群        │
└─────────┘                └─────────┘            └──────────────┘
                                                      │
                                                ┌─────▼─────┐
                                                │  ArgoCD   │
                                                │ (控制器)   │
                                                └───────────┘
```

**核心收益**：
- 变更可追溯：每条改动对应 Git commit
- 回滚简单：git revert + sync
- 审计合规：谁、何时、改了什么一目了然
- 灾难恢复：新集群直接 sync 即可重建全部应用

### 2 ArgoCD 架构

```
┌─────────────────────────────────────────┐
│                ArgoCD                    │
│  ┌──────────┐  ┌──────────┐             │
│  │API Server│  │Repo Server│   Git Repo  │
│  └────┬─────┘  └────┬─────┘       ▲      │
│       │             │             │      │
│  ┌────▼─────────────▼──┐         │      │
│  │ Application         │─────────┘      │
│  │ Controller          │                │
│  └────────┬────────────┘                │
│           │ apply                        │
│  ┌────────▼────────────┐                │
│  │  Kubernetes 集群     │◀──────────────┘
│  └─────────────────────┘
└─────────────────────────────────────────┘
```

### 3 安装 ArgoCD

```shell
# 1. 创建命名空间并安装
$ kubectl create namespace argocd
$ kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 2. 暴露 ArgoCD API Server（NodePort 方式）
$ kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"NodePort","ports":[{"port":443,"nodePort":30443}]}}'

# 3. 获取初始 admin 密码
$ kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# 4. 安装 ArgoCD CLI
$ brew install argocd    # macOS
# 或下载二进制：https://github.com/argoproj/argo-cd/releases

# 5. 登录
$ argocd login <ARGOCD_SERVER>:30443 --username admin --password <password> --insecure
```

### 4 核心概念

| 概念 | 说明 |
|------|------|
| **Application** | 一组 Kubernetes 资源的集合，关联到一个 Git 仓库路径 |
| **Project** | Application 的逻辑分组，可设置允许的源仓库和目标集群 |
| **Repository** | 存储 Kubernetes 清单的 Git 仓库 |
| **Cluster** | 部署目标的 Kubernetes 集群 |
| **Sync** | 将 Git 中的期望状态应用到集群的过程 |

#### 4.1 Sync 循环原理

ArgoCD Application Controller 以 `sync` 机制维持集群状态与 Git 一致：

```
┌──────────────────────────────────────────────┐
│  Sync 触发方式（二选一，互不冲突）:            │
│                                              │
│  1. Polling（默认 3 分钟）:                   │
│     每 3 分钟自动检查 Git → 发现 diff → sync  │
│                                              │
│  2. Webhook 推送（推荐）:                     │
│     Git push → Webhook → ArgoCD → 立即 sync  │
│                                              │
│  3. Manual Sync:                             │
│     argocd app sync <app> 或 Web UI 点击     │
└──────────────────────────────────────────────┘
```

> **重要**：修改 Git 后，Polling 模式下最多等 3 分钟；Webhook 模式下延迟 <10 秒。生产环境务必配置 Webhook。

### 5 创建 Application

#### 5.1 准备 Git 仓库

```
git-repo/
├── app-base/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── kustomization.yaml
├── overlays/
│   ├── dev/
│   │   └── kustomization.yaml
│   ├── staging/
│   │   └── kustomization.yaml
│   └── prod/
│       └── kustomization.yaml
```

#### 5.2 通过 Web UI 创建

打开 `https://<ARGOCD_SERVER>:30443` → `+ New App`：

```
Application Name:  my-app
Project:           default
Sync Policy:       Automatic
  ✅ Prune Resources      # 删除 Git 中不存在的资源
  ✅ Self Heal            # 自动修复偏离
Repository URL:    https://github.com/org/app-manifests.git
Revision:          main
Path:              overlays/prod
Cluster:           https://kubernetes.default.svc
Namespace:         app-prod
```

#### 5.3 通过 YAML 声明式创建（推荐）

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io   # 级联删除
spec:
  project: default
  source:
    repoURL: https://github.com/org/app-manifests.git
    targetRevision: main
    path: overlays/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: app-prod
  syncPolicy:
    automated:
      prune: true        # 删除 Git 中移除的资源
      selfHeal: true     # 自动修复手动变更
    syncOptions:
      - CreateNamespace=true
      - PruneLast=true   # 先创建新资源再删旧资源
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

### 6 多环境 / 多集群管理

#### 6.1 多环境（同一集群不同命名空间）

使用 Kustomize overlay 模式：

```yaml
# overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: app-prod
resources:
  - ../../app-base
patches:
  - patch: |-
      - op: replace
        path: /spec/replicas
        value: 5
    target:
      kind: Deployment
      name: my-app
```

分别创建 prod / staging 两个 Application，指向不同 Path。

#### 6.2 管理外部集群

```shell
# 注册外部集群
$ argocd cluster add <cluster-context>
```

```yaml
# Application 指定部署到外部集群
spec:
  destination:
    server: https://10.20.0.1:6443     # 外部集群 API Server
    namespace: app-prod
```

### 7 App of Apps 模式（应用集管理）

用一个 ArgoCD Application 管理其他所有 Application：

```yaml
# app-of-apps.yaml — 根 Application
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: apps
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/cluster-bootstrap.git
    targetRevision: main
    path: apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```
apps/                          # 这是 app-of-apps 指向的目录
├── app-backend.yaml           # 每个文件是一个 Application 定义
├── app-frontend.yaml
├── app-monitoring.yaml
├── app-logging.yaml
└── app-ingress.yaml
```

### 8 生产最佳实践

| 建议 | 说明 |
|------|------|
| 清单与源码分离 | 应用代码一个仓库，部署清单另一个仓库 |
| 分支保护 | main 分支禁止直接 push，要求 PR + 审批 |
| Sync Policy 谨慎使用 `selfHeal` | 紧急手动修复不会被自动回退（建议只在 staging 启用） |
| Secrets 不要明文存 Git | 使用 Sealed Secrets / External Secrets Operator / Vault |
| 配合 Image Updater | ArgoCD Image Updater 自动更新镜像 tag |
| 通知集成 | 配置 Slack / Webhook 通知部署状态 |
| 健康检查 | 为每个 Application 自定义 Health Check |

### 9 ArgoCD Image Updater

自动检测新镜像并更新 Git 中的镜像 tag：

```yaml
metadata:
  annotations:
    argocd-image-updater.argoproj.io/image-list: nginx=docker.io/nginx
    argocd-image-updater.argoproj.io/nginx.update-strategy: semver
    argocd-image-updater.argoproj.io/nginx.allow-tags: regexp:^1\.2[0-9]\..*$
    argocd-image-updater.argoproj.io/write-back-method: git
```

---

## 第二十五章 云资源集成

- Kubernetes 与云平台资源协同
- 存储（云盘 / 对象存储）
- 负载均衡
- DNS 与 ExternalDNS
- External Secrets Operator
- 生产场景

### 1 云平台集成全景

```
┌──────────────────────────────────────────────────────┐
│                  Kubernetes 集群                      │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐          │
│  │  Pod    │  │  Pod    │  │ External     │          │
│  │         │  │         │  │ Secrets Op   │          │
│  └────┬────┘  └────┬────┘  └──────┬──────┘          │
│       │ pvc         │ svc/type:   │ fetch secret     │
│       ▼             │ LoadBalancer│                  │
│  ┌─────────┐  ┌─────▼────┐  ┌─────▼──────┐          │
│  │ CSI     │  │ Cloud    │  │ AWS SM /   │          │
│  │ Driver  │  │ LB       │  │ Vault /    │          │
│  └────┬────┘  └─────┬────┘  │ Tencent SSM│          │
└───────┼─────────────┼───────┴─────┬───────┘─────────┘
        │             │             │
   ┌────▼────┐   ┌────▼────┐   ┌───▼─────┐
   │ 云硬盘   │   │ 云 LB   │   │ 密钥管理 │
   │ CBS/PD  │   │ CLB/ELB │   │   服务   │
   └─────────┘   └─────────┘   └─────────┘
```

### 2 存储集成（CSI Driver）

#### 2.1 动态创建云盘 PVC

不同云平台的 StorageClass 示例：

```yaml
# 腾讯云 CBS
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cbs-premium
provisioner: com.tencent.cloud.csi.cbs
parameters:
  type: CLOUD_PREMIUM          # 高性能云硬盘
  # type: CLOUD_SSD            # SSD 云硬盘
  # type: CLOUD_HSSD           # 增强型 SSD
  # encrypt: "ENCRYPT"         # 加密
reclaimPolicy: Delete
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer   # 等待 Pod 调度后再创建（可用区感知）
```

```yaml
# AWS EBS
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
  iops: "3000"
  throughput: "125"
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
```

```yaml
# GCP Persistent Disk
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: pd-balanced
provisioner: pd.csi.storage.gke.io
parameters:
  type: pd-balanced
  replication-type: regional-pd   # 区域复制（高可用）
```

#### 2.2 使用云盘 PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: cbs-ssd
  resources:
    requests:
      storage: 100Gi
```

```yaml
# StatefulSet 挂载
volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: cbs-ssd
      resources:
        requests:
          storage: 100Gi
```

#### 2.3 Volume Snapshot（云盘快照）

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: cbs-snapshot-class
driver: com.tencent.cloud.csi.cbs
deletionPolicy: Delete
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: mysql-snapshot-20240601
spec:
  volumeSnapshotClassName: cbs-snapshot-class
  source:
    persistentVolumeClaimName: mysql-data
```

快照恢复：

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-data-restored
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: cbs-ssd
  resources:
    requests:
      storage: 100Gi
  dataSource:
    name: mysql-snapshot-20240601
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
```

#### 2.4 CSI 驱动内部原理

CSI（Container Storage Interface）将存储厂商插件与 K8s 核心解耦，标准化三个 gRPC 服务：

```
┌─────────────────────────────────────────────────────────┐
│                    CSI 驱动架构                           │
│                                                         │
│  ┌─────────────────┐     ┌─────────────────┐            │
│  │ CSI Controller  │     │  CSI Node       │            │
│  │ (Deployment)    │     │  (DaemonSet)    │            │
│  │                 │     │                 │            │
│  │ CreateVolume()   │     │ NodeStageVolume()│           │
│  │ DeleteVolume()   │     │ NodePublishVolume()│         │
│  │ CreateSnapshot() │     │ NodeUnpublishVolume()│       │
│  │ ControllerExpandVolume()│ NodeExpandVolume()│         │
│  └────────┬────────┘     └────────┬────────┘            │
│           │ 调用云 API              │ 挂载/格式化          │
│           ▼                        ▼                     │
│  ┌─────────────────────────────────────────┐           │
│  │          云存储后端 (CBS/EBS/PD)         │           │
│  └─────────────────────────────────────────┘           │
│                                                         │
│  ┌─────────────────┐                                   │
│  │ CSI Identity    │   (所有 CSI 驱动必须实现)           │
│  │ GetPluginInfo()  │                                   │
│  │ GetPluginCapabilities()│                             │
│  │ Probe()          │                                   │
│  └─────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

**三个核心 gRPC 服务**：

| 服务 | 运行位置 | 职责 |
|------|----------|------|
| **Identity** | Controller + Node | 返回驱动信息和能力 |
| **Controller** | Deployment (单副本) | 创建/删除/快照/扩容云盘 |
| **Node** | DaemonSet (每节点) | 挂载/卸载/格式化到 Pod |

**CSI Sidecar 容器（由 external-provisioner 等注入）**：

| Sidecar | 职责 |
|---------|------|
| `external-provisioner` | 监听 PVC → 调用 Controller.CreateVolume |
| `external-attacher` | 监听 VolumeAttachment → 调用 Controller.PublishVolume |
| `external-snapshotter` | 监听 VolumeSnapshot → 调用 Controller.CreateSnapshot |
| `external-resizer` | 监听 PVC 扩容请求 → 调用 Controller.ExpandVolume |
| `node-driver-registrar` | 注册 CSI Node 驱动到 kubelet |
| `livenessprobe` | 检测 CSI 驱动健康状态 |

**CSI 卷生命周期**：

```
用户创建 PVC → external-provisioner 检测到 PVC
  → 调用 CSI Controller.CreateVolume() → 云 API 创建云盘 → 返回 VolumeID
  → PV 创建(含 VolumeHandle=VolumeID) → PV 绑定 PVC

Pod 调度到节点 → external-attacher 检测到 VolumeAttachment
  → 调用 CSI Controller.ControllerPublishVolume() → 云 API 挂载云盘到节点
  → kubelet 调用 CSI Node.NodeStageVolume() → 格式化/挂载全局路径
  → kubelet 调用 CSI Node.NodePublishVolume() → bind mount 到 Pod 目录

Pod 删除 → NodeUnpublishVolume() → 卸载 Pod 目录
  → ControllerUnpublishVolume() → 云 API 卸载云盘
  → PVC 删除 → DeleteVolume() → 云 API 删除云盘
```

**CSI 迁移（CSI Migration）**：K8s 1.23+ 将内置的 in-tree 存储插件（如 `kubernetes.io/aws-ebs`）逐步迁移为 CSI 驱动。迁移后 in-tree provisioner 名称仍可用，但底层自动路由到 CSI 驱动。

```yaml
# CSI Ephemeral Volume（Pod 生命周期内临时卷）
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: app
      volumeMounts:
        - name: scratch
          mountPath: /scratch
  volumes:
    - name: scratch
      csi:
        driver: com.tencent.cloud.csi.cbs
        volumeAttributes:
          type: CLOUD_SSD
```

### 3 负载均衡

#### 3.1 LoadBalancer Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-lb
  annotations:
    # 腾讯云
    service.kubernetes.io/qcloud-loadbalancer-internet-charge-type: "TRAFFIC_POSTPAID_BY_HOUR"
    service.kubernetes.io/qcloud-loadbalancer-internet-max-bandwidth-out: "100"
    # AWS
    # service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    # service.beta.kubernetes.io/aws-load-balancer-internal: "true"
spec:
  type: LoadBalancer
  selector:
    app: nginx
  ports:
    - port: 80
      targetPort: 80
```

```shell
# 查看分配的云 LB 公网 IP
$ kubectl get svc nginx-lb -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

### 4 ExternalDNS

自动管理云 DNS 记录，使 Service/Ingress 的域名自动解析。

#### 4.1 安装

```shell
$ helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
$ helm install external-dns external-dns/external-dns \
    --namespace kube-system \
    --set provider=tencentcloud \
    --set tencentcloud.secretId=<YOUR_SECRET_ID> \
    --set tencentcloud.secretKey=<YOUR_SECRET_KEY> \
    --set policy=sync
```

#### 4.2 使用

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx
  annotations:
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    external-dns.alpha.kubernetes.io/ttl: "300"
spec:
  type: LoadBalancer
  ports:
    - port: 80
```

```shell
# 自动创建 DNS 记录：api.example.com → <LB_IP>
```

```yaml
# Ingress 同样支持
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  annotations:
    external-dns.alpha.kubernetes.io/hostname: "app.example.com,www.example.com"
spec:
  ...
```

### 5 External Secrets Operator

将云平台密钥管理服务（AWS Secrets Manager / Tencent SSM / Vault / GCP Secret Manager）中的密钥同步到 Kubernetes Secret。

#### 5.1 安装

```shell
$ helm repo add external-secrets https://charts.external-secrets.io
$ helm install external-secrets external-secrets/external-secrets \
    --namespace external-secrets \
    --create-namespace
```

#### 5.2 SecretStore 配置

```yaml
# SecretStore（命名空间级别）或 ClusterSecretStore（集群级别）
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secretstore
  namespace: default
spec:
  provider:
    aws:
      service: SecretsManager
      region: ap-east-1
      auth:
        secretRef:
          accessKeyIDSecretRef:
            name: aws-creds
            key: access-key
          secretAccessKeySecretRef:
            name: aws-creds
            key: secret-access-key
```

#### 5.3 ExternalSecret 同步

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: app-secrets
  namespace: default
spec:
  refreshInterval: 1h          # 每小时同步一次
  secretStoreRef:
    name: aws-secretstore
    kind: SecretStore
  target:
    name: app-secrets-k8s      # Kubernetes 中的 Secret 名称
    creationPolicy: Owner
  data:
    - secretKey: DB_PASSWORD   # K8s Secret 中的 key
      remoteRef:
        key: prod/db/password  # 云平台中的路径
        property: password
    - secretKey: API_KEY
      remoteRef:
        key: prod/api/keys
        property: api-key
```

Pod 使用（无感知差异）：

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: app-secrets-k8s
        key: DB_PASSWORD
```

> **安全收益**：Secret 原文只存在于云密钥管理服务中，Git 中零暴露。

### 6 生产建议

| 场景 | 推荐方案 |
|------|----------|
| 数据库持久化 | 云盘 CSI + VolumeSnapshot 定期备份 |
| 对象存储访问 | 通过 IAM 角色 / Workload Identity，不硬编码 AK/SK |
| 公网入口 | 云 LB + ExternalDNS + cert-manager |
| 敏感配置 | External Secrets Operator 统一管理 |
| 多 AZ 存储 | CSI `WaitForFirstConsumer` 确保 Pod 和卷在同一 AZ |

---

## 第二十六章 Sidecar 模式

- 什么是 Sidecar
- 常见场景
- 日志收集 Sidecar 实战
- 配置热更新 Sidecar
- Sidecar 容器（Kubernetes 1.28+ 原生支持）

### 1 什么是 Sidecar 模式

Sidecar（边车）是一种容器设计模式：在主应用容器旁运行一个辅助容器，两者共享 Pod 的**网络、存储和生命周期**。

```
┌──────────────────────────┐
│          Pod             │
│  ┌──────────┐ ┌────────┐│
│  │ 主容器    │ │Sidecar ││
│  │(app)     │ │(辅助)  ││
│  └──────────┘ └────────┘│
│         ▲           ▲    │
│   共享 Network / Storage │
│   (可选 PID namespace)   │
└──────────────────────────┘
```

**共享机制详解**：

| 命名空间 | 默认行为 | 控制字段 |
|----------|----------|----------|
| **Network** | 始终共享（同一 Pod 内 localhost 可达） | 不可关闭 |
| **Storage** | 通过 `volumes` + `volumeMounts` 显式共享 | 按需声明 |
| **PID** | **默认不共享** | `spec.shareProcessNamespace: true` |
| **IPC** | 默认共享 | `spec.hostIPC: false` 可关闭 |

> **PID 共享的作用**：Sidecar 需要查看主容器进程（如 Promtail 监控主容器的日志文件位置、APM agent 采集进程指标）时，必须设置 `shareProcessNamespace: true`，否则 Sidecar 看不到主容器进程。

```yaml
# 需要 PID 共享的场景
spec:
  shareProcessNamespace: true   # Sidecar 可通过 /proc 看到主容器进程
  containers:
    - name: app
      image: myapp
    - name: monitoring-agent     # 需要监控主容器进程
      image: datadog/agent
```

### 2 常见场景

| 场景 | Sidecar 作用 |
|------|-------------|
| **日志收集** | 读取主容器日志文件，发送到集中日志平台 |
| **监控代理** | Prometheus exporter、APM agent |
| **配置热更新** | 监听 ConfigMap 变化，reload 主容器 |
| **服务网格代理** | Istio Envoy / Linkerd proxy（透明注入流量代理） |
| **安全代理** | 数据库加密代理、认证 Sidecar |
| **缓存预热** | 启动时从远程拉取数据到本地缓存 |

### 3 日志收集 Sidecar 实战

```
主容器写日志到共享 emptyDir → Sidecar 读取并推送 Loki/ES
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-log-sidecar
spec:
  containers:
    # 主应用容器
    - name: app
      image: myapp:latest
      volumeMounts:
        - name: logs
          mountPath: /var/log/app
    # Sidecar 日志收集容器
    - name: log-shipper
      image: grafana/promtail:latest
      args:
        - -config.file=/etc/promtail/config.yml
        - -client.url=http://loki.logging.svc:3100/loki/api/v1/push
      volumeMounts:
        - name: logs
          mountPath: /var/log/app
          readOnly: true
        - name: promtail-config
          mountPath: /etc/promtail
  volumes:
    - name: logs
      emptyDir: {}
    - name: promtail-config
      configMap:
        name: promtail-config
```

### 4 配置热更新 Sidecar

ConfigMap 更新后，Sidecar 自动通知主容器 reload（无需重启 Pod）：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx-auto-reload
spec:
  containers:
    # 主容器 — Nginx
    - name: nginx
      image: nginx:1.23
      volumeMounts:
        - name: nginx-config
          mountPath: /etc/nginx/conf.d
    # Sidecar — 监听配置变化并调用 nginx -s reload
    - name: config-reloader
      image: nginx:1.23
      command:
        - /bin/sh
        - -c
        - |
          apt-get update && apt-get install -y inotify-tools
          while true; do
            inotifywait -e modify,create,delete -r /etc/nginx/conf.d && \
            nginx -s reload
          done
      volumeMounts:
        - name: nginx-config
          mountPath: /etc/nginx/conf.d
        - name: nginx-pid
          mountPath: /var/run
  volumes:
    - name: nginx-config
      configMap:
        name: nginx-conf
    - name: nginx-pid
      emptyDir: {}
```

> **注意**：Kubernetes 1.21+ 支持 `immutable` ConfigMap，但更新 ConfigMap 后 symlink 方式挂载的文件默认不更新（需配合 `configmap-reloader` 工具）。

### 5 Sidecar 容器（Kubernetes 1.28+ 原生支持）

从 Kubernetes 1.28 开始（`SidecarContainers` feature gate 默认启用），原生支持 Sidecar 容器。Sidecar 容器在 Init Containers 基础上增加了 `restartPolicy: Always`，保证其与主容器同生命周期：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: native-sidecar
spec:
  initContainers:
    # Native Sidecar — InitContainer 设为 Always 重启策略
    - name: envoy-proxy
      image: envoyproxy/envoy:v1.28
      restartPolicy: Always        # 关键：标记为 Sidecar
      volumeMounts:
        - name: envoy-config
          mountPath: /etc/envoy
    # 普通 Init Container — 启动前运行一次
    - name: setup
      image: busybox
      command: ["sh", "-c", "echo 'init done'"]
  containers:
    # 主容器
    - name: app
      image: myapp:latest
  volumes:
    - name: envoy-config
      configMap:
        name: envoy-conf
```

**原生 Sidecar 的优势**：

| 特性 | 传统 Sidecar | 原生 Sidecar (1.28+) |
|------|-------------|----------------------|
| 启动顺序 | 与主容器并发 | InitContainers 跑完 → Sidecar → 主容器 |
| 关闭顺序 | 并发 | 先停主容器 → 等待 terminationGracePeriod → 再停 Sidecar |
| 探针支持 | 全支持 | 全支持 |
| Job 支持 | 不支持 | 支持（主容器结束后 Sidecar 自动退出） |

---

## 第二十七章 生产环境网络架构

- 整体网络拓扑
- CNI 插件选型与对比
- 服务网格（Service Mesh）
- 多集群网络
- 生产网络排障工具

### 1 生产环境网络拓扑全景

```
                              Internet
                                 │
                          ┌──────▼──────┐
                          │  WAF / CDN  │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │ 云负载均衡   │ (CLB/NLB/ALB)
                          │ + TLS 卸载   │
                          └──────┬──────┘
                                 │
                    ┌────────────┴────────────┐
                    │    Kubernetes Cluster    │
                    │                         │
                    │  ┌───────────────────┐  │
                    │  │ Ingress Controller│  │
                    │  │ (Nginx/Traefik)   │  │
                    │  └────────┬──────────┘  │
                    │           │              │
                    │  ┌────────▼──────────┐  │
                    │  │  Service (ClusterIP)│ │
                    │  └────────┬──────────┘  │
                    │           │              │
                    │  ┌────────▼──────────┐  │
                    │  │       Pods        │  │
                    │  │  ┌────┐ ┌──────┐  │  │
                    │  │  │app │ │sidecar│  │  │
                    │  │  └────┘ └──────┘  │  │
                    │  └───────────────────┘  │
                    │                         │
                    │  ┌───────────────────┐  │
                    │  │  CNI 网络平面     │  │
                    │  │  (Calico/Cilium)  │  │
                    │  └───────────────────┘  │
                    └─────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │      外部服务            │
                    │  DB / Redis / MQ / S3   │
                    └─────────────────────────┘
```

### 2 CNI 插件选型

| 插件 | 性能 | NetworkPolicy | eBPF | 加密 | 适用场景 |
|------|------|:---:|:---:|:---:|----------|
| **Flannel** | 中 | ❌ | ❌ | ❌ | 学习/开发环境 |
| **Calico** | 高 | ✅ | ✅ | ✅ (WireGuard) | 通用生产环境首选 |
| **Cilium** | 极高 | ✅ | ✅ (深度) | ✅ | 大规模 + 可观测性需求 |
| **Weave** | 中 | ✅ | ❌ | ✅ | 中小规模，简单场景 |
| **Kube-OVN** | 高 | ✅ | ✅ | ✅ | OpenStack/虚拟化环境 |

#### 2.1 Calico 安装

```shell
# 通过 tigera operator 安装
$ kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.0/manifests/tigera-operator.yaml
$ kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.0/manifests/custom-resources.yaml
```

#### 2.2 Calico NetworkPolicy 示例

```yaml
# Calico 的 NetworkPolicy 比 K8s 原生更强大
apiVersion: projectcalico.org/v3
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: prod
spec:
  selector: app == 'backend'
  ingress:
    - action: Allow
      source:
        selector: app == 'frontend'
      destination:
        ports: [8080]
    - action: Allow
      source:
        nets: [10.0.0.0/8]     # 办公网段
      destination:
        ports: [8080]
    - action: Log
    - action: Deny
```

#### 2.3 Cilium 的 Hubble 可观测性

Cilium 内置 Hubble，提供流量可视化：

```shell
# 安装 Cilium + Hubble
$ helm install cilium cilium/cilium \
    --namespace kube-system \
    --set hubble.relay.enabled=true \
    --set hubble.ui.enabled=true

# 访问 Hubble UI
$ cilium hubble ui

# 查看实时流量
$ cilium hubble observe
```

```
Hubble 提供：
  - 服务依赖图：哪些 Pod 在互相通信
  - 流量监控：实时查看 HTTP/gRPC/Kafka 调用
  - 网络策略验证：检查规则是否生效
  - 安全审计：记录所有被拒绝的连接
```

#### 2.4 CNI 插件内部原理

CNI（Container Network Interface）定义了容器运行时应如何配置网络的规范。每个 CNI 插件是一个可执行文件，由 kubelet（通过 CRI runtime）在 Pod 生命周期内调用。

```
┌──────────────────────────────────────────────────────────┐
│                    CNI 工作流程                           │
│                                                          │
│   kubelet                                                 │
│     │                                                     │
│     │ Pod 创建: ADD 命令                                  │
│     ▼                                                     │
│   ┌─────────────┐    ┌──────────┐    ┌──────────────┐   │
│   │ CNI Plugin  │───▶│ IPAM     │───▶│ 配置网络接口  │   │
│   │ (二进制)    │    │ 分配 IP   │    │ veth pair    │   │
│   └─────────────┘    └──────────┘    │ route/iptables│   │
│                                      └──────────────┘   │
│                                                          │
│     Pod 删除: DEL 命令 → 回收 IP → 清理网络接口          │
│                                                          │
│   CNI 配置文件: /etc/cni/net.d/*.conf                    │
│   CNI 插件路径: /opt/cni/bin/                             │
└──────────────────────────────────────────────────────────┘
```

**CNI 插件链（Chained Plugins）**：一个 CNI 配置文件可以调用多个插件，按顺序执行：

```json
{
  "cniVersion": "0.3.1",
  "name": "prod-network",
  "plugins": [
    {
      "type": "calico",       // 主插件：路由/BGP
      "ipam": { "type": "calico-ipam" }
    },
    {
      "type": "bandwidth",    // 辅助插件：限速
      "capabilities": { "bandwidth": true }
    },
    {
      "type": "portmap"       // 辅助插件：HostPort 支持
    }
  ]
}
```

**CNI 核心操作（ADD / DEL / CHECK / VERSION）**：

| 操作 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| **ADD** | Pod 创建 | 容器 NS 路径、网络配置 JSON | IP 分配结果、路由/DNS 配置 |
| **DEL** | Pod 删除 | 同上 | 无（清理网络资源） |
| **CHECK** | 定期/手动检查 | 同上 | 无或错误（网络是否正常） |
| **VERSION** | 版本协商 | 无 | 插件支持的 CNI 版本 |

**主要 CNI 数据平面比较**：

| 插件 | 数据平面 | IPAM | 网络模型 | 典型场景 |
|------|----------|------|----------|----------|
| **Flannel** | vxlan / host-gw | host-local | Overlay | 简单部署 |
| **Calico** | BGP / vxlan / IPIP | calico-ipam | L3 路由 | 通用生产 |
| **Cilium** | eBPF | cluster-pool / ENI | eBPF+Overlay | 高性能+可观测 |
| **Kube-OVN** | vxlan / geneve | ovn-ipam | SDN | 虚拟化/OpenStack |

**CNI 故障排查流程**：

```shell
# 1. 查看 CNI 配置文件
$ ls /etc/cni/net.d/

# 2. 查看 kubelet CNI 相关日志
$ journalctl -u kubelet | grep -i cni

# 3. 从节点上手动测试 CNI 插件
$ export CNI_COMMAND=ADD
$ export CNI_CONTAINERID=$(docker ps -q | head -1)
$ export CNI_NETNS=/proc/$(docker inspect -f '{{.State.Pid}}' $CNI_CONTAINERID)/ns/net
$ export CNI_IFNAME=eth0
$ export CNI_PATH=/opt/cni/bin
$ cat /etc/cni/net.d/10-calico.conflist | /opt/cni/bin/calico

# 4. 检查 CNI IPAM 分配情况
$ kubectl get ippools.crd.projectcalico.org -A
$ kubectl get ipamblocks.crd.projectcalico.org -A
```

**生产 CNI 选型建议**：

```
□ 小规模（<50 节点）：Calico vxlan 模式，部署简单
□ 中大规模（50~500 节点）：Calico BGP 模式，无 Overlay 开销
□ 大规模（>500 节点）+ 网络可观测性需求：Cilium eBPF
□ 游戏/低延迟场景：VPC-CNI（云原生 ENI 直通）+ Cilium
□ 自建机房：Calico BGP + MetalLB
```

#### 2.5 Pod 间网络通信底层原理（面试深度）

> **面试常见问题**："两个 Pod 之间网络是怎么通的？" 或 "Pod A 在 Node1，Pod B 在 Node2，TCP 包怎么过去的？"
> 以下从内核层面的 veth pair、Linux Bridge、路由表、VXLAN 封包逐步拆解。

##### 一、K8s 网络模型的三条铁律

```
1. 每个 Pod 拥有一个独立 IP（集群内唯一，没有 NAT，没有端口映射）
2. 同一节点上的 Pod 可以直接通信（通过 Pod IP + CNI 网桥）
3. 跨节点的 Pod 可以直接通信（通过 Pod IP，依赖 CNI 插件做路由/隧道）

实现这三点是 CNI 插件的责任，K8s 本身只管分配 IP。
```

##### 二、同节点 Pod 通信：veth pair + cni0 bridge

```

┌─────────────── Node1 ───────────────┐
│                                     │
│  ┌──────────┐       ┌──────────┐    │
│  │  Pod A   │       │  Pod B   │    │
│  │ eth0     │       │ eth0     │    │
│  │10.0.1.10│       │10.0.1.20│    │
│  └────┬─────┘       └────┬─────┘    │
│       │                  │          │
│   veth pair           veth pair     │
│       │                  │          │
│  ┌────┴──────────────────┴─────┐    │
│  │       cni0 (bridge)         │    │
│  │       10.0.1.1              │    │
│  └─────────────────────────────┘    │
│              │                       │
│         eth0 (物理网卡)              │
│         192.168.1.10                │
└─────────────────────────────────────┘
```

**veth pair（虚拟网线）**：

```
veth pair = 一对虚拟网络接口，像一根网线的两端

端 A：在 Pod 的 network namespace 里 → 显示为 Pod 内的 eth0
端 B：在宿主机的 root namespace 里    → 显示为 vethXXXXX

工作机制：Pod 进程通过 eth0 发出的任何字节，
          直接从对端 vethXXXXX 出来，进入宿主机协议栈。
          没有 NAT、没有封包、就是内核内存拷贝。
```

验证：

```shell
# Pod 里看
$ kubectl exec pod-a -- ip addr show eth0
eth0: 10.0.1.10/32

# 宿主机上看 veth 对端（iflink 接口索引关联）
$ kubectl exec pod-a -- cat /sys/class/net/eth0/iflink
3
$ ip link show | grep "^3:"
3: vethabc123@if4: <BROADCAST> ...
# vethabc123 就是 Pod eth0 在宿主机的对端
```

**cni0 bridge（Linux Bridge 虚拟交换机）**：

```
cni0 是 CNI 插件在每个节点上创建的 Linux Bridge：
  - 同节点所有 Pod 的 veth 对端都插在 cni0 上
  - 工作在二层（MAC 地址学习 + 转发）
  - 类似一个透明的二层交换机

Pod A → Pod B（同节点）完整过程：

Step 1: Pod A 要访问 10.0.1.20
  → Pod A 路由表：目标在同一子网 → 发起 ARP 请求找 MAC 地址

Step 2: ARP 广播 "谁的 IP 是 10.0.1.20？"
  → eth0 → veth pair → cni0 bridge
  → cni0 广播到所有连接的 veth 接口

Step 3: Pod B 响应 "是我！MAC=aa:bb:cc:dd:ee:ff"
  → Pod A 拿到 MAC → 二层帧头发送

Step 4: 帧进入 cni0 → cni0 查 MAC 表：
  "aa:bb:cc:dd:ee:ff 在 vethB 口" → 从 vethB 转发 → 进入 Pod B

全程 Pod IP 不变，纯二层交换。
```

##### 三、跨节点 Pod 通信：三大方案对比

```
┌──────────── Node1 ────────────┐     ┌──────────── Node2 ────────────┐
│ Pod A (10.0.1.10)            │     │ Pod B (10.0.2.20)             │
│ eth0 → veth → cni0            │     │ eth0 ← veth ← cni0            │
│          │                    │     │          │                    │
│    eth0 (物理)                │     │    eth0 (物理)                │
│    192.168.1.1               │     │    192.168.2.1               │
└──────────┬───────────────────┘     └──────────┬────────────────────┘
           │                                    │
           └────────── 物理网络 ─────────────────┘
```

**问题**：Node1 只知道本节点的 Pod 网段 `10.0.1.0/24`，怎么知道 `10.0.2.20` 在 Node2 上？这取决于 CNI 插件的做法：

**方案 A — 路由模式（Calico BGP，无封装）**：

```
核心思想：节点互相宣告各自 Pod 网段，做完路由裸 IP 转发。

Calico 在每个节点上跑 bird（BGP daemon），互相 BGP 宣告：

  Node1 bird: "我有 10.0.1.0/24，下一跳是我 192.168.1.1"
  Node2 bird: "我有 10.0.2.0/24，下一跳是我 192.168.2.1"

节点路由表（BGP 自动写入）：
  Node1: 10.0.2.0/24 via 192.168.2.1  ← BGP 学到的！
  Node2: 10.0.1.0/24 via 192.168.1.1

Pod A → Pod B 流程：
Step 1: Pod A 发包，目标 10.0.2.20
  → 查路由表 → 命中 10.0.2.0/24 via 192.168.2.1

Step 2: Node1 物理网卡发出，源 IP = 10.0.1.10（原样！），目标 IP = 10.0.2.20（原样！）
  → 二层目标 MAC = Node2 物理 MAC（ARP 获取）

Step 3: 物理网络按 192.168.2.1 转发到 Node2

Step 4: Node2 收到 → 查路由表 → 10.0.2.0/24 dev cni0
  → 从 cni0 → veth → Pod B

全程 Pod IP 没被改过（无 NAT、无封装），性能最优（~1% 损耗）。
要求：物理网络能路由 Pod IP。云上 VPC 通常不认识 Pod IP → 不适用。
```

**方案 B — Overlay 封包模式（Flannel VXLAN / Calico IPIP）**：

```
核心思想：物理网络不认识 Pod IP → 把 Pod IP 包"装进"Node IP 包里

VXLAN 封装原理：
  原始包（Pod A 发）：
  ┌──────────────────────────────────────────────┐
  │ 源IP:10.0.1.10 │ 目标IP:10.0.2.20 │ TCP数据 │
  └──────────────────────────────────────────────┘

  封装后在物理网络上传输：
  ┌──────────────────────────────────────────────────────────────────┐
  │ 外层IP:192.168.1.1→192.168.2.1 │ UDP(8472) │ VXLAN头 │ 原始IP包 │
  └──────────────────────────────────────────────────────────────────┘
  物理网络只看到 Node IP（192.168.x.x），完全不知道里面有 Pod 包

VXLAN 完整流程：
Step 1: Pod A 发包 → cni0 bridge → Node1 主机协议栈
Step 2: Node1 查路由：10.0.2.0/24 → flannel.1（VXLAN 设备）
Step 3: flannel.1 查 FDB 表："10.0.2.0/24 的 VTEP 是 Node2 IP 192.168.2.1"
  → 给原始包加外层 UDP + 外层 IP + VXLAN 头
Step 4: 封装后的包从 Node1 物理网卡发出 → 物理网络正常转发
Step 5: Node2 收到 UDP 端口 8472 → 内核 VXLAN 模块解封装 → 露出原始包
Step 6: Node2 路由原始包 → cni0 → Pod B

IPIP 模式（Calico 的另一选择，比 VXLAN 轻量）：
  ┌──────────────────┬────────────────────┐
  │ 外层 IP 头        │ 原始 IP 包（完整）  │  ← 只多一层 IP 头，无 UDP/VXLAN
  └──────────────────┴────────────────────┘
  协议号 4，损耗约 3-5%（vs VXLAN 的 5-10%）
```

**方案 C — eBPF 直通（Cilium）**：

```
核心思想：用 eBPF 程序绕开内核协议栈，在网卡驱动层直接转发

传统路径（iptables/kube-proxy）：
  Pod A → veth → cni0 → host 协议栈（iptables 逐条匹配规则 O(n)）
  → 路由决策 → 物理网卡 → 网络 → Node2 → 反过来再走一遍

Cilium eBPF 路径：
  Pod A → veth → eBPF 直接查 Map（O(1) 查表）
  → "目标 10.0.2.20 → 下一跳是 Node2 → 直发物理网卡"
  
  跳过了：
    ✗ cni0 bridge（不需要二层桥）
    ✗ iptables（不需要逐条 O(n) 匹配）
    ✗ conntrack（不需要连接跟踪）

性能：转发延迟约 50μs（vs iptables 约 500μs）
```

**三种方案性能对比**：

| 方案 | 原理 | 性能损耗 | 适用场景 |
|------|------|----------|----------|
| 路由 (Calico BGP) | IP 路由，无封装 | ~1% | 自建机房，物理网络可路由 Pod IP |
| IPIP (Calico) | IP-in-IP 隧道 | ~3-5% | 云上 VPC，不需要 BGP |
| VXLAN (Flannel) | L2 over UDP 隧道 | ~5-10% | 云上 VPC，需要 L2 连通性 |
| eBPF (Cilium) | 内核旁路直接转发 | ~0% | 内核 ≥ 5.4，高性能场景 |

##### 四、NAT 在 Pod 网络中的位置

**NAT（Network Address Translation）= 地址转换**，把 IP 包的源或目标 IP 改掉。

```
Pod 网络中 NAT 的使用场景：

✅ 有 NAT 的地方：
  1. Pod 访问外网 → 节点做 SNAT，Pod IP(10.0.1.10) → 节点 IP(192.168.1.1)
     否则外部服务器不认识 10.0.x.x（私有 IP）
  2. Service ClusterIP → Pod IP → kube-proxy 做 DNAT

❌ 没有 NAT 的地方：
  1. Pod → Pod（同节点或跨节点）→ 直接 IP 通信，不做 NAT
  2. Calico BGP 路由模式 → Pod IP 全链路不变
```

##### 五、BGP 协议在 Calico 中的作用

```
BGP（Border Gateway Protocol）= 路由广播协议

互联网上的 BGP：运营商路由器互相告知"百度 IP 段走这条路线"

Calico 中的 BGP：节点互相告知"我的 Pod 网段走我这个 IP"

没有 BGP → 每新增节点手动配路由（ip route add ...），Pod 一变就乱
有 BGP → 节点自动广播，所有节点自动学习，全自动
```

##### 六、面试速记答案

```
问："两个 Pod 之间网络怎么通的？"

答：
同节点 → veth pair 连接 Pod NS 和宿主机 cni0 bridge，二层 MAC 转发。

跨节点 → 取决于 CNI：
  - Calico BGP：节点 BGP 宣告 Pod 网段，裸 IP 路由，不封包，性能最好
  - Flannel VXLAN：Pod IP 包封装进 Node IP 的 UDP，物理网络只看到 Node IP
  - Cilium eBPF：网卡驱动层直接转发，旁路内核，延迟最低

K8s 只定义"每个 Pod 独立 IP"，具体怎么通是 CNI 插件的责任。
```

### 3 服务网格（Service Mesh）概述

Service Mesh 将网络通信能力下沉到 Sidecar 代理层，应用无需感知。

```
┌──────────────────────────────────────────┐
│              Service Mesh                 │
│                                          │
│  ┌──────────┐         ┌──────────┐      │
│  │ App      │◄───────▶│ App      │      │
│  │ Container│  mTLS   │ Container│      │
│  ├──────────┤         ├──────────┤      │
│  │ Envoy    │◄───────▶│ Envoy    │      │
│  │ Sidecar  │   L7    │ Sidecar  │      │
│  └──────────┘         └──────────┘      │
│       ▲                     ▲            │
│       │   控制平面          │            │
│  ┌────┴─────────────────────┴────┐      │
│  │  Istio / Linkerd Control Plane│      │
│  └───────────────────────────────┘      │
└──────────────────────────────────────────┘
```

#### 3.1 Istio 核心能力

| 能力 | 说明 |
|------|------|
| **mTLS** | Pod 间自动加密通信 |
| **流量管理** | 金丝雀、熔断、超时、重试 |
| **可观测性** | 自动生成 L7 指标 + 分布式追踪 |
| **访问控制** | L4/L7 授权策略 |

#### 3.2 Istio 安装

```shell
# 下载 Istio
$ curl -L https://istio.io/downloadIstio | sh -
$ cd istio-1.20.0
$ export PATH=$PWD/bin:$PATH

# 安装（默认配置）
$ istioctl install --set profile=default -y

# 启用 Sidecar 自动注入
$ kubectl label namespace default istio-injection=enabled
```

#### 3.3 Istio 流量管理示例

```yaml
# VirtualService: 金丝雀发布（90% v1, 10% v2）
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: app
spec:
  hosts:
    - app
  http:
    - route:
        - destination:
            host: app
            subset: v1
          weight: 90
        - destination:
            host: app
            subset: v2
          weight: 10
---
# DestinationRule: 定义子集
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: app
spec:
  host: app
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
```

#### 3.4 Istio AuthorizationPolicy

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-frontend
  namespace: prod
spec:
  selector:
    matchLabels:
      app: backend
  action: ALLOW
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/prod/sa/frontend-sa"]
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/*"]
```

#### 3.5 Istio Operator 生产级安装

`istioctl install` 适合开发和调试，生产环境推荐使用 **IstioOperator CR** 声明式管理 Istio 安装。Istio Operator 是 K8s Operator 模式的具体应用，通过 CR 描述 Istio 集群的期望状态。

```
┌──────────────────────────────────────────────────────────┐
│              Istio Operator 架构                          │
│                                                          │
│  kubectl apply -f istio-operator.yaml                    │
│        │                                                 │
│        ▼                                                 │
│  ┌──────────────────────┐                               │
│  │ IstioOperator CR     │  ← 用户定义期望状态             │
│  │ (spec.profile/components) │                           │
│  └──────────┬───────────┘                               │
│             │ watch                                       │
│             ▼                                             │
│  ┌──────────────────────┐                               │
│  │ Istio Operator       │  ← 控制循环（Controller）       │
│  │ (Deployment)         │     调谐：实际 → 期望           │
│  └──────────┬───────────┘                               │
│             │ 创建/更新                                   │
│             ▼                                             │
│  ┌──────────────────────────────────────┐               │
│  │ Istiod (Control Plane)               │               │
│  │ Discovery + CA + xDS Server          │               │
│  │ ┌──────────┐ ┌──────────┐           │               │
│  │ │Pilot     │ │Citadel   │ ...       │               │
│  │ └──────────┘ └──────────┘           │               │
│  └──────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────┘
```

**步骤 1：安装 Istio Operator**

```shell
# 使用 istioctl 安装 Operator（仅一次）
$ istioctl operator init
# 或通过 Helm:
$ helm install istio-operator manifests/charts/istio-operator
```

**步骤 2：编写 IstioOperator CR**

```yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: production-istio
  namespace: istio-system
spec:
  # 基础配置 Profile：default / demo / minimal / empty
  profile: default

  # 全局配置
  meshConfig:
    accessLogFile: /dev/stdout
    accessLogEncoding: JSON
    enableTracing: true
    # 可观测性后端
    defaultProviders:
      metrics:
        - prometheus
    # 信任域
    trustDomain: prod.internal

  # 组件配置（按需调整副本和资源）
  components:
    pilot:
      k8s:
        replicas: 2
        hpaSpec:
          minReplicas: 2
          maxReplicas: 10
          metrics:
            - type: Resource
              resource:
                name: cpu
                targetAverageUtilization: 80
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
          limits:
            cpu: 2
            memory: 4Gi
        # Pod 反亲和：分散到不同节点
        affinity:
          podAntiAffinity:
            requiredDuringSchedulingIgnoredDuringExecution:
              - labelSelector:
                  matchLabels:
                    istio: pilot
                topologyKey: kubernetes.io/hostname

    # Ingress Gateway
    ingressGateways:
      - name: istio-ingressgateway
        enabled: true
        k8s:
          replicas: 2
          service:
            type: LoadBalancer
            ports:
              - port: 80
                targetPort: 8080
                name: http2
              - port: 443
                targetPort: 8443
                name: https
              - port: 15443
                targetPort: 15443
                name: tls
          # HPA 自动伸缩
          hpaSpec:
            minReplicas: 2
            maxReplicas: 5
            metrics:
              - type: Resource
                resource:
                  name: cpu
                  targetAverageUtilization: 80

    # Egress Gateway（出站流量管控）
    egressGateways:
      - name: istio-egressgateway
        enabled: true
        k8s:
          replicas: 1

  # Sidecar 注入配置
  values:
    sidecarInjectorWebhook:
      enableNamespacesByDefault: false   # 默认不注入，按 namespace 标签控制
    global:
      proxy:
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 2
            memory: 512Mi
        # 日志级别
        logLevel: warning
        # 接入日志
        accessLogFile: /dev/stdout
        accessLogEncoding: JSON
```

**步骤 3：应用 IstioOperator**

```shell
# 预览变更（dry-run）
$ istioctl analyze --operator-file istio-operator.yaml

# 应用配置
$ kubectl apply -f istio-operator.yaml

# 查看 Operator 状态
$ kubectl get istiooperator -n istio-system
$ istioctl version
$ istioctl proxy-status                    # 查看所有 Sidecar 状态
```

**IstioOperator vs istioctl install 对比**：

| 特性 | `istioctl install` | IstioOperator CR |
|------|-------------------|-------------------|
| 声明式 | ❌（命令行传参） | ✅（YAML CR） |
| GitOps 友好 | ❌（脚本化） | ✅（CR 可直接入 Git） |
| 自动调谐 | ❌（手动更新） | ✅（Operator 持续调谐） |
| 增量变更 | 需要完整重装 | 修改 CR 即可 |
| 回滚 | 手动卸载重装 | 修改 CR 或 Git revert |
| 多版本共存 | ❌ | ✅（canary upgrade） |

**金丝雀升级（Canary Upgrade）**：

```yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: canary-1-21
  namespace: istio-system
spec:
  revision: 1-21                 # 版本标签
  profile: default
  components:
    pilot:
      k8s:
        env:
          - name: PILOT_SCOPE_NAMESPACES
            value: "game-preview"    # 仅影响指定命名空间
```

```shell
# 部署新版本（不影响现有流量）
$ kubectl apply -f canary-1-21.yaml

# 将测试 namespace 切换到新版本
$ kubectl label namespace game-preview istio.io/rev=1-21

# 验证后全量迁移 → 删除旧版本 IstioOperator CR
```

### 4 多集群网络

| 方案 | 说明 | 适用场景 |
|------|------|----------|
| **KubeFed v2** | 官方联邦方案，跨集群同步资源 | 多区域部署 |
| **Istio Multi-Cluster** | Service Mesh 层跨集群通信 | 已有 Istio |
| **Cilium Cluster Mesh** | CNI 层跨集群 Pod 直通 | 低延迟需求 |
| **Submariner** | 跨集群网络直连 | CNI 无关，简单部署 |

### 5 生产网络排障工具

```shell
# 1. 测试 Pod 到 Pod 连通性
$ kubectl run test --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash
bash# ping <pod-ip>
bash# curl -v http://<service>.<namespace>:<port>

# 2. DNS 排查
$ kubectl run test --image=nicolaka/netshoot --rm -it --restart=Never -- \
    nslookup kubernetes.default
$ kubectl run test --image=nicolaka/netshoot --rm -it --restart=Never -- \
    dig +short my-service.my-namespace.svc.cluster.local
```

**netshoot 容器包含的工具**：`curl`, `wget`, `tcpdump`, `nslookup`, `dig`, `iperf`, `netstat`, `ip`, `mtr` 等。

```shell
# 3. 抓包分析
$ kubectl exec -it debug-pod -- tcpdump -i eth0 -w /tmp/capture.pcap port 80
$ kubectl cp debug-pod:/tmp/capture.pcap ./capture.pcap

# 4. 检测 NetworkPolicy 是否阻止
$ kubectl get networkpolicy -A
$ kubectl describe networkpolicy <name> -n <ns>

# 5. Service 负载均衡测试
$ for i in {1..10}; do
    kubectl run curl-$i --image=curlimages/curl --rm -it --restart=Never -- \
        curl -s http://my-service 2>/dev/null | grep -o "hostname:.*" &
  done

# 6. 节点间网络延迟
$ kubectl run iperf-server --image=networkstatic/iperf3 --port=5201 -- iperf3 -s
$ kubectl run iperf-client --image=networkstatic/iperf3 --rm -it --restart=Never -- \
    iperf3 -c <iperf-server-pod-ip>
```

### 6 生产网络架构建议

```
┌────────────────────────────────────────────────────┐
│         生产环境网络 checklist                       │
├────────────────────────────────────────────────────┤
│ □ CNI 选 Calico/Cilium（必须支持 NetworkPolicy）    │
│ □ NetworkPolicy 全局拒绝 + 按需放行                  │
│ □ Ingress Controller 前面放置云 LB + WAF            │
│ □ 内部服务使用 ClusterIP + CoreDNS 服务发现          │
│ □ 敏感服务间启用 mTLS（Istio/Linkerd 或 Cilium）    │
│ □ 外部依赖（DB/Redis）通过 ExternalName Service 访问 │
│ □ 集群内 DNS 缓存（node-local-dns）减少延迟          │
│ □ 监控 DNS 延迟和失败率（CoreDNS metrics）           │
│ □ 网络可观测性（Hubble 或 Weave Scope）              │
│ □ 定期网络故障演练（chaos-mesh / chaosblade）        │
└────────────────────────────────────────────────────┘
```

---

## 第二十八章 ServiceMonitor & PodMonitor 声明式指标采集

- Prometheus Operator 核心 CRD
- ServiceMonitor 完整配置
- PodMonitor 完整配置
- Relabeling 与 Metric Relabeling
- 多服务自动发现
- 采集端点认证（TLS / BearerToken）
- 生产案例

### 1 为什么需要 ServiceMonitor

传统方式需要在 Prometheus 配置文件 `scrape_configs` 中手动写采集目标：

```yaml
# ❌ 传统方式：每次新增服务都要改 Prometheus 配置，重启 Prometheus
scrape_configs:
  - job_name: 'my-app'
    static_configs:
      - targets: ['10.0.1.5:8080', '10.0.1.6:8080']
```

**ServiceMonitor** 将采集规则从 Prometheus 配置中解耦，变成 Kubernetes 原生资源，由**应用开发者自己声明**：

```yaml
# ✅ 声明式：应用开发者创建 ServiceMonitor，Prometheus 自动发现
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-app
spec:
  selector:
    matchLabels:
      app: my-app
  endpoints:
    - port: metrics
      interval: 30s
```

```
┌──────────────────────────────────────────────────────┐
│              Prometheus Operator                      │
│                                                      │
│  ┌──────────────┐    watch     ┌────────────────┐   │
│  │  Prometheus  │◄────────────│ ServiceMonitor  │   │
│  │   CR 实例     │             │ / PodMonitor    │   │
│  └──────┬───────┘             │ / Probe CRD    │   │
│         │ 自动更新配置         └───────┬────────┘   │
│         ▼                             │ 管理者       │
│  ┌──────────────┐              ┌──────▼─────────┐  │
│  │  Prometheus  │── scrape ──▶│     Pods        │  │
│  │    Pod       │              └────────────────┘  │
│  └──────────────┘                                   │
└──────────────────────────────────────────────────────┘
```

### 2 Prometheus Operator CRD 全景与选择器匹配机制

**Prometheus CR 如何发现 ServiceMonitor**：

```yaml
# Prometheus CR 定义了"接受哪些 ServiceMonitor"
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: k8s
  namespace: monitoring
spec:
  serviceMonitorSelector:
    matchLabels:
      release: prometheus      # ← 只有带此 label 的 ServiceMonitor 才会被选中
  podMonitorSelector:           # PodMonitor 同理
    matchLabels:
      release: prometheus
```

```
Prometheus CR.serviceMonitorSelector.matchLabels
          ↓ 匹配
ServiceMonitor.metadata.labels    ← 必须包含 "release: prometheus"
          ↓ 发现
Service.selector                  ← 找到 Service 对应的 Pod
          ↓ scrape
Pod IP:port
```

> **最常见故障**：ServiceMonitor 配置正确但 Target 不出现 → 检查 ServiceMonitor 的 labels 是否匹配 Prometheus CR 的 `serviceMonitorSelector`。

#### 2.1 匹配关系总结

| 步骤 | 说明 |
|------|------|
| 1. Prometheus CR → ServiceMonitor | 通过 `serviceMonitorSelector` label 匹配 |
| 2. ServiceMonitor → Service | 通过 `spec.selector` label 匹配 |
| 3. Service → Pod | 通过 `spec.selector` label 匹配 |
| 4. Prometheus → Pod | 使用 Pod IP + containerPort 直连采集 |

**CRD 全景表格**：

| CRD | 作用 | 管理者 |
|-----|------|--------|
| **Prometheus** | 定义 Prometheus 实例（副本数、存储、版本） | 集群管理员 |
| **ServiceMonitor** | 基于 Service 的采集目标 | 应用开发者 |
| **PodMonitor** | 直接基于 Pod 的采集目标（无需 Service） | 应用开发者 |
| **Probe** | 集群外目标的健康探测（blackbox exporter） | 应用开发者 |
| **PrometheusRule** | 告警和记录规则 | 应用开发者/运维 |
| **AlertmanagerConfig** | Alertmanager 路由配置 | 应用开发者 |

### 3 ServiceMonitor 完整字段解析

#### 3.1 最简示例

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nginx-monitor
  namespace: app-ns
  labels:
    release: prometheus          # 匹配 Prometheus CR 的 serviceMonitorSelector
spec:
  selector:
    matchLabels:
      app: nginx                 # 选择要监控的 Service
  endpoints:
    - port: metrics              # Service 中定义的 port name
      interval: 30s
```

#### 3.2 匹配关系

```
ServiceMonitor.selector.matchLabels
        ↓ 匹配
Service.metadata.labels
        ↓ 关联
Service.spec.selector
        ↓ 匹配
Pod.metadata.labels
        ↓ 获取
Pod.Status.PodIP + Service.spec.ports[].targetPort
        ↓
Prometheus 向 PodIP:targetPort 发起 scrape
```

> **关键**：Prometheus 直接采集 **Pod IP**，不经过 Service 虚拟 IP。Service 只用于服务发现。

#### 3.3 全部字段

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gamesvr-monitor
  namespace: game-prod
  labels:
    release: prometheus
    team: backend
spec:
  # === 目标选择 ===
  jobLabel: app                           # 用哪个 label 的值作为 Prometheus job 名称
  targetLabels:                           # 从 Service 传递哪些 label 到 target
    - app
    - version
  podTargetLabels:                        # 从 Pod 传递哪些 label 到 target
    - app
    - version
    - pod-template-hash
  selector:
    matchLabels:
      app: gamesvr
    matchExpressions:                     # 更灵活的选择器
      - key: env
        operator: In
        values:
          - prod
          - staging
  namespaceSelector:                      # 监控哪些命名空间的 Service
    matchNames:
      - game-prod
      - game-staging
    # any: true                           # 所有命名空间

  # === 端点配置 ===
  endpoints:
    - port: metrics                       # Service port name（推荐）或 port number
      interval: 30s                       # 采集间隔
      scrapeTimeout: 10s                  # 单次采集超时
      path: /metrics                      # 指标路径
      scheme: http                        # http 或 https
      params:                             # URL 查询参数
        format: ["prometheus"]
      # === 后端 TLS ===
      tlsConfig:
        insecureSkipVerify: false
        ca:
          secret:
            name: metrics-ca
            key: ca.crt
        cert:
          secret:
            name: metrics-client-cert
            key: tls.crt
        keySecret:
          name: metrics-client-cert
          key: tls.key
        serverName: metrics.gamesvr.svc
      # === Bearer Token 认证 ===
      bearerTokenSecret:
        name: metrics-token
        key: token
      # === Basic Auth ===
      basicAuth:
        username:
          name: metrics-auth
          key: username
        password:
          name: metrics-auth
          key: password
      # === 指标重标记（拉取前） ===
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_node_name]
          targetLabel: node
          replacement: $1
        - sourceLabels: [__meta_kubernetes_namespace]
          targetLabel: namespace
        - action: keep                     # 只采集特定条件的 target
          sourceLabels: [__meta_kubernetes_pod_label_version]
          regex: v[2-9]\..*               # 只采集 v2+ 版本
        - action: drop                     # 丢弃匹配的 target
          sourceLabels: [__meta_kubernetes_pod_label_canary]
          regex: "true"
        - action: labelmap                 # 自动将匹配的 label 前缀映射
          regex: __meta_kubernetes_pod_label_(.+)  # 所有 pod label → 去掉前缀
      # === 指标重标记（拉取后，推荐在此做） ===
      metricRelabelings:
        - action: drop                     # 丢弃不必要的高基数指标
          sourceLabels: [__name__]
          regex: 'http_request_duration_seconds_bucket'
        - action: keep                     # 只保留匹配的指标
          sourceLabels: [__name__]
          regex: 'go_.*|process_.*|http_.*'
        - action: labeldrop                # 删除指定 label
          regex: 'pod_template_hash|pod_uid'
        - action: labelkeep                # 只保留指定 label
          regex: 'namespace|pod|container'

  # === 采集端点的 target 数量限制 ===
  sampleLimit: 1000                        # 单次采集最大样本数
  targetLimit: 50                          # 最大 target 数
  labelLimit: 30                           # 单个 target 最大 label 数
  labelNameLengthLimit: 200                # label 名最大长度
  labelValueLengthLimit: 500               # label 值最大长度
```

### 4 自动发现元标签速查表

ServiceMonitor 自动注入以下元标签，可通过 `relabelings` 使用：

| 元标签 | 说明 | 示例值 |
|--------|------|--------|
| `__meta_kubernetes_namespace` | Pod 所在命名空间 | `game-prod` |
| `__meta_kubernetes_pod_name` | Pod 名称 | `gamesvr-5d8f9c7b6-x9k2m` |
| `__meta_kubernetes_pod_ip` | Pod IP | `10.244.3.15` |
| `__meta_kubernetes_pod_node_name` | 所在节点 | `k8s-node2` |
| `__meta_kubernetes_pod_label_<label>` | Pod 的每个 label | 自动注入 |
| `__meta_kubernetes_pod_annotation_<annotation>` | Pod 的每个 annotation | 自动注入 |
| `__meta_kubernetes_pod_container_name` | 容器名称 | `gamesvr` |
| `__meta_kubernetes_pod_container_port_name` | 容器端口名 | `metrics` |
| `__meta_kubernetes_pod_container_port_number` | 容器端口号 | `9090` |
| `__meta_kubernetes_pod_ready` | Pod 是否就绪 | `true` |
| `__meta_kubernetes_service_name` | Service 名称 | `gamesvr-svc` |
| `__meta_kubernetes_service_label_<label>` | Service 的每个 label | 自动注入 |

### 5 PodMonitor

当服务不需要 Service（如直接端点发现、Headless Service），使用 **PodMonitor** 直接从 Pod 采集：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: nats-monitor
  namespace: game-prod
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: nats
  # 不要求 Pod 有对应的 Service
  podMetricsEndpoints:
    - port: metrics                  # 容器 port name
      interval: 15s
      path: /metrics
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_name]
          targetLabel: instance
  namespaceSelector:
    matchNames:
      - game-prod
```

**ServiceMonitor vs PodMonitor**：

| 维度 | ServiceMonitor | PodMonitor |
|------|----------------|------------|
| 依赖 | Service 必须存在 | 直接选 Pod |
| 确定性 | 只采集 Ready Pod | 可能采集未就绪 Pod |
| 端口映射 | 通过 Service port name | 直接使用容器 port name |
| 适用场景 | 常规 HTTP/gRPC 服务 | Sidecar、Headless、NATS |

### 6 生产案例一：游戏服多端口采集

游戏服务通常有多个端口和多个 metric 路径：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gamesvr-full
  namespace: game-prod
  labels:
    release: prometheus
    team: game-backend
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: gamesvr
  endpoints:
    # 业务指标（Go/Java 应用）
    - port: metrics
      interval: 30s
      path: /metrics
      metricRelabelings:
        - action: keep
          sourceLabels: [__name__]
          regex: 'game_.*|go_.*|process_.*'
    # 运行时指标（NATS 客户端）
    - port: metrics
      interval: 30s
      path: /debug/vars
      metricRelabelings:
        - action: keep
          sourceLabels: [__name__]
          regex: 'nats_.*'
    # gRPC 健康检查
    - port: grpc-metrics
      interval: 60s
      path: /grpc.health.v1.Health/Check
```

### 7 生产案例二：Sidecar 指标采集

当应用通过 Sidecar（如 Envoy proxy、Promtail）暴露指标时：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: app-with-sidecar
  labels:
    app: backend
spec:
  selector:
    app: backend
  ports:
    - name: app-metrics
      port: 8080
      targetPort: 8080
    - name: sidecar-metrics
      port: 9090
      targetPort: 9090
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: backend-full
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app: backend
  endpoints:
    - port: app-metrics
      interval: 30s
      path: /metrics
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_container_name]
          regex: app
          action: keep           # 只从 app 容器采集此端口
    - port: sidecar-metrics
      interval: 30s
      path: /stats/prometheus
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_container_name]
          regex: envoy-sidecar
          action: keep           # 只从 envoy-sidecar 容器采集此端口
```

### 8 生产案例三：Stable / Canary 版本分离监控

游戏项目常见双版本发布（stable + canary），需要分别监控：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: combat-stable
  namespace: game-prod
  labels:
    release: prometheus
    track: stable
spec:
  selector:
    matchLabels:
      app: combat
      version: stable
  endpoints:
    - port: metrics
      interval: 30s
      relabelings:
        - targetLabel: version
          replacement: stable
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: combat-canary
  namespace: game-prod
  labels:
    release: prometheus
    track: canary
spec:
  selector:
    matchLabels:
      app: combat
      version: canary
  endpoints:
    - port: metrics
      interval: 15s        # 金丝雀版本采集更频繁
      relabelings:
        - targetLabel: version
          replacement: canary
```

```promql
# Grafana 对比查询
sum(rate(http_requests_total{version="stable"}[5m]))
  /
sum(rate(http_requests_total{version="canary"}[5m]))
```

### 9 生产案例四：多环境统一监控

使用 `namespaceSelector` + label filter 监控所有环境：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gamesvr-all-env
  namespace: monitoring
  labels:
    release: prometheus
spec:
  # 不限制命名空间，监控所有带 label 的 Service
  namespaceSelector:
    any: true
  selector:
    matchLabels:
      prometheus.io/scrape: "true"    # 约定：标记需要监控的服务
  endpoints:
    - port: metrics
      interval: 30s
      relabelings:
        # 用 namespace 作为 Prometheus 的 job 标签值
        - sourceLabels: [__meta_kubernetes_namespace]
          targetLabel: job
```

**应用侧只需要在 Service 上加 label**：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: gamesvr
  namespace: game-stable
  labels:
    app: gamesvr
    prometheus.io/scrape: "true"     # 自动加入采集
spec:
  ports:
    - name: metrics
      port: 8080
```

### 10 生产案例五：Calico / Cilium 等系统组件的 PodMonitor

部分系统组件没有传统 Service，用 PodMonitor：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: calico-node
  namespace: calico-system
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      k8s-app: calico-node
  podMetricsEndpoints:
    - port: metrics
      interval: 30s
      path: /metrics
      metricRelabelings:
        - action: keep
          sourceLabels: [__name__]
          regex: 'felix_.*|calico_.*'
```

### 11 高基数问题与性能优化

**常见问题**：Pod label 或 annotation 直接映射为 metric label 导致基数爆炸。

```yaml
# ❌ 危险：每个 Pod 的 uid 都作为 label，指标基数 = Pod 数量
relabelings:
  - action: labelmap
    regex: __meta_kubernetes_pod_label_(.+)

# ✅ 安全：只映射特定的 label
relabelings:
  - sourceLabels: [__meta_kubernetes_pod_label_app]
    targetLabel: app
  - sourceLabels: [__meta_kubernetes_pod_label_version]
    targetLabel: version

# ✅ 使用 metricRelabelings 在拉取后丢弃高基数 label（不影响 target 发现）
metricRelabelings:
  - action: labeldrop
    regex: 'pod_uid|container_id|pod_ip'
```

**性能保护参数**：

```yaml
endpoints:
  - port: metrics
    sampleLimit: 5000             # 单次采集最大 5000 条样本
    targetLimit: 100              # 单个 Service 最多 100 个 target
    labelLimit: 50
    labelValueLengthLimit: 1024
    bodySizeLimit: 10MB           # 响应体最大 10MB
```

### 12 完整健康检查链路

```
ServiceMonitor 声明 ─→ Prometheus 自动发现 ─→ 采集指标
     │
     ├─ PrometheusRule 定义告警规则
     │       │
     │       ▼
     │   AlertManager 路由告警 → 企业微信 / 钉钉 / Slack
     │
     └─ Grafana 仪表盘可视化
```

```yaml
# PrometheusRule: 告警规则
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gamesvr-alerts
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: gamesvr
      rules:
        - alert: GameServerHighErrorRate
          expr: |
            sum(rate(http_requests_total{app="gamesvr",status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total{app="gamesvr"}[5m]))
            > 0.05
          for: 5m
          labels:
            severity: critical
            team: game-backend
          annotations:
            summary: "gamesvr 错误率 > 5%"
            description: "namespace={{ $labels.namespace }}, 错误率={{ $value | humanizePercentage }}"
            runbook_url: "https://wiki.example.com/runbooks/gamesvr-error-rate"

        - alert: GameServerHighLatency
          expr: |
            histogram_quantile(0.99,
              rate(http_request_duration_seconds_bucket{app="gamesvr"}[5m])
            ) > 2
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "gamesvr P99 延迟 > 2s"
```

### 13 调试 ServiceMonitor

```shell
# 1. 确认 ServiceMonitor 已被 Prometheus 选中
$ kubectl get servicemonitor -n game-prod
$ kubectl describe servicemonitor gamesvr-monitor -n game-prod

# 2. 查看 Prometheus 的 Targets 页面
$ kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# 浏览器打开 http://localhost:9090/targets

# 3. 检查 Prometheus 日志
$ kubectl logs -n monitoring prometheus-prometheus-0 -c prometheus --tail=50 | grep "error"

# 4. 验证 target 的 relabel 结果
# Targets 页面 → 点击具体 target → 查看 "Discovered Labels" vs "Target Labels"

# 5. 查看 Prometheus CR 的 serviceMonitorSelector
$ kubectl get prometheus -n monitoring -o yaml | grep -A10 serviceMonitorSelector

# 6. 确认 Service 的 endpoints 不为空
$ kubectl get endpoints -n game-prod gamesvr-svc
NAME          ENDPOINTS                         AGE
gamesvr-svc   10.244.3.15:8080,10.244.5.22:8080 5d
```

### 14 常见问题速查

| 症状 | 原因 | 排查 |
|------|------|------|
| Target 不出现 | ServiceMonitor label 不匹配 Prometheus CR 的 `serviceMonitorSelector` | `kubectl describe prometheus` |
| Target 出现但 DOWN | 1. 端口不对 2. Pod 未就绪 3. 网络策略阻止 | `kubectl get endpoints <svc>`, 测试直连 Pod IP |
| 指标为空 | path 写错 | `curl http://<pod-ip>:<port>/metrics` |
| 采集超时 | Pod 响应慢或 `/metrics` 返回过大 | 加大 `scrapeTimeout`，优化应用指标 |
| 部分 Target 缺失 | `relabelings` 中有 `action: keep/drop` 误杀 | 检查 relabel 规则，先去掉所有 relabel 验证 |
| 新 Pod 采集不到 | Service selector 不匹配新 Pod label | `kubectl describe svc` 确认 selector |

---

## 第二十九章 腾讯云 TKE 生产实践

- TKE 集群类型与选型
- VPC-CNI 网络模式
- BCS 游戏工作负载（GameStatefulSet / HookTemplate / PortPool）
- CLB 集成（多线路 / 端口池 / 直通 Pod）
- CBS / CFS / COS 存储
- 节点池与弹性伸缩
- TCR 镜像仓库
- 蓝鲸监控集成
- 生产 Checklist

### 1 TKE 集群概述

腾讯云容器服务 TKE 提供两种集群模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **托管集群** | Master 由腾讯云托管，用户只管理 Worker 节点 | 99% 的生产场景（Panda / RAG 均使用此模式） |
| **独立集群** | 用户自行管理全部节点（含 Master） | 特殊合规需求 |

```
┌─────────────────────────────────────────────┐
│                TKE 托管集群                   │
│                                             │
│  ┌───────────────────────────────────────┐ │
│  │  腾讯云托管 Master（不可见）            │ │
│  │  etcd + apiserver + controller-manager│ │
│  │  + scheduler + cloud-controller       │ │
│  └───────────────────────────────────────┘ │
│                    │                        │
│  ┌─────────────────┴───────────────────┐   │
│  │         用户 Worker 节点              │   │
│  │  ┌─────────┐ ┌─────────┐ ┌───────┐ │   │
│  │  │ Node 1  │ │ Node 2  │ │ Node N│ │   │
│  │  │ (CVM)   │ │ (CVM)   │ │ (CVM) │ │   │
│  │  └─────────┘ └─────────┘ └───────┘ │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  腾讯云集成组件                       │  │
│  │  CLB / CBS / CFS / COS / TCR / CAM  │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 2 网络模式选型

TKE 提供两种容器网络方案，创建集群时必须选择且不可更改：

#### 2.1 Global Router（全局路由）

```
Pod 网段独立于 VPC，通过路由表转发
适用于：节点数 < 200，不要求 Pod 直连 VPC 资源
```

```shell
# 创建集群时指定
--network-cidr=172.16.0.0/16      # 集群内 Pod 网段
--cluster-cidr=10.0.0.0/12        # Service 网段
```

**优点**：简单，无 VPC IP 消耗
**缺点**：Pod 无法直接访问 VPC 内其他资源（需 NAT 网关），不支持固定 Pod IP

#### 2.2 VPC-CNI（ENI 网络）**推荐**

```
Pod 直接从 VPC 子网获取弹性网卡 IP
适用于：需要 Pod 与 VPC 内 CVM/数据库直通、固定 IP、超过 200 节点
```

```yaml
# VPC-CNI 模式下 Pod 直接使用 VPC IP
# Pod 内看到的 IP = VPC 内可达的 IP
# 无需 NAT 转换，性能更高
```

| 对比维度 | Global Router | VPC-CNI |
|----------|:---:|:---:|
| Pod 网络性能 | 中（NAT 转发） | 高（ENI 直通） |
| Pod 与 VPC 资源互通 | 需 NAT 网关 | 直接互通 |
| 固定 Pod IP | ❌ | ✅ |
| 子网 IP 消耗 | 低 | 高（需预留足够 IP） |
| 节点 Pod 密度 | 高（256+） | 受 ENI 数量限制 |

> **生产选型**：RAG 和 Panda 项目均使用 VPC-CNI，以确保游戏服 Pod 与 DB/Redis 低延迟直连。

#### 2.3 VPC-CNI 固定 IP 示例

```yaml
# StatefulSet + VPC-CNI 固定 IP
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: gamesvr
  annotations:
    tke.cloud.tencent.com/eni-ip-pool: "true"   # 启用固定 IP
spec:
  serviceName: gamesvr-headless
  replicas: 3
  template:
    spec:
      containers:
        - name: gamesvr
          image: gamesvr:v1.0
```

### 3 CLB 负载均衡集成

TKE 的 LoadBalancer Service 自动创建腾讯云 CLB，支持丰富的注解定制：

#### 3.1 内外网 CLB

```yaml
apiVersion: v1
kind: Service
metadata:
  name: gamesvr-external
  annotations:
    # 公网 CLB（按流量计费）
    service.kubernetes.io/qcloud-loadbalancer-internet-charge-type: "TRAFFIC_POSTPAID_BY_HOUR"
    service.kubernetes.io/qcloud-loadbalancer-internet-max-bandwidth-out: "200"
spec:
  type: LoadBalancer
  selector:
    app: gamesvr
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
---
apiVersion: v1
kind: Service
metadata:
  name: gamesvr-internal
  annotations:
    # 内网 CLB
    service.kubernetes.io/qcloud-loadbalancer-internal-subnetid: "subnet-xxxxxx"
spec:
  type: LoadBalancer
  selector:
    app: gamesvr
  ports:
    - port: 8080
```

#### 3.2 多线路 CLB（三网分离）

Panda 项目实际使用三线路模式（面向多运营商玩家）：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: gamesvr-dx      # 电信线路
  annotations:
    service.cloud.tencent.com/direct-access: "true"
    service.cloud.tencent.com/tke-service-config: |
      {
        "loadBalancer": {
          "l4Listeners": [{
            "protocol": "TCP",
            "port": 8080,
            "scheduler": "WRR"
          }]
        }
      }
  labels:
    service.cloud.tencent.com/loadbalance-type: "OPEN"  # 公网
    service.cloud.tencent.com/loadbalance-isp: "CTCC"   # 电信
spec:
  type: LoadBalancer
  ports:
    - port: 8080
      targetPort: 8080
```

| ISP 标签 | 运营商 |
|----------|--------|
| `CTCC` | 电信 |
| `CUCC` | 联通 |
| `CMCC` | 移动 |
| `BGP` | BGP 多线（默认） |

#### 3.3 CLB 直通 Pod（绕过 NodePort）

VPC-CNI 模式下可直接将 CLB 绑定到 Pod IP，性能最优：

```yaml
metadata:
  annotations:
    service.cloud.tencent.com/direct-access: "true"  # CLB 直通 Pod
    service.cloud.tencent.com/eni-pod-annotation: "true"
```

```
传统模式:  CLB → NodePort → kube-proxy → Pod（2 跳）
直通模式:  CLB → Pod ENI（1 跳，延迟降低 40%）
```

### 4 BCS 游戏工作负载

蓝鲸容器服务 BCS 在 TKE 之上扩展了游戏专用的 CRD，Panda 和 RAG 项目均重度使用：

#### 4.1 GameStatefulSet（游戏有状态集）

相比原生 StatefulSet，增加了**原地升级**和**生命周期 Hook**：

```yaml
apiVersion: tkex.tencent.com/v1alpha1
kind: GameStatefulSet
metadata:
  name: combat
spec:
  replicas: 5
  serviceName: combat-headless
  # 原地升级（不重建 Pod，只更新容器镜像）
  updateStrategy:
    type: InPlaceUpdate
    maxUnavailable: 1
  # 生命周期钩子（缩容前检查）
  preDeleteUpdateStrategy:
    hook:
      templateName: combat-hook      # 引用 HookTemplate
  selector:
    matchLabels:
      app: combat
  template:
    metadata:
      labels:
        app: combat
    spec:
      containers:
        - name: combat
          image: combat:v2.1.0
          ports:
            - containerPort: 9090
```

**原生 StatefulSet vs GameStatefulSet**：

| 能力 | StatefulSet | GameStatefulSet |
|------|:---:|:---:|
| 原地升级 | ❌ | ✅（只换镜像，不重建 Pod，保留 IP） |
| 缩容前置检查 | ❌ | ✅（HookTemplate 确保玩家下线） |
| 金丝雀更新 | ❌ | ✅（分区发布） |
| 滚动更新顺序 | 序号顺序 | 序号顺序 + 自定义 |

#### 4.2 HookTemplate（缩容前置检查）

缩容前通过 Prometheus 指标确认 Pod 可安全删除：

```yaml
apiVersion: tkex.tencent.com/v1alpha1
kind: HookTemplate
metadata:
  name: combat-hook
spec:
  metrics:
    - name: online_players        # 在线玩家数
      url: http://localhost:9090/metrics
      params:
        query: game_online_players{pod="${POD_NAME}"}
      threshold: 0                # 阈值：玩家数 = 0 才允许缩容
      operator: eq
    - name: pending_requests      # 正在处理的请求数
      url: http://localhost:9090/metrics
      params:
        query: game_pending_requests{pod="${POD_NAME}"}
      threshold: 0
      operator: eq
  timeoutSeconds: 300             # 最多等待 5 分钟
  onTimeout: ForceDelete          # 超时后强制删除或取消操作（Cancel）
```

> **原理**：kubelet 缩容时先调用 HookTemplate，轮询 Prometheus 直到阈值满足或超时。游戏服在有玩家在线时绝不会被删除。

#### 4.3 SidecarSet（全局 Sidecar 注入）

全命名空间自动为符合条件的 Pod 注入 Sidecar 容器：

```yaml
apiVersion: apps.kruise.io/v1alpha1
kind: SidecarSet
metadata:
  name: inject-apm-agent
spec:
  # 选择哪些 Pod 需要注入
  selector:
    matchLabels:
      app.kubernetes.io/managed-by: gamesvr
  # 不可修改已有注入
  updateStrategy:
    type: RollingUpdate
    maxUnavailable: 1
  # Sidecar 容器定义
  containers:
    - name: apm-agent
      image: bkm-collector:latest
      env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: http://bkm-collector.bkmonitor-operator:4317
      volumeMounts:
        - name: pod-info
          mountPath: /etc/podinfo
  # 注入到 Pod 的 volumes
  volumes:
    - name: pod-info
      downwardAPI:
        items:
          - path: labels
            fieldRef:
              fieldPath: metadata.labels
```

**SidecarSet vs 手动 Sidecar**：

| | 手动 Sidecar | SidecarSet |
|---|---|---|
| 注入方式 | 每个 Deployment 重复写 | 一次定义，自动匹配 |
| 升级 Sidecar | 逐个重建 Pod | SidecarSet 滚动更新 |
| 选择性注入 | 靠复制粘贴 | `selector` 精确控制 |

#### 4.4 PortPool（端口池管理）

多线路 CLB 场景下管理端口映射：

```yaml
apiVersion: tkex.tencent.com/v1alpha1
kind: PortPool
metadata:
  name: gamesvr-pool
spec:
  ports:
    - name: game-dx         # 电信线路
      port: 8080
      protocol: TCP
    - name: game-lt         # 联通线路
      port: 8081
      protocol: TCP
    - name: game-yd         # 移动线路
      port: 8082
      protocol: TCP
```

### 5 存储集成

#### 5.1 CBS 云硬盘（块存储）

```yaml
# TKE 中 CBS CSI 已预装，直接使用 StorageClass
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cbs-premium
provisioner: com.tencent.cloud.csi.cbs
parameters:
  type: CLOUD_PREMIUM         # 高性能云硬盘
  # type: CLOUD_SSD           # SSD
  # type: CLOUD_ENHANCEDSSD   # 增强型 SSD
  # type: CLOUD_TSSD          # 极速型 SSD
  encrypt: "ENCRYPT"
  throughput: "150"
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

#### 5.2 CFS 文件存储（共享 NAS）

适合多 Pod 读写的共享场景（日志、配置文件、静态资源）：

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: game-logs-pv
spec:
  capacity:
    storage: 500Gi
  accessModes:
    - ReadWriteMany
  csi:
    driver: com.tencent.cloud.csi.cfs
    volumeHandle: cfs-xxxxxx
    volumeAttributes:
      host: 10.0.0.100
      path: /game-logs
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: game-logs-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 500Gi
```

#### 5.3 COS 对象存储

Python 工具中常用的 COS 集成模式：

```python
# 通过 Workload Identity 或环境变量传递临时密钥
# 不硬编码 AK/SK，由 TKE CAM 角色授权
from qcloud_cos import CosConfig, CosS3Client
import os

config = CosConfig(
    Region=os.environ["COS_REGION"],
    SecretId=os.environ["COS_SECRET_ID"],     # CAM 角色注入
    SecretKey=os.environ["COS_SECRET_KEY"],
    Token=os.environ["COS_TOKEN"],            # STS 临时凭证
)
client = CosS3Client(config)

# 生成预签名下载链接（运维脚本常用）
url = client.get_presigned_url(
    Method='GET',
    Bucket='game-assets-1250000000',
    Key='release/v2.0.0/build.tar.gz',
    Expired=3600
)
```

### 6 节点池与弹性伸缩

#### 6.1 节点池分类

| 节点池类型 | 用途 | 配置建议 |
|-----------|------|----------|
| **普通节点池** | 运行常规业务 Pod | CVM 按量/包年包月 |
| **GPU 节点池** | AI/渲染任务 | GPU 型 CVM + nvidia-device-plugin |
| **原生节点池** | TKE 原生节点，免运维 | CXM 模式，自动升级 |

#### 6.2 Cluster Autoscaler（CA）配置

CA 监听 Pending 的 Pod，自动扩容节点池；空闲节点缩容：

```yaml
# 为节点池启用 CA
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-autoscaler-status
  namespace: kube-system
data:
  status: |
    cluster-autoscaler:
      nodeGroups:
        - name: ap-guangzhou-3
          minSize: 3
          maxSize: 50
          # 空闲节点缩容阈值（默认 10 分钟）
          scaleDownUnneededTime: 10m
          # 缩容前允许的空闲时间
          scaleDownUnreadyTime: 20m
```

**HPA + CA 协同工作**：

```
流量上涨 → HPA 扩容 Pod → Pod Pending（资源不足）
    → CA 检测到 Pending Pod → CA 扩容节点
    → 新节点 Ready → Pod 调度成功

流量下降 → HPA 缩容 Pod → 节点空闲
    → CA 检测到空闲节点 → CA 缩容节点（10分钟后）
```

#### 6.3 节点自动修复

TKE 节点池支持自动检测异常节点并替换：

```yaml
# 节点池配置（控制台或 API）
autoRepair: true            # 开启自动修复
autoUpgrade: true           # 开启自动升级 kubelet 版本
unschedulable: 0            # 预留不可调度的节点数
```

### 7 TCR 镜像仓库

TKE 默认集成 TCR 企业版，支持镜像安全扫描和跨地域同步：

```shell
# 1. 获取 TCR 登录密码
$ tccli tcr CreateInstanceToken --RegistryId tcr-xxxxxx

# 2. 创建 imagePullSecret
$ kubectl create secret docker-registry tcr-secret \
    --docker-server=ccr.ccs.tencentyun.com \
    --docker-username=100012345678 \
    --docker-password=<TCR_TOKEN> \
    -n game-prod

# 3. Deployment 引用
```

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
        - name: tcr-secret
      containers:
        - name: gamesvr
          image: ccr.ccs.tencentyun.com/namespace/gamesvr:v1.0.0
```

### 8 蓝鲸监控集成

TKE 集群可一键接入蓝鲸监控（bkmonitor），Panda 和 RAG 均已接入：

#### 8.1 安装 bkmonitor-operator

```shell
# 通过蓝鲸监控平台下发采集器
# 自动部署：bkmonitor-operator + kube-state-metrics + node-exporter
$ helm install bkmonitor-operator \
    --namespace bkmonitor-operator \
    --create-namespace \
    <蓝鲸平台提供的 helm chart>
```

#### 8.2 ServiceMonitor → bkmonitor 对接

bkmonitor-operator 会自动识别集群中已有的 ServiceMonitor，与传统 Prometheus Operator 模式完全兼容：

```yaml
# 与标准 ServiceMonitor 完全相同（见第二十八章）
# bkmonitor-operator 自动采集并上报到蓝鲸监控平台
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gamesvr
  labels:
    release: bkmonitor     # bkmonitor 的 selector
spec:
  selector:
    matchLabels:
      app: gamesvr
  endpoints:
    - port: metrics
      interval: 30s
```

#### 8.3 APM 集成（OTLP）

Panda 项目的 .NET 应用接入蓝鲸 APM：

```yaml
containers:
  - name: silo-server
    image: panda-silo:v1.0
    env:
      # OTLP gRPC Exporter 地址（蓝鲸 APM）
      - name: OTEL_EXPORTER_OTLP_ENDPOINT
        value: http://bkm-collector.bkmonitor-operator:4317
      - name: OTEL_RESOURCE_ATTRIBUTES
        value: service.name=silo-server,service.namespace=panda-prod
      - name: OTEL_TRACES_EXPORTER
        value: otlp
      - name: OTEL_METRICS_EXPORTER
        value: otlp
```

### 9 TKE 生产 Checklist

```
┌────────────────────────────────────────────────────────┐
│              TKE 生产环境 Checklist                      │
├────────────────────────────────────────────────────────┤
│ 集群层面:                                               │
│ □ 使用托管集群（Master 免运维）                          │
│ □ 生产环境使用 VPC-CNI 网络模式                          │
│ □ 开启集群审计日志（CLS）                                │
│ □ 开启事件持久化（CLS）                                  │
│ □ etcd 自动备份（托管集群默认开启）                       │
│ □ API Server 公网访问：关闭或仅限白名单                   │
│ □ 开启 IPVS 模式 kube-proxy                             │
│                                                        │
│ 节点层面:                                               │
│ □ 使用节点池管理（按可用区 + 用途分组）                   │
│ □ 常规节点池最小 3 节点（多 AZ 分布）                     │
│ □ GPU 节点池独立管理，打污点隔离                          │
│ □ 开启 CA 自动伸缩（min ≥ 2, max 按需）                  │
│ □ 开启节点自动修复（autoRepair）                          │
│ □ 节点使用 TencentOS 或 Ubuntu 22.04                     │
│                                                        │
│ 网络层面:                                               │
│ □ 公网 CLB + WAF 防护                                    │
│ □ 内网 CLB 用于服务间通信                                │
│ □ 多线路场景使用 PortPool 管理                           │
│ □ CLB 直通 Pod 模式（VPC-CNI）提升性能                   │
│ □ 集群内启用 node-local-dns 缓存                         │
│                                                        │
│ 安全层面:                                               │
│ □ 镜像使用 TCR 企业版（漏洞扫描 + 跨地域同步）            │
│ □ Pod 使用 CAM 角色而非 AK/SK                           │
│ □ Secret 使用凭据管理（SSM）或 External Secrets Operator │
│ □ RBAC 最小权限 + 命名空间隔离                           │
│ □ NetworkPolicy 全局拒绝 + 按需放行                      │
│                                                        │
│ 可观测性:                                               │
│ □ 接入蓝鲸监控（bkmonitor-operator）                     │
│ □ 核心服务配置 ServiceMonitor                            │
│ □ 应用接入 APM（OTLP）                                   │
│ □ 配置关键告警策略（见第十九章）                          │
│ □ 日志接入 CLS 或蓝鲸日志平台                            │
│                                                        │
│ 运维层面:                                               │
│ □ 使用 ArgoCD GitOps 部署（App of Apps 模式）            │
│ □ GameStatefulSet + HookTemplate 保证缩容安全            │
│ □ 定期进行节点池升级和镜像更新                           │
│ □ 制定集群升级方案（托管集群自动升级小版本）              │
└────────────────────────────────────────────────────────┘
```

---

## 附录A Kubernetes YAML 字段速查

> 本节解释 K8s YAML 中每个核心字段的含义，帮初学者建立"字段→作用"的映射。
> 所有字段按 `apiVersion` / `kind` / `metadata` / `spec` / `status` 五层组织。

### A.1 YAML 五层骨架

一个 K8s 资源的 YAML 文件始终遵循以下 5 层结构：

```yaml
apiVersion: apps/v1       # 【第 1 层】使用哪个 API 版本（决定可使用哪些字段）
kind: Deployment          # 【第 2 层】资源类型（Pod / Service / Deployment / ...）
metadata:                 # 【第 3 层】元数据：名称、标签、命名空间等
  name: my-app
  namespace: default
  labels:
    app: my-app
spec:                     # 【第 4 层】期望状态：用户定义的配置
  replicas: 3
  selector: ...
  template: ...
status:                   # 【第 5 层】当前状态：K8s 自动维护，用户不要写
  replicas: 3
  readyReplicas: 3
```

> `status` 字段是 K8s 自动回写的当前实际状态，用户提交 YAML 时**不要写 status**。

### A.2 metadata 字段一览

| 字段 | 必填 | 类型 | 说明 | 示例 |
|------|:---:|------|------|------|
| `name` | ✅ | string | 资源名称，同一命名空间内唯一 | `my-app` |
| `namespace` | 否 | string | 所属命名空间（默认 `default`） | `team-a` |
| `labels` | 否 | map | 标签，用于匹配和筛选 | `app: nginx` |
| `annotations` | 否 | map | 注解，存储非标识性元数据 | `prometheus.io/scrape: "true"` |
| `ownerReferences` | 否 | array | 所有者引用（GC 级联删除用） | 系统自动填 |
| `finalizers` | 否 | array | 终结器（删除前执行清理逻辑） | `kubernetes` |
| `generation` | 否 | int | 期望状态的版本号（每次 spec 变更递增） | 系统自动填 |
| `resourceVersion` | 否 | string | 集群级别的版本号（乐观锁） | 系统自动填 |
| `uid` | 否 | string | 资源的全局唯一标识 | 系统自动填 |

**labels vs annotations 的区别**：
- `labels` → 用于**筛选和关联**（`kubectl get pods -l app=nginx`，Service 的 selector）
- `annotations` → 用于**存储额外信息**（监控配置、部署描述符、工具标记）

### A.3 Pod Spec 核心字段

```yaml
spec:
  # === 容器定义 ===
  containers:               # 主容器列表（至少一个）
  initContainers:           # Init 容器列表（在主容器前按序运行）
  
  # === 调度 ===
  nodeSelector:             # 标签匹配调度到特定节点
  nodeName:                 # 直接指定节点（跳过调度器）
  affinity:                 # 亲和性/反亲和性规则
  tolerations:              # 容忍节点污点
  
  # === 网络 ===
  hostNetwork: false        # 是否使用宿主机网络
  dnsPolicy: ClusterFirst   # DNS 策略
  hostAliases: []           # 覆盖 /etc/hosts
  shareProcessNamespace: false  # 容器间共享 PID 命名空间
  
  # === 存储 ===
  volumes:                  # 卷定义
  serviceAccountName:       # 绑定的 ServiceAccount
  
  # === 安全 ===
  securityContext:          # Pod 级安全上下文
  hostIPC: false            # 使用宿主机 IPC
  hostPID: false            # 使用宿主机 PID
  
  # === 生命周期 ===
  restartPolicy: Always     # 重启策略（Always/OnFailure/Never）
  terminationGracePeriodSeconds: 30  # 优雅终止等待时间
  activeDeadlineSeconds:    # Pod 最长存活时间（超时终止）
  
  # === 优先级 ===
  priorityClassName:        # 优先级类名（决定调度和抢占顺序）
  
  # === 镜像拉取 ===
  imagePullSecrets:         # 拉取私有镜像的认证
```

### A.4 Container Spec 核心字段

```yaml
containers:
  - name: my-app            # 【必填】容器名称
    image: nginx:1.25       # 【必填】镜像名:标签
    imagePullPolicy: IfNotPresent  # 拉取策略：Always / IfNotPresent / Never
    
    # === 入口点 ===
    command:                # 覆盖镜像 ENTRYPOINT
    args:                   # 覆盖镜像 CMD
    
    # === 端口 ===
    ports:
      - name: http          # 端口名（用于 Service 引用）
        containerPort: 8080 # 容器内监听的端口
        protocol: TCP       # TCP / UDP / SCTP
    
    # === 环境变量 ===
    env:
      - name: DB_HOST
        value: "mysql"      # 直接赋值
      - name: DB_PASSWORD
        valueFrom:           # 从其他来源取值
          secretKeyRef:
            name: db-secret
            key: password
    
    # === 资源 ===
    resources:
      requests:             # 调度保障（节点必须有多余量才能调度）
        cpu: "200m"
        memory: "128Mi"
      limits:               # 硬上限（超过会被 throttle/kill）
        cpu: "500m"
        memory: "256Mi"
    
    # === 存储挂载 ===
    volumeMounts:
      - name: data-vol      # 引用 volumes 中定义的卷名
        mountPath: /data    # 容器内的挂载路径
        readOnly: false
        subPath:            # 只挂载卷中的子路径
    
    # === 探针 ===
    livenessProbe:          # 存活检查（失败→重启容器）
    readinessProbe:         # 就绪检查（失败→移出 Service）
    startupProbe:           # 启动检查（成功前禁用上述两个探针）
    
    # === 生命周期钩子 ===
    lifecycle:
      postStart:            # 容器创建后立即执行
      preStop:              # 容器终止前执行（优雅关闭）
    
    # === 安全 ===
    securityContext:        # 容器级安全上下文
    
    # === 终端 ===
    tty: false
    stdin: false
```

### A.5 Deployment Spec 核心字段

| 字段 | 说明 | 常用值 |
|------|------|--------|
| `replicas` | 期望副本数 | `3` |
| `selector` | 通过标签选择管理的 Pod | `matchLabels: {app: web}` |
| `strategy.type` | 更新策略 | `RollingUpdate` / `Recreate` |
| `strategy.rollingUpdate.maxSurge` | 更新期间可超出副本数 | `1` 或 `25%` |
| `strategy.rollingUpdate.maxUnavailable` | 更新期间可不可用的副本数 | `0` 或 `25%` |
| `minReadySeconds` | Ready 后等待多久才认为就绪 | `10` |
| `revisionHistoryLimit` | 保留的 ReplicaSet 历史数量 | `5` |
| `paused` | 暂停部署 | `false` |
| `progressDeadlineSeconds` | 更新超时时间 | `600` |

### A.6 Service Spec 核心字段

| 字段 | 说明 | 常用值 |
|------|------|--------|
| `type` | Service 类型 | `ClusterIP` / `NodePort` / `LoadBalancer` / `ExternalName` |
| `selector` | 通过标签选择后端 Pod | `app: mysql` |
| `ports[].port` | Service 对外端口 | `80` |
| `ports[].targetPort` | 后端 Pod 的端口 | `8080` |
| `ports[].nodePort` | 节点端口（仅 NodePort） | `30000-32767` |
| `clusterIP` | 设为 `None` 即 Headless | `10.96.0.1` 或 `None` |
| `sessionAffinity` | 会话保持 | `None` / `ClientIP` |
| `externalTrafficPolicy` | 外部流量策略 | `Cluster` / `Local` |

### A.7 YAML 易错点速查

| 易错点 | 说明 |
|--------|------|
| `labels` vs `selector` | `metadata.labels` 是贴在自己身上的，`spec.selector` 是匹配别人的——两者必须一致（Deployment 中） |
| `targetPort` vs `port` | `port` 是 Service 自己的端口，`targetPort` 是 Pod 的端口 |
| `containers` vs `initContainers` | 前者并行，后者串行且必须全部成功 |
| `command` vs `args` | `command` 覆盖 ENTRYPOINT，`args` 覆盖 CMD |
| `requests` vs `limits` | 前者决定调度和 OOM Score，后者是硬天花板 |
| `emptyDir` vs `hostPath` | 前者随 Pod 生命周期，后者绑定节点 |

### A.8 kubectl 查看字段文档

```shell
# 查看某类资源的全部可用字段
$ kubectl explain pod.spec
$ kubectl explain deployment.spec.strategy.rollingUpdate

# 递归查看所有字段（包含说明）
$ kubectl explain pod --recursive
```

---

> **文档版本**: v6.2  
> **定位**：Kubernetes 生产实战完全指南（独立完整文档，含基础概要 + 进阶 + 生产专题）  
> **v6.2 新增**：附录A YAML 字段速查；第三章探针/Init/亲和性补充完整 YAML 示例；第五章补充 Service 调试验证命令；第六章补充 Volume/PV 完整 YAML；第十七章补充滚动更新观察命令  
> **v6.1 新增**：CSI 内部原理（架构/gRPC 服务/Sidecar/卷生命周期/CSI Migration）、CNI 内部原理（插件链/核心操作/数据平面对比/排障）、Istio Operator 生产级安装（IstioOperator CR/声明式管理/金丝雀升级）  
> **v6.0 新增**：目录 + 前置 1~10 章基础内容概要（Pod/Controller/Service/存储/ConfigMap/Ingress/命名空间/Helm）  
> **v5.0 新增**：腾讯云 TKE 生产实践（网络模式/BCS 游戏工作负载/CLB 多线路/SidecarSet/HookTemplate/PortPool/存储/伸缩/镜像仓库/蓝鲸监控）  
> **v4.0 新增**：ServiceMonitor & PodMonitor 声明式指标采集完整指南（元标签、Relabeling、生产案例、调优排障）  
> **v3.0 新增**：GitOps & ArgoCD、云资源集成（CSI/ExternalDNS/ExternalSecrets）、Sidecar 模式、生产网络架构  
> **相关文档**：`Prometheus_Observability.md`（Prometheus 全链路专题）
