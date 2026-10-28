# ArgoCD & GitOps 面试准备指南

> ML SRE 面试中，ArgoCD 出现在**多集群部署**、**GitOps 实践**、**持续交付**三个话题中。
> 本文档覆盖 GitOps 核心概念、ArgoCD 架构原理、多集群管理、面试场景题，与多地域容灾章节互补。

---

## 目录

- [术语速查表](#术语速查表)
- [第一章 GitOps 概念与背景](#第一章-gitops-概念与背景)
- [第二章 ArgoCD 核心架构](#第二章-argocd-核心架构)
- [第三章 Application 资源详解](#第三章-application-资源详解)
- [第四章 多集群管理](#第四章-多集群管理)
- [第五章 App of Apps 模式](#第五章-app-of-apps-模式)
- [第六章 同步策略与健康检查](#第六章-同步策略与健康检查)
- [第七章 面试高频 12 问](#第七章-面试高频-12-问)
- [第八章 实战速查](#第八章-实战速查)

---

## 术语速查表

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **GitOps** | Git Operations | 以 Git 仓库为唯一真实源（Single Source of Truth），声明式管理基础设施和应用的部署 |
| **ArgoCD** | Argo Continuous Delivery | CNCF 毕业项目的 GitOps 持续交付工具，核心是一个 K8s Controller，持续比较 Git 中的期望状态与集群实际状态 |
| **Application** | ArgoCD Application CRD | 定义一个应用的部署目标：Git 仓库在哪、部署到哪个集群、用什么同步策略 |
| **Project** | ArgoCD AppProject CRD | 应用的逻辑分组，管理权限和资源白名单（允许哪些集群、哪些 Git 仓库、哪些资源类型） |
| **Sync** | 同步 | ArgoCD 将 Git 仓库中的期望状态应用到 K8s 集群的过程。结果分三种：Synced / OutOfSync / Unknown |
| **Health** | 健康状态 | 对已部署资源的健康检查（如 Deployment 的 Pod 是否全部就绪）。分 Healthy / Progressing / Degraded / Missing |
| **Repository** | Git 仓库连接 | ArgoCD 中注册的 Git 仓库凭据和连接，支持 HTTPS / SSH / GitHub App 认证 |
| **Cluster** | 目标集群 | ArgoCD 管理的 K8s 集群。可以是 ArgoCD 自己所在的集群，也可以是远程集群 |
| **App of Apps** | 应用模式 | 用父 Application 管理子 Application 的模式，实现声明式的多应用批量管理 |
| **ArgoCD API Server** | API 服务 | ArgoCD 的入口组件，提供 Web UI、gRPC/REST API、Git webhook 回调 |
| **Application Controller** | 应用控制器 | 核心控制器，持续比对 Git 期望状态和集群实际状态，触发同步 |
| **Repo Server** | 仓库服务 | 从 Git 仓库拉取代码、渲染 Helm/Kustomize/Jsonnet 模板、生成最终 K8s manifests |
| **argocd-image-updater** | 镜像更新器（可选组件） | 自动检测容器镜像仓库中的新版本，更新 Git 仓库中的镜像 tag |
| **ApplicationSet** | 批量应用生成器 | 基于模板自动批量创建 Application，按集群/分支/目录等维度生成 |

---

## 第一章 GitOps 概念与背景

### 0 传统 CD 的痛点

```
传统持续部署流程（Push 模型）：

CI: 代码提交 → 构建 → 推镜像
CD: Jenkins Pipeline → kubectl apply → 部署到集群

问题：
  1. Jenkins 需要集群 kubeconfig（安全问题）
  2. 部署脚本和集群状态没有做版本管理
  3. "手动改了一下线上配置" → 没人知道谁改的
  4. 回滚需要重新跑 pipeline（慢）
  5. 多集群部署时，pipeline 复杂度成倍增长
```

### 1 GitOps 做了什么事

```
GitOps = 把 Git 仓库当成唯一真实源（Single Source of Truth）

┌─────────────────────────────────────────────────────────┐
│                    传统 Push 模型                         │
│                                                         │
│  CI Pipeline ──kubectl apply──▶ K8s Cluster              │
│        ↑                                                 │
│        └── 谁有 kubeconfig 谁就能改集群，不安全           │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                    GitOps Pull 模型                       │
│                                                         │
│  开发者 ──git push──▶ Git 仓库                           │
│                         │                               │
│                    ArgoCD pull                           │
│                    (持续监控 Git 变更)                    │
│                         │                               │
│                         ▼                               │
│                   K8s Cluster                            │
│                                                         │
│  集群凭据只存在 ArgoCD 内部，CI Pipeline 不需要访问集群     │
│  所有变更都在 Git 中有记录（git log = 变更历史）          │
└─────────────────────────────────────────────────────────┘
```

**GitOps 四大原则**：

| 原则 | 说明 |
|------|------|
| **声明式** | 用 YAML/Helm/Kustomize 描述期望状态，不写 `kubectl` 命令 |
| **版本化** | 所有配置存在 Git，变更历史 = `git log`，回滚 = `git revert` |
| **自动化** | ArgoCD 自动检测 Git 变更并同步到集群，不需要手动操作 |
| **持续协调** | ArgoCD 每 3 分钟检查一次集群状态，发现偏差自动修正 |

### 2 面试速记：GitOps vs 传统 CD 一句话对比

```
传统 CD：Pipeline 把配置"推"到集群（Push）
GitOps：ArgoCD 从 Git "拉"配置并应用到集群（Pull）

Push 的问题：谁有 kubeconfig 谁就能改集群
Pull 的好处：Git 是唯一入口，ArgoCD 是唯一执行者，集群不暴露凭据
```

---

## 第二章 ArgoCD 核心架构

### 0 三大核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                    ArgoCD 架构                               │
│                                                             │
│  外部用户（浏览器/CLI）                                       │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────┐                                        │
│  │  API Server     │  ← gRPC/REST API + Web UI              │
│  │  (入口层)       │     RBAC 鉴权                          │
│  └────────┬────────┘                                        │
│           │                                                 │
│     ┌─────┴─────┐                                           │
│     ▼           ▼                                           │
│  ┌──────────┐ ┌──────────────────┐                         │
│  │  Repo    │ │  Application    │                          │
│  │  Server  │ │  Controller     │                          │
│  │ (渲染)   │ │  (协调)          │                          │
│  └────┬─────┘ └───────┬──────────┘                         │
│       │               │                                     │
│       │           ┌───┴───┐                                 │
│       │           │ Redis │  ← 缓存同步状态                  │
│       │           └───────┘                                 │
│       │                                                     │
│       ▼               ▼                                     │
│  Git 仓库         目标 K8s 集群(们)                          │
│  (期望状态)       (实际状态)                                 │
└─────────────────────────────────────────────────────────────┘
```

**三个组件的职责**：

| 组件 | 职能 | 类比 | 关键逻辑 |
|------|------|------|----------|
| **API Server** | 接收请求、鉴权、Web UI 后端 | Nginx + Auth | 转发创建 Application 请求 |
| **Repo Server** | 从 Git 拉取源码，渲染 Helm/Kustomize 模板 | Jenkins 的 SCM + 渲染步骤 | 生成最终 K8s YAML |
| **Application Controller** | 比对新旧 YAML → 执行 `kubectl apply` | Jenkins 的 deploy 步骤 | 持续协调循环 |

### 1 一次 Sync 的完整流程

```
时刻 T：开发者 git push 到仓库

Step 1: Repo Server 检测变更（每 3 分钟轮询或 webhook 触发）
  → git clone / git fetch 最新代码
  → 根据 Application 定义的 source（路径/分支/chart）定位到配置目录
  → 渲染模板：Helm template / Kustomize build / Jsonnet / 纯 YAML
  → 输出原始 K8s Manifests（Deployment.yaml, Service.yaml ...）

Step 2: Application Controller 对比差异
  → 拿到 Repo Server 生成的"期望状态"（Desired Manifests）
  → 通过 K8s API 获取集群中资源的"实际状态"（Live State）
  → 执行 diff：哪些资源变了（新增/修改/删除）

Step 3: 执行 Sync
  → 对新增/修改的资源 → kubectl apply
  → 对 Git 中删除但集群中还存在的资源 → kubectl delete（前提开启 Prune）
  → 记录 sync 结果到 Redis（Synced / OutOfSync）

Step 4: 后续持续协调
  → Controller 每 3 分钟重新检查一次
  → 发现有人手动改了集群 → 标记 OutOfSync
  → 如果开启了 Auto-Sync → 自动修回 Git 定义的状态（Self-Healing）
```

### 2 部署模式

```
模式 1：集群内（默认）
  ArgoCD 和业务应用在同一个集群里
  → 安装最简单，适合单集群场景

模式 2：Hub-Spoke（多集群管理）
  ┌────────────────────┐
  │  Hub Cluster       │  ← ArgoCD 部署在这里
  │  (管理集群)         │
  │  有所有远程集群的    │
  │  kubeconfig/Service │
  └───┬───────┬────────┘
      │       │
      ▼       ▼
  ┌──────┐ ┌──────┐
  │ Spoke│ │ Spoke│  ← 业务应用部署在这些集群
  │ GPUs │ │ GPUs │     ArgoCD 推配置过来
  └──────┘ └──────┘

  关键：Spoke 集群不需要安装 ArgoCD，只需创建 ServiceAccount + RBAC
  场景：ML 训练平台多机房 GPU 集群（主集群部署 ArgoCD，GPU 集群只跑训练任务）
```

---

## 第三章 Application 资源详解

### 0 Application = 一个部署目标的声明

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: game-server-prod
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io   # 删除 Application 时级联删资源
spec:
  # ========== 目标集群 ==========
  destination:
    server: https://10.0.2.1:6443             # 目标集群 API Server 地址
    namespace: game-prod                        # 部署到哪个命名空间
    # name: gpu-cluster-gz                     # 也可以用集群名字（在 ArgoCD 中注册的名称）
  
  # ========== Git 源 ==========
  project: default
  source:
    repoURL: https://git.internal/game/game-server-config.git
    targetRevision: main                        # Git 分支/tag/commit
    path: overlays/production                   # 配置文件的目录路径
    
    # Helm 模式（三选一）
    # helm:
    #   valueFiles:
    #     - values-prod.yaml
    
    # Kustomize 模式（三选一）
    # kustomize:
    #   namePrefix: prod-
    
    # 纯 YAML 模式（什么都不写就是纯 YAML）
  
  # ========== 同步策略 ==========
  syncPolicy:
    automated:                                  # 自动同步
      prune: true                               # 自动删除 Git 中已删除的资源
      selfHeal: true                            # 自动修复手动变更（Self-Healing）
      allowEmpty: false                         # 不允许空配置（防止误删）
    syncOptions:
      - CreateNamespace=true                    # 自动创建命名空间
      - PrunePropagationPolicy=foreground       # 级联删除
      - ApplyOutOfSyncOnly=true                 # 只同步差异资源（加速）
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  
  # ========== 健康检查 ==========
  ignoreDifferences:                            # 忽略某些字段差异
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas                       # HPA 改的副本数不触发 OutOfSync
    - group: ""
      kind: Service
      jsonPointers:
        - /spec/clusterIP
```

### 1 自动 Sync vs 手动 Sync

```
自动 Sync (automated)：
  好处：Git 变了就自动部署，完全无需人工介入
  风险：main 分支写错了 → 全自动部署到生产（需要配合 PR + CI 检查）
  适用：开发环境、非核心服务

手动 Sync：
  好处：确认过再部署，安全
  缺点：需要人工介入
  适用：生产环境、高风险变更

字节/大厂常见做法：
  开发/测试环境 → automated: true
  生产环境 → automated: false，通过 Web UI 或 CLI 手动 sync
  关键服务 → 加 PR 审批 + ArgoCD Sync Window 限制非工作时间部署
```

### 2 Project（资源白名单）

```
Project 的作用 → 限制"这个项目允许部署到哪些集群 / 使用哪些 Git 仓库 / 创建哪些资源"

反面例子：
  算法工程师不小心把 Deployment 部署到了 GPU 训练集群的管理命名空间 → 覆盖了系统组件

正面做法：
  AppProject 配置：
    sourceRepos: 只允许特定的 Git 仓库
    destinations: 只允许特定的命名空间
    clusterResourceWhitelist: 只允许特定的资源类型

  这样即使写错，ArgoCD 也会拒绝同步
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: gpu-training
  namespace: argocd
spec:
  description: GPU 训练任务部署项目
  sourceRepos:
    - 'https://git.internal/gpu/*'             # 只允许 gpu 组下仓库
  destinations:
    - namespace: 'training-*'                   # 只允许部署到 training- 前缀的命名空间
      server: https://10.0.2.1:6443            # 只允许这一个集群
  clusterResourceWhitelist:                     # 允许创建集群级别的资源
    - group: ''
      kind: Namespace
  namespaceResourceBlacklist:                   # 禁止在命名空间内创建的资源
    - group: ''
      kind: Secret                               # 防止泄漏凭据
```

---

## 第四章 多集群管理

> 这和 ML_SRE_Interview_Guide 第九章"多集群管理"互补，这里聚焦 ArgoCD 的具体做法。

### 0 为什么 ML 平台需要多集群

```
场景：字节 Seed 团队管理多个 GPUs 集群
  - 华北 GPU 集群 (500 nodes × 8 H100)
  - 华南 GPU 集群 (200 nodes × 8 H100)
  - 每个集群需要部署相同的 GPU Operator + 监控组件 + 训练平台组件

传统方式：每个集群跑一遍 Jenkins Pipeline → 4 个集群 × 5 个组件 = 20 条 Pipeline
ArgoCD：写 1 份配置 Git → ArgoCD 自动推送到所有集群

核心理念：配置写一次，ArgoCD 帮你推送到所有注册的集群。
```

### 1 注册远程集群

```shell
# 列出当前管理的集群
$ argocd cluster list
SERVER                          NAME              STATUS
https://10.0.1.1:6443          in-cluster        Successful   ← ArgoCD 自己所在的集群
https://10.0.2.1:6443          gpu-cluster-gz    Successful   ← 远程 GPU 集群（华北）
https://10.0.3.1:6443          gpu-cluster-sh    Successful   ← 远程 GPU 集群（华南）

# 注册新集群
$ argocd cluster add gpu-cluster-nj --name gpu-cluster-nj

# 原理：argocd cluster add 做了两件事
# 1. 在目标集群创建 namespace=argocd + ServiceAccount + ClusterRole + Secret（凭据）
# 2. 在 ArgoCD 所在集群创建 Secret（含有目标集群的 kubeconfig）
```

### 2 一个 Application 部署到多个集群（ApplicationSet）

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: gpu-operator-all-clusters
  namespace: argocd
spec:
  # 生成器：按集群列表生成 Application
  generators:
    - list:
        elements:
          - cluster: gpu-cluster-gz
            url: https://10.0.2.1:6443
            gpuDriverVersion: "550.54.15"
          - cluster: gpu-cluster-sh
            url: https://10.0.3.1:6443
            gpuDriverVersion: "550.54.15"
  template:
    metadata:
      name: 'gpu-operator-{{cluster}}'
    spec:
      destination:
        server: '{{url}}'
        namespace: gpu-operator
      source:
        repoURL: https://git.internal/infra/gpu-operator.git
        targetRevision: main
        path: .
        helm:
          parameters:
            - name: driver.version
              value: '{{gpuDriverVersion}}'       # 每个集群可定制驱动版本
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

**常见生成器**：

| 生成器 | 作用 | 场景 |
|--------|------|------|
| **List** | 手动列出集群和参数 | 集群数量固定、配置差异大 |
| **Cluster** | 按注册的集群自动生成 | 所有集群部署相同内容 |
| **Git Directory** | 按 Git 目录结构生成 | 每个子目录 = 一个 Application |
| **SCM Provider** | 按 Git 组织/仓库生成 | 每个仓库 = 一个 Application（多租户） |
| **Pull Request** | 按 PR 临时生成环境 | 预览环境 / 临时测试集群 |

---

## 第五章 App of Apps 模式

### 0 问题场景

```
你有一个 GPU 训练平台，包含：
  - gpu-operator
  - prometheus-stack
  - training-platform
  - logging (Loki)
  - ingress-nginx

不用 App of Apps 的做法：
  手动创建 5 个 Application YAML → 一个一个 apply

App of Apps 的做法：
  创建 1 个根 Application → 它指向一个 Git 目录
  → 目录里有 5 个子 Application YAML
  → ArgoCD 自动创建并管理这 5 个 Application
```

### 1 目录结构

```
git-repo/
├── app-of-apps/
│   └── root-app.yaml          # 根 Application，指向 apps/ 目录
└── apps/
    ├── gpu-operator.yaml       # Application: GPU Operator
    ├── prometheus-stack.yaml   # Application: Prometheus
    ├── training-platform.yaml  # Application: 训练平台
    ├── loki.yaml               # Application: 日志
    └── ingress-nginx.yaml      # Application: Ingress
```

```yaml
# 根 Application：只定义一个，交给 ArgoCD
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  source:
    repoURL: https://git.internal/infra/gpu-platform.git
    path: apps/                        # ← 指向 apps 目录
    targetRevision: main
    directory:
      recurse: true
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**效果**：
1. 你只需创建 `root-app` 这一个 Application
2. ArgoCD 扫描 `apps/` 目录，发现 5 个子 Application 的 YAML
3. 自动创建这 5 个子 Application
4. 子 Application 再各自去部署实际应用
5. 新增服务 → 在 `apps/` 下加一个 YAML → ArgoCD 自动识别

---

## 第六章 同步策略与健康检查

### 0 Self-Healing（自愈）

```
Self-Healing = 自动修复手动变更

开了 selfHeal: true：
  场景：有人手动 kubectl scale deployment game-server --replicas=10
        但 Git 里定义的是 replicas: 3
  → ArgoCD 检测到差异 → 自动修回 3（通常是 3 分钟后）
  → 告警："有人手动改集群！"

没开 selfHeal：
  → 标记为 OutOfSync，但不自动修复
  → 需要手动触发 sync 才会修回去

推荐：
  生产核心服务 → selfHeal: true（防止误操作）
  开发环境 → selfHeal: false（避免打断调试）
```

### 1 Prune（自动清理）

```
Prune = Git 中删了，集群中也跟着删

开了 prune: true：
  Git 中删除了 game-server.yaml
  → ArgoCD sync 时自动 kubectl delete game-server
  → 确保集群状态 = Git 状态

没开 prune：
  → Git 中删了，集群中还在（不会自动删）
  → 需要手动删除或标记为需要 prune

风险：Git 中删错了 → Prune 直接删线上服务
缓解：开 selfHeal + prune 时，确保 Git 仓库有 branch protection + PR review
```

### 2 Sync Window（同步窗口）

```yaml
# 限制同步时间段，防止非工作时间触发变更
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: production-apps
spec:
  syncWindows:
    - kind: allow          # 只在工作时间允许同步
      schedule: '0 9 * * 1-5'     # 周一至周五 9:00 开始
      duration: 9h                 # 持续 9 小时（到 18:00）
      applications:
        - '*'                      # 针对所有 Application
      manualSync: true             # 允许手动覆盖
    - kind: deny           # 禁止在维护窗口同步
      schedule: '0 2 * * 0'
      duration: 2h
      namespaces:
        - 'production-*'
```

### 3 健康检查定制

```yaml
# 默认的健康检查只判断 Deployment 是否 Ready
# 可以自定义 CRD 的健康检查字段
apiVersion: argoproj.io/v1alpha1
kind: Application
spec:
  syncPolicy:
    automated:
      selfHeal: true
  ignoreDifferences:
    # 场景1：HPA 控制的副本数忽略
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
    # 场景2：GPU Pod 被 Scheduler 加了临时 Taint 时忽略
    - group: ""
      kind: Pod
      jsonPointers:
        - /spec/tolerations
    # 场景3：Service 的 clusterIP 由 K8s 分配
    - group: ""
      kind: Service
      jsonPointers:
        - /spec/clusterIP
```

---

## 第七章 面试高频 12 问

### Q1：GitOps 和传统 CI/CD 有什么区别？

```
传统 CI/CD：Pipeline Push 模型
  CI 构建镜像 → CD Pipeline kubectl apply
  问题：Jenkins 持有集群凭据、部署逻辑分散在 Pipeline 脚本中、无版本回滚能力

GitOps：Pull 模型
  开发者 git push → ArgoCD 检测到 Git 变更 → 拉取 + diff + apply 到集群
  优势：
    1. Git 是唯一入口，所有变更可审计 (git log)
    2. 集群凭据只在 ArgoCD 内，更安全
    3. 回滚 = git revert + ArgoCD 自动同步（秒级）
    4. Self-Healing：有人手动改集群 → 自动修回 Git 定义
```

### Q2：ArgoCD 的 Application Controller 是怎么工作的？

```
持续协调循环（类似 K8s Reconciliation Loop）：

1. 每 3 分钟（可配）触发一次协调
2. 获取 Git 期望状态（通过 Repo Server 渲染 Helm/Kustomize）
3. 获取集群实际状态（通过 K8s API 查询已有资源）
4. diff 对比：
   - Git 有，集群没有 → 需创建
   - Git 改了，集群旧 → 需更新
   - Git 删了，集群还在 → 需 Prune（如果开启了）
5. 差异 = 0 → 标记 Synced + Healthy
   差异 > 0 → 标记 OutOfSync
6. 如果开启了 autoSync → 执行变更
```

### Q3：ArgoCD 怎么知道 Git 仓库有了新提交？

```
三种检测方式：

方式 1：Polling（默认，每 3 分钟）
  → Repo Server git fetch 检查是否有新 commit
  → 简单可靠，但有最多 3 分钟延迟

方式 2：Webhook
  → Git 仓库配置 webhook → ArgoCD API Server
  → Git push → 立即触发 refresh
  → 延迟 < 5 秒，推荐生产环境使用

方式 3：手动触发
  → argocd app sync my-app
  → Web UI 点 Refresh 按钮
```

### Q4：ArgoCD 的 Self-Healing 是什么？有什么风险？

```
Self-Healing = 自动修复手动变更

机制：
  ArgoCD 每 3 分钟检测一次集群状态
  发现实际状态 ≠ Git 期望状态 → 自动修回

例子：
  有人 kubectl scale deployment game-server --replicas=5
  Git 中是 replicas: 3
  → 3 分钟后 ArgoCD 自动 scale 回 3

风险：
  1. 排障时手动改了配置，还没来得及改 Git → 被自动覆盖
     → 解决：临时关 autoSync 或用 argocd app pause
  2. HPA 改了副本数 → ArgoCD 又改回去 → 抖动
     → 解决：配置 ignoreDifferences 忽略 HPA 管理的字段
```

### Q5：Application 和 ApplicationSet 的区别？

```
Application：手动创建，一个 Application = 一个部署目标
ApplicationSet：自动批量生成 Application

ApplicationSet 的生成器：
  - List：手动列出集群 → 适合集群数量少
  - Cluster：按注册的集群 → 适合所有集群统一部署
  - Git Directory：按目录 → 适合 mono repo 多服务
  - SCM Provider：按仓库 → 适合多团队各自维护

场景示例：
  有 10 个 GPU 集群，每个都要部署 GPU Operator
  → ApplicationSet + Cluster Generator → 1 个 YAML 搞定 10 个集群
```

### Q6：ArgoCD 多集群是怎么连上的？

```
步骤：
1. 在远程集群创建 ServiceAccount + ClusterRole + ClusterRoleBinding
2. 把远程集群的 kubeconfig（包含 token）以 Secret 形式存在 ArgoCD 所在集群
3. ArgoCD 通过这个 Secret 中的 kubeconfig 访问远程集群

argocd cluster add <cluster-name> 这条命令自动化了上面所有步骤。

安全考量：
  - 远程集群的 ServiceAccount 的 ClusterRole 应遵循最小权限原则
  - 不同环境使用不同的 ServiceAccount（prod 和 dev 权限分开）
  - Secret 中的 token 可以定期轮转
```

### Q7：什么是 App of Apps 模式？什么时候用？

```
App of Apps = 用一个父 Application 管理多个子 Application

用法：
  1. 在 Git 仓库中创建一个 apps/ 目录
  2. 在 apps/ 下放子 Application 的 YAML 文件
  3. 创建一个根 Application，其 source.path = apps/
  4. ArgoCD 自动创建所有子 Application

什么时候用：
  ✅ 管理大量 Application（> 10 个）
  ✅ 需要统一管理新环境（dev/staging/prod）
  ✅ 多租户场景（每个团队一个子目录）

不用的时候：
  ❌ 只有 1~2 个 Application → 手动创建更快
  ❌ 不同 Application 有完全不同 Git 仓库和集群 → ApplicationSet 更合适
```

### Q8：ArgoCD 同步失败了，会回滚吗？

```
ArgoCD 本身不会自动回滚到上一个版本。
它的行为取决于 sync 失败后的状态：

Sync 失败（kubectl apply 报错）：
  → 标记为 OutOfSync（有错误）
  → 部分资源可能已创建，部分可能失败
  → 不会自动回滚

恢复方式：
  # 方式 1：revert 到上一次成功的 commit
  $ git revert <bad-commit>
  $ git push
  → ArgoCD 检测到新 commit → 自动 sync 回正确状态

  # 方式 2：手动指定 targetRevision 回旧版本
  argocd app set my-app --revision <last-good-commit-hash>
  argocd app sync my-app

  # 方式 3：用 Argo Rollouts 做金丝雀/蓝绿发布（进阶）
  → 观察新版本指标 → 自动或手动决策 promote/abort
```

### Q9：metrics 变更也用 ArgoCD 管吗？比如改 Prometheus 告警规则

```
应该这样分层：

配置（用 ArgoCD 管）：
  - PrometheusRule YAML（告警规则）
  - ServiceMonitor YAML
  - Grafana Dashboard JSON
  - Helm values（采集间隔、保留时间）

数据（不用 ArgoCD 管）：
  - Prometheus 采集的 metric 数据（TSDB）
  - Grafana 用户创建的临时面板

好处：
  → 告警规则改了 → Git PR review → 合并 → ArgoCD 自动同步
  → 告警规则被谁改过 → git log 一清二楚
  → 新集群上线 → ArgoCD 自动部署全套监控规则
```

### Q10：Helm 和 ArgoCD 怎么配合？

```
ArgoCD 原生支持三种配置管理方式（三选一）：

1. 纯 YAML：
   source.path: ./manifests/
   → ArgoCD 直接 apply 目录里的 YAML 文件

2. Helm：
   source.path: ./charts/my-app
   source.helm.valueFiles: [values-prod.yaml]
   → ArgoCD 内部执行 helm template → apply 渲染后的 manifests

3. Kustomize：
   source.path: ./overlays/production
   → ArgoCD 内部执行 kustomize build → apply 渲染后的 manifests

推荐做法：
  Helm Chart 存通用模板（社区版或公共 chart）
  values.yaml 存环境差异（按 dev/staging/prod 分开）
  ArgoCD Application 引用对应的 values 文件

面试加分：
  "ArgoCD 调 helm template 而不是 helm install，因为：
   - helm install 管理 Release 生命周期，与 ArgoCD 的 Application 冲突
   - helm template 只渲染 manifests，不做状态管理，把控制权交给 ArgoCD"
```

### Q11：GPU Operator 这种组件用 ArgoCD 管吗？

```
用，而且是推荐做法：

分层策略：
  ┌─────────────────────────┐
  │ 集群层（用 ArgoCD 管）    │
  │ GPU Operator             │
  │ Prometheus Operator      │
  │ cert-manager             │
  │ Ingress Controller       │
  ├─────────────────────────┤
  │ 业务层（用 ArgoCD 管）    │
  │ 训练平台 API              │
  │ 推理服务 (vLLM)           │
  │ 监控告警规则              │
  ├─────────────────────────┤
  │ 数据层（不用 ArgoCD 管）  │
  │ 模型权重                  │
  │ 训练数据集                │
  │ Checkpoint               │
  └─────────────────────────┘

GPU Operator 的特殊注意：
  1. 驱动版本写在 Helm values 里：driver.version: "550.54.15"
     → Git 中可追溯版本变更
  2. GPU Operator DaemonSet 更新会级联影响所有 GPU Pod
     → 建议设置 syncWindow 在维护窗口更新
  3. 不同集群可能需要不同驱动版本
     → ApplicationSet + list generator → 每个集群定制 driver.version
```

### Q12：ArgoCD 和 Flux CD 有什么区别？

```
都是 CNCF 毕业项目，都是 GitOps 工具，核心思路相同。

| 维度 | ArgoCD | Flux CD |
|------|--------|---------|
| 哲学 | Application 为中心 | Source + Kustomization 分层 |
| UI | 内置 Web UI（很强） | 没有内置 UI（需配合 Weave GitOps） |
| 多集群 | Hub-Spoke 模式 | 每个集群独立部署 |
| 学习曲线 | 较低（概念少） | 略高（分层抽象） |
| 生态 | Argo Rollouts / Events / Workflows | 与 Kustomize/Helm 深度集成 |
| 社区 | 更大 | 次之 |

选型建议：
  - 需要 Web UI + 多集群管理 → ArgoCD
  - 深度依赖 Kustomize → Flux CD
  - 大厂常用（字节/腾讯） → ArgoCD 为主
```

---

## 第八章 实战速查

### 1 安装 ArgoCD

```shell
# 创建命名空间
$ kubectl create namespace argocd

# 安装（核心组件）
$ kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 暴露 Web UI
$ kubectl port-forward -n argocd svc/argocd-server 8080:443
# 浏览器打开 https://localhost:8080

# 获取初始密码
$ kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### 2 常用 CLI 命令

```shell
# ===== 登录 =====
$ argocd login localhost:8080 --username admin --password <password> --insecure

# ===== 应用管理 =====
$ argocd app list                                   # 查看所有应用
$ argocd app get my-app                             # 查看应用详情
$ argocd app create my-app --repo <url> --path <path> --dest-server <server> --dest-namespace <ns>
$ argocd app sync my-app                            # 手动同步
$ argocd app sync my-app --prune                    # 同步并删除多余资源
$ argocd app rollback my-app <revision-id>          # 回滚到指定版本
$ argocd app history my-app                         # 查看部署历史
$ argocd app diff my-app                            # 查看 Git 和集群的差异（不实际部署）
$ argocd app delete my-app                          # 删除应用
$ argocd app delete my-app --cascade                # 删除应用并清理集群资源

# ===== 集群管理 =====
$ argocd cluster list                               # 列出所有管理集群
$ argocd cluster add <cluster-name>                 # 注册新集群

# ===== 项目 =====
$ argocd proj list                                  # 列出项目
$ argocd proj create <project-name>                 # 创建项目

# ===== 调试 =====
$ argocd app manifests my-app                       # 查看渲染后的最终 YAML
$ argocd app logs my-app                            # 查看应用日志
$ argocd app wait my-app                            # 等待应用同步完成
```

### 3 常见排障

```shell
# 问题1：Application 一直 OutOfSync，但 kubectl apply 手动执行正常
# → 检查 ignoreDifferences 是否缺少某些自动注入字段
$ argocd app diff my-app

# 问题2：Sync 后仍然显示 Progressing
# → 检查 Pod 是否健康（Readiness Probe 是否通过）
$ argocd app get my-app --show-health
$ kubectl get pods -n <namespace> -l app=my-app

# 问题3：仓库连接失败
$ argocd repo list
$ argocd repo add git@git.internal:team/repo.git --ssh-private-key-path ~/.ssh/id_rsa

# 问题4：Application 删除不了（卡在 Terminating）
# → 手动移除 finalizer
$ kubectl patch app my-app -n argocd -p '{"metadata":{"finalizers":null}}' --type=merge
```

---

> **文档版本**: v1.0  
> **定位**：ArgoCD & GitOps 面试准备（概念 → 架构 → 多集群 → 同步策略 → 高频问答）  
> **适合**：ML SRE 面试中需要回答 GitOps/ArgoCD/多集群部署相关问题  
> **相关文档**：`ML_SRE_Interview_Guide.md` 第九章（多地域容灾与部署）、`K8s_Advanced.md`（K8s 进阶）
