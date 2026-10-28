# Operator / CSI 集成测试与调试

> 覆盖单元测试、envtest 集成测试、本地调试、CSI sanity 测试和生产故障场景。

---

## 一、Operator 测试

### 1.1 单元测试

`controllers/suite_test.go`（kubebuilder 自动生成，需要少量修改）：

```go
package controllers

import (
    "path/filepath"
    "testing"

    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    "k8s.io/client-go/kubernetes/scheme"
    "sigs.k8s.io/controller-runtime/pkg/client"
    "sigs.k8s.io/controller-runtime/pkg/envtest"
    logf "sigs.k8s.io/controller-runtime/pkg/log"
    "sigs.k8s.io/controller-runtime/pkg/log/zap"

    examplev1 "github.com/example/demo-operator/api/v1"
)

var (
    testEnv   *envtest.Environment
    k8sClient client.Client
)

func TestAPIs(t *testing.T) {
    RegisterFailHandler(Fail)
    RunSpecs(t, "Controller Suite")
}

var _ = BeforeSuite(func() {
    logf.SetLogger(zap.New(zap.WriteTo(GinkgoWriter), zap.UseDevMode(true)))

    // 启动 envtest（本地 API Server + etcd）
    testEnv = &envtest.Environment{
        CRDDirectoryPaths: []string{
            filepath.Join("..", "config", "crd", "bases"),
        },
        ErrorIfCRDPathMissing: true,
    }

    cfg, err := testEnv.Start()
    Expect(err).NotTo(HaveOccurred())
    Expect(cfg).NotTo(BeNil())

    // 注册 Scheme
    err = examplev1.AddToScheme(scheme.Scheme)
    Expect(err).NotTo(HaveOccurred())

    k8sClient, err = client.New(cfg, client.Options{Scheme: scheme.Scheme})
    Expect(err).NotTo(HaveOccurred())
    Expect(k8sClient).NotTo(BeNil())
})

var _ = AfterSuite(func() {
    if testEnv != nil {
        testEnv.Stop()
    }
})
```

`controllers/demotask_controller_test.go`：

```go
package controllers

import (
    "context"
    "time"

    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    batchv1 "k8s.io/api/batch/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/types"

    examplev1 "github.com/example/demo-operator/api/v1"
)

var _ = Describe("DemoTask Controller", func() {
    const (
        timeout  = time.Second * 30
        interval = time.Millisecond * 250
    )

    ctx := context.Background()

    It("Should create Jobs and update Status", func() {
        // 1. 创建 DemoTask CR
        demoTask := &examplev1.DemoTask{
            ObjectMeta: metav1.ObjectMeta{
                Name:      "test-task-1",
                Namespace: "default",
            },
            Spec: examplev1.DemoTaskSpec{
                Image:       "busybox:1.36",
                Command:     []string{"echo", "hello"},
                Completions: 2,
                Parallelism: 2,
            },
        }
        Expect(k8sClient.Create(ctx, demoTask)).Should(Succeed())

        // 2. 等待 Controller 创建 Job
        var jobList batchv1.JobList
        Eventually(func() int {
            k8sClient.List(ctx, &jobList)
            return len(jobList.Items)
        }, timeout, interval).Should(BeNumerically(">=", 2))

        // 3. 验证 Job 的 OwnerReference
        for _, job := range jobList.Items {
            Expect(job.OwnerReferences).Should(HaveLen(1))
            Expect(job.OwnerReferences[0].Kind).Should(Equal("DemoTask"))
        }

        // 4. 手动标记 Job 完成（模拟 Job Controller 行为）
        for i := range jobList.Items {
            jobList.Items[i].Status.Succeeded = 1
            k8sClient.Status().Update(ctx, &jobList.Items[i])
        }

        // 5. 验证 DemoTask Status 更新
        Eventually(func() string {
            var updated examplev1.DemoTask
            k8sClient.Get(ctx, types.NamespacedName{
                Name: "test-task-1", Namespace: "default"}, &updated)
            return updated.Status.Phase
        }, timeout, interval).Should(Equal("Succeeded"))

        Eventually(func() int32 {
            var updated examplev1.DemoTask
            k8sClient.Get(ctx, types.NamespacedName{
                Name: "test-task-1", Namespace: "default"}, &updated)
            return updated.Status.Succeeded
        }, timeout, interval).Should(Equal(int32(2)))

        // 6. 清理
        k8sClient.Delete(ctx, demoTask)
    })

    It("Should handle paused state", func() {
        demoTask := &examplev1.DemoTask{
            ObjectMeta: metav1.ObjectMeta{
                Name:      "test-task-paused",
                Namespace: "default",
            },
            Spec: examplev1.DemoTaskSpec{
                Image:       "busybox:1.36",
                Command:     []string{"sleep", "10"},
                Completions: 1,
                Paused:      true,
            },
        }
        Expect(k8sClient.Create(ctx, demoTask)).Should(Succeed())

        // 暂停状态下不应创建任何 Job
        Consistently(func() int {
            var jobs batchv1.JobList
            k8sClient.List(ctx, &jobs)
            return len(jobs.Items)
        }, time.Second*5, interval).Should(Equal(0))

        k8sClient.Delete(ctx, demoTask)
    })
})
```

