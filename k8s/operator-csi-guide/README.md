# Kubernetes Operator & CSI 开发完整指南

> 从零到一开发 Kubernetes Operator 和 CSI 驱动，包含详细流程、代码示例、调试方法和生产建议。

---

## 目录

| 文档 | 内容 |
|---|---|
| [`01-operator-development.md`](./01-operator-development.md) | Operator 开发流程：CRD 定义 → Controller 实现 → 部署测试 → 生产加固 |
| [`02-csi-development.md`](./02-csi-development.md) | CSI 驱动开发流程：Identity → Controller → Node Plugin → 部署测试 |
| [`03-integration-testing.md`](./03-integration-testing.md) | 集成测试、调试方法、性能调优和故障场景验证 |
| [`04-interview-qa.md`](./04-interview-qa.md) | Operator / CSI 开发面试常见问题 |

## 示例代码

| 目录 | 说明 |
|---|---|
| [`examples/demo-operator/`](./examples/demo-operator/) | 完整 Operator 示例（kubebuilder）：`DemoTask` CRD + Controller |
| [`examples/demo-csi/`](./examples/demo-csi/) | 完整 CSI Driver 示例：Identity + Controller + Node Plugin |

## 快速开始

### Operator 示例

```shell
cd examples/demo-operator
# 生成 CRD manifests
make generate && make manifests
# 安装到集群
make install
# 运行（本地开发模式）
make run
# 创建测试资源
kubectl apply -f config/samples/demotask.yaml
```

### CSI Driver 示例

```shell
cd examples/demo-csi
# 构建
go build -o demo-csi-driver ./main.go
# 本地运行测试
./demo-csi-driver --endpoint=unix:///tmp/csi.sock --node-id=test-node --driver-name=demo-csi
```

## 前置知识

- Go 语言基础（interface、goroutine、channel、context）
- Kubernetes 核心概念（Pod、Deployment、DaemonSet、Service）
- kubebuilder / controller-runtime 基础
- gRPC 基础（CSI 以 gRPC 为通信协议）
- Linux 文件系统基础（mount、bind mount、overlayfs）

## 开发环境要求

- Go >= 1.21
- Docker / containerd
- kubectl + kind / minikube（本地 K8s 集群）
- kubebuilder（Operator 开发）
- protoc + protoc-gen-go + protoc-gen-go-grpc（CSI 开发，如需自定义 proto）