运行测试：

```shell
# 需要先安装 envtest 二进制
make envtest

# 运行测试
make test

# 或
go test ./controllers/... -v
```

### 1.2 Fake Client 测试（快速验证）

```go
import (
    "sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func TestReconcile_Idempotent(t *testing.T) {
    scheme := runtime.NewScheme()
    _ = examplev1.AddToScheme(scheme)
    _ = batchv1.AddToScheme(scheme)

    demoTask := &examplev1.DemoTask{
        ObjectMeta: metav1.ObjectMeta{
            Name:      "test",
            Namespace: "default",
        },
        Spec: examplev1.DemoTaskSpec{
            Image: "busybox", Completions: 1,
        },
    }

    fakeClient := fake.NewClientBuilder().
        WithScheme(scheme).
        WithObjects(demoTask).
        WithStatusSubresource(demoTask).
        Build()

    r := &DemoTaskReconciler{Client: fakeClient, Scheme: scheme}

    // 第一次 Reconcile
    result, err := r.Reconcile(context.Background(), reconcile.Request{
        NamespacedName: types.NamespacedName{Name: "test", Namespace: "default"},
    })
    assert.NoError(t, err)

    // 验证创建了 Job
    var jobs batchv1.JobList
    fakeClient.List(context.Background(), &jobs)
    assert.Equal(t, 1, len(jobs.Items))

    // 第二次 Reconcile（幂等：不应重复创建）
    result, err = r.Reconcile(context.Background(), reconcile.Request{
        NamespacedName: types.NamespacedName{Name: "test", Namespace: "default"},
    })
    assert.NoError(t, err)

    fakeClient.List(context.Background(), &jobs)
    assert.Equal(t, 1, len(jobs.Items))  // 仍是 1 个
}
```

---

## 二、CSI 测试

### 2.1 CSI Sanity 测试

```shell
# 安装 csi-sanity
go install github.com/kubernetes-csi/csi-test/v5/cmd/csi-sanity@latest

# 启动 CSI 驱动（在一个终端）
sudo ./demo-csi-driver \
    --endpoint=unix:///tmp/csi.sock \
    --driver-name=demo.csi.example.com \
    --node-id=test-node

# 运行 sanity 测试（在另一个终端）
sudo csi-sanity \
    --csi.endpoint=unix:///tmp/csi.sock \
    --csi.testvolumeaccesstype=mount \
    --csi.testvolumeaccesstype=block \
    --ginkgo.v
```

### 2.2 手动测试脚本

```shell
#!/bin/bash
# test-csi.sh

CSI_ENDPOINT="unix:///tmp/csi.sock"
VOLUME_NAME="test-vol-$(date +%s)"

echo "=== 1. Identity 测试 ==="
csc identity plugin-info --endpoint "$CSI_ENDPOINT"

echo "=== 2. CreateVolume 测试 ==="
VOLUME_ID=$(csc controller create-volume \
    --endpoint "$CSI_ENDPOINT" \
    --cap 1,1 \
    --req-bytes 1073741824 \
    "$VOLUME_NAME" | jq -r '.volume.volume_id')
echo "Volume ID: $VOLUME_ID"

echo "=== 3. ControllerPublishVolume 测试 ==="
csc controller publish-volume \
    --endpoint "$CSI_ENDPOINT" \
    --node-id test-node \
    --cap 1,1 \
    "$VOLUME_ID"

echo "=== 4. NodeStageVolume 测试 ==="
STAGING_PATH="/tmp/csi-staging-$VOLUME_ID"
csc node stage-volume \
    --endpoint "$CSI_ENDPOINT" \
    --staging-target-path "$STAGING_PATH" \
    --cap 1,1 \
    "$VOLUME_ID"

echo "=== 5. NodePublishVolume 测试 ==="
TARGET_PATH="/tmp/csi-target-$VOLUME_ID"
csc node publish-volume \
    --endpoint "$CSI_ENDPOINT" \
    --staging-target-path "$STAGING_PATH" \
    --target-path "$TARGET_PATH" \
    --cap 1,1 \
    "$VOLUME_ID"

echo "=== 6. 写入测试 ==="
echo "CSI test data" | sudo tee "$TARGET_PATH/test.txt"

echo "=== 7. 卸载测试 ==="
csc node unpublish-volume \
    --endpoint "$CSI_ENDPOINT" \
    --target-path "$TARGET_PATH" \
    "$VOLUME_ID"

csc node unstage-volume \
    --endpoint "$CSI_ENDPOINT" \
    --staging-target-path "$STAGING_PATH" \
    "$VOLUME_ID"

echo "=== 8. ControllerUnpublishVolume 测试 ==="
csc controller unpublish-volume \
    --endpoint "$CSI_ENDPOINT" \
    --node-id test-node \
    "$VOLUME_ID"

echo "=== 9. DeleteVolume 测试 ==="
csc controller delete-volume \
    --endpoint "$CSI_ENDPOINT" \
    "$VOLUME_ID"

echo "=== All tests passed! ==="
```

---

## 三、调试技巧

### 3.1 Operator 调试

```shell
# 1. 查看 Controller 日志
kubectl logs -n demo-operator-system deploy/demo-operator-controller-manager -f

# 2. 提高日志级别
# 在 Deployment 中设置 --zap-log-level=debug
args:
  - "--zap-log-level=debug"
  - "--zap-devel=true"

# 3. 查看 Event
kubectl get events -n default --sort-by='.lastTimestamp' | tail -20

# 4. 检查 CRD 是否已注册
kubectl get crd demotasks.example.com -o yaml

# 5. 本地调试（使用 delve）
dlv debug ./main.go -- --metrics-bind-address=:8081

# 在 Controller 中打断点
# (dlv) break controllers/demotask_controller.go:50
# (dlv) continue
```

### 3.2 CSI 调试

```shell
# 1. 检查 Node Plugin 日志
kubectl logs -n demo-csi daemonset/demo-csi-node -c csi-node -f

# 2. 检查 Controller Plugin 日志
kubectl logs -n demo-csi statefulset/demo-csi-controller -c csi-controller -f

# 3. 检查 sidecar 日志
kubectl logs -n demo-csi daemonset/demo-csi-node -c node-driver-registrar

# 4. 检查 socket 文件
kubectl exec -n demo-csi daemonset/demo-csi-node -c csi-node -- ls -la /csi/

# 5. 检查 kubelet 插件注册
ls -la /var/lib/kubelet/plugins_registry/
cat /var/lib/kubelet/plugins_registry/demo.csi.example.com-reg.sock
```

### 3.3 常见问题

#### Operator

| 问题 | 排查方向 |
|---|---|
| CRD 已创建但 `kubectl get` 没有资源 | 检查 CRD 的 `scope`（Namespaced vs Cluster）和 `names.plural` |
| Controller 不触发 | 检查 `SetupWithManager` 的 RBAC、filter、Watch 链路 |
| Reconcile 死循环 | 检查是否在 Reconcile 中对 CR 做了 `Update()` 而非 `Status().Update()` |
| `AlreadyExists` 错误 | 检查 ObjectKey 生成逻辑，使用 `IsAlreadyExists` 处理 |
| `No match for kind` 错误 | CRD 还未完全注册，等待几秒或检查 `Established` condition |

#### CSI

| 问题 | 排查方向 |
|---|---|
| `failed to get plugin info` | socket 路径不正确、插件未启动、权限问题 |
| `Volume not found` | 驱动重启后内存状态丢失，需持久化 volume metadata |
| `mount failed` | Node Plugin 需要 `privileged: true` 和 `Bidirectional` mount propagation |
| `ControllerPublishVolume timeout` | Controller 与 Node 不在同一节点，检查网络和 gRPC 超时 |
| `PVC stuck in Pending` | StorageClass 的 `volumeBindingMode: WaitForFirstConsumer` 需要 Pod 先调度 |

---

## 四、性能与压力测试

### 4.1 Operator 压测

```go
// 创建大量 DemoTask
func BenchmarkDemoTaskController(b *testing.B) {
    for i := 0; i < b.N; i++ {
        task := &examplev1.DemoTask{
            ObjectMeta: metav1.ObjectMeta{
                Name:      fmt.Sprintf("bench-task-%d", i),
                Namespace: "default",
            },
            Spec: examplev1.DemoTaskSpec{
                Image:       "busybox:1.36",
                Command:     []string{"echo", "ok"},
                Completions: 1,
            },
        }
        k8sClient.Create(ctx, task)
    }
}
```

### 4.2 监控 Controller 性能

```promql
# Reconcile 速率
rate(controller_runtime_reconcile_total{controller="demotask"}[5m])

# Reconcile 延迟 P99
histogram_quantile(0.99,
  rate(controller_runtime_reconcile_time_seconds_bucket{controller="demotask"}[5m]))

# WorkQueue 深度
workqueue_depth{name="demotask"}

# WorkQueue 延迟
histogram_quantile(0.99,
  rate(workqueue_queue_duration_seconds_bucket{name="demotask"}[5m]))
```

### 4.3 CSI 性能观察

```shell
# 测量单次 mount 耗时
time csc node publish-volume \
    --endpoint unix:///tmp/csi.sock \
    --staging-target-path /tmp/staging \
    --target-path /tmp/publish \
    --cap 1,1 \
    <volume-id>

# 并发 mount 测试
for i in $(seq 1 100); do
    (
        csc node publish-volume \
            --endpoint unix:///tmp/csi.sock \
            --staging-target-path "/tmp/staging-$i" \
            --target-path "/tmp/publish-$i" \
            --cap 1,1 \
            <volume-id> &
    )
done
wait

# 验证所有 mount 点
mount | grep /tmp/publish- | wc -l
```
