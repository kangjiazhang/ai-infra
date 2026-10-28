# Kubernetes Operator 开发完整流程

> 基于 kubebuilder，从零开发一个 `DemoTask` Operator。
>
> 最终效果：用户提交 `DemoTask` CR → Controller 创建 Job → 更新 Status 反馈执行结果。

---

## 一、Operator 开发总览

### 1.1 什么是 Operator

```
Operator = CRD (自定义资源定义) + Controller (控制器)
                │                          │
          扩展 K8s API              实现 Reconcile 调和循环
          声明资源结构               持续将实际状态驱动为期望状态
```

### 1.2 开发流程（7 步）

```
Step 1: 初始化项目     → kubebuilder init
Step 2: 创建 API       → kubebuilder create api (生成 CRD + Controller 骨架)
Step 3: 定义 CRD 字段   → api/v1/<kind>_types.go
Step 4: 实现 Controller → controllers/<kind>_controller.go
Step 5: 生成代码和清单  → make generate && make manifests
Step 6: 本地测试        → make install && make run
Step 7: 部署上线        → make docker-build && make deploy
```

### 1.3 核心技术栈

| 组件 | 作用 |
|---|---|
| **kubebuilder** | 脚手架工具，生成 CRD、Controller、RBAC 骨架 |
| **controller-runtime** | 运行时库，提供 Manager、Reconcile、Informer、WorkQueue |
| **client-go** | K8s API 客户端，List/Get/Create/Update/Delete/Watch |
| **apiextensions-apiserver** | CRD 注册和校验 |

---

## 二、Step 1：初始化项目

```shell
# 创建项目目录
mkdir demo-operator && cd demo-operator

# 初始化 Go module 和 kubebuilder 项目
kubebuilder init \
    --domain example.com \
    --repo github.com/example/demo-operator \
    --owner "demo-team"

# 项目结构：
# ├── Dockerfile
# ├── Makefile
# ├── PROJECT           # kubebuilder 项目元数据
# ├── config/
# │   ├── crd/          # CRD YAML
# │   ├── rbac/         # RBAC 配置
# │   ├── manager/      # Controller Manager Deployment
# │   ├── default/      # kustomize overlay
# │   └── samples/      # CR 示例
# ├── go.mod
# ├── go.sum
# └── main.go           # 入口
```

---

## 三、Step 2：创建 API（CRD + Controller 骨架）

```shell
kubebuilder create api \
    --group example --version v1 --kind DemoTask \
    --resource --controller

# 生成文件：
# api/v1/demotask_types.go          ← CRD 字段定义（需要手动编写）
# api/v1/groupversion_info.go       ← API Group/Version 注册
# api/v1/zz_generated.deepcopy.go   ← 自动生成的 DeepCopy 方法
# controllers/demotask_controller.go ← Controller 实现（需要手动编写）
```

---

## 四、Step 3：定义 CRD 字段

编辑 `api/v1/demotask_types.go`：

```go
package v1

import (
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status

// DemoTask 是示例任务 API
type DemoTask struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`

    Spec   DemoTaskSpec   `json:"spec,omitempty"`
    Status DemoTaskStatus `json:"status,omitempty"`
}

// DemoTaskSpec 定义期望状态
type DemoTaskSpec struct {
    // Image 指定容器镜像（必填）
    // +kubebuilder:validation:Required
    // +kubebuilder:validation:MinLength=1
    Image string `json:"image"`

    // Command 指定容器命令
    // +kubebuilder:validation:MinItems=1
    Command []string `json:"command,omitempty"`

    // Completions 需要成功完成的次数
    // +kubebuilder:validation:Minimum=1
    // +kubebuilder:default:=1
    Completions int32 `json:"completions,omitempty"`

    // Parallelism 并发执行数
    // +kubebuilder:validation:Minimum=1
    // +kubebuilder:default:=1
    Parallelism int32 `json:"parallelism,omitempty"`

    // BackoffLimit 失败重试上限
    // +kubebuilder:validation:Minimum=0
    // +kubebuilder:default:=6
    BackoffLimit int32 `json:"backoffLimit,omitempty"`

    // TTLSecondsAfterFinished 完成后保留时间（秒），0 表示不自动清理
    // +kubebuilder:default:=3600
    TTLSecondsAfterFinished int32 `json:"ttlSecondsAfterFinished,omitempty"`

    // Paused 是否暂停执行
    // +kubebuilder:default:=false
    Paused bool `json:"paused,omitempty"`
}

// DemoTaskStatus 定义实际状态
type DemoTaskStatus struct {
    // Phase 当前阶段：Pending / Running / Succeeded / Failed
    // +kubebuilder:validation:Enum=Pending;Running;Succeeded;Failed
    Phase string `json:"phase,omitempty"`

    // Succeeded 成功完成的 Pod 数
    Succeeded int32 `json:"succeeded,omitempty"`

    // Failed 失败的 Pod 数
    Failed int32 `json:"failed,omitempty"`

    // Active 正在运行的 Pod 数
    Active int32 `json:"active,omitempty"`

    // StartTime 任务启动时间
    StartTime *metav1.Time `json:"startTime,omitempty"`

    // CompletionTime 任务完成时间
    CompletionTime *metav1.Time `json:"completionTime,omitempty"`

    // Conditions 详细状态条件
    // +patchMergeKey=type
    // +patchStrategy=merge
    Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`
}

// +kubebuilder:object:root=true
type DemoTaskList struct {
    metav1.TypeMeta `json:",inline"`
    metav1.ListMeta `json:"metadata,omitempty"`
    Items           []DemoTask `json:"items"`
}

func init() {
    SchemeBuilder.Register(&DemoTask{}, &DemoTaskList{)
}
```

### 关键注解说明

| 注解 | 作用 |
|---|---|
| `+kubebuilder:object:root=true` | 标记为 K8s 资源根类型 |
| `+kubebuilder:subresource:status` | 启用 `/status` 子资源 |
| `+kubebuilder:validation:Required` | 必填字段 |
| `+kubebuilder:validation:Minimum=1` | 最小值校验 |
| `+kubebuilder:default:=1` | 设置默认值 |
| `+kubebuilder:printcolumn` | `kubectl get` 可见列 |

编辑 `api/v1/groupversion_info.go`，确保 Scheme 正确注册：

```go
package v1

import (
    "k8s.io/apimachinery/pkg/runtime/schema"
    "sigs.k8s.io/controller-runtime/pkg/scheme"
)

var (
    GroupVersion = schema.GroupVersion{
        Group: "example.com", Version: "v1"}
    SchemeBuilder = &scheme.Builder{GroupVersion: GroupVersion}
    AddToScheme   = SchemeBuilder.AddToScheme
)
```

---

## 五、Step 4：实现 Controller

### 5.1 Controller 核心架构

```
┌─────────────────────────────────────────────────────┐
│                  Controller                          │
│                                                     │
│  API Server ──Watch──▶ Informer ──Event──▶        │
│                                          WorkQueue  │
│                                             │       │
│                                        ┌────▼───┐  │
│                                        │ Worker │  │
│                                        │ Pool   │  │
│                                        └────┬───┘  │
│                                             │       │
│                                    Reconcile(key)   │
│                                         │           │
│                               ┌─────────▼────────┐  │
│                               │ 1. Get CR         │  │
│                               │ 2. Get Job (实际) │  │
│                               │ 3. Compare 差异   │  │
│                               │ 4. Create/Update  │  │
│                               │ 5. Update Status  │  │
│                               └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 5.2 实现 Reconcile

编辑 `controllers/demotask_controller.go`：

```go
package controllers

import (
    "context"
    "fmt"
    "time"

    batchv1 "k8s.io/api/batch/v1"
    corev1 "k8s.io/api/core/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/runtime"
    "k8s.io/client-go/tools/record"
    ctrl "sigs.k8s.io/controller-runtime"
    "sigs.k8s.io/controller-runtime/pkg/client"
    "sigs.k8s.io/controller-runtime/pkg/controller"
    "sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
    "sigs.k8s.io/controller-runtime/pkg/event"
    "sigs.k8s.io/controller-runtime/pkg/handler"
    "sigs.k8s.io/controller-runtime/pkg/log"
    "sigs.k8s.io/controller-runtime/pkg/predicate"
    "sigs.k8s.io/controller-runtime/pkg/reconcile"
    "sigs.k8s.io/controller-runtime/pkg/source"

    examplev1 "github.com/example/demo-operator/api/v1"
)

const demoTaskFinalizer = "example.com/demotask-finalizer"

// DemoTaskReconciler 调和 DemoTask 与底层 Job
type DemoTaskReconciler struct {
    client.Client
    Scheme   *runtime.Scheme
    Recorder record.EventRecorder
}

// +kubebuilder:rbac:groups=example.com,resources=demotasks,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=example.com,resources=demotasks/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=example.com,resources=demotasks/finalizers,verbs=update
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

func (r *DemoTaskReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    logger.Info("开始 Reconcile", "name", req.NamespacedName)

    // ========== 1. 获取 DemoTask CR ==========
    var demoTask examplev1.DemoTask
    if err := r.Get(ctx, req.NamespacedName, &demoTask); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // ========== 2. 处理 Finalizer（CR 删除时清理） ==========
    if !demoTask.DeletionTimestamp.IsZero() {
        return r.handleFinalizer(ctx, &demoTask)
    }

    // 注册 finalizer
    if !controllerutil.ContainsFinalizer(&demoTask, demoTaskFinalizer) {
        controllerutil.AddFinalizer(&demoTask, demoTaskFinalizer)
        if err := r.Update(ctx, &demoTask); err != nil {
            return ctrl.Result{}, err
        }
    }

    // ========== 3. 检查暂停 ==========
    if demoTask.Spec.Paused {
        logger.Info("DemoTask 已暂停，跳过调和")
        return ctrl.Result{}, nil
    }

    // ========== 4. 查找已有的 Job ==========
    var childJobs batchv1.JobList
    if err := r.List(ctx, &childJobs,
        client.InNamespace(req.Namespace),
        client.MatchingLabels{"demotask.example.com/name": demoTask.Name},
    ); err != nil {
        return ctrl.Result{}, err
    }

    // ========== 5. 统计当前状态 ==========
    var activeJobs []*batchv1.Job
    var succeededJobs, failedJobs int32 = 0, 0

    for i := range childJobs.Items {
        job := &childJobs.Items[i]
        if job.Status.Succeeded > 0 {
            succeededJobs++
        } else if job.Status.Failed > 0 {
            failedJobs++
        } else if job.Status.Active > 0 {
            activeJobs = append(activeJobs, job)
        }
    }

    logger.Info("Job 状态统计",
        "succeeded", succeededJobs,
        "failed", failedJobs,
        "active", len(activeJobs),
    )

    // ========== 6. 更新 Status ==========
    if demoTask.Status.StartTime == nil {
        now := metav1.Now()
        demoTask.Status.StartTime = &now
    }
    demoTask.Status.Succeeded = succeededJobs
    demoTask.Status.Failed = failedJobs
    demoTask.Status.Active = int32(len(activeJobs))

    // ========== 7. 判断任务完成 ==========
    totalFinished := succeededJobs + failedJobs

    if succeededJobs >= demoTask.Spec.Completions {
        // 全部成功
        demoTask.Status.Phase = "Succeeded"
        now := metav1.Now()
        demoTask.Status.CompletionTime = &now
        if err := r.Status().Update(ctx, &demoTask); err != nil {
            return ctrl.Result{}, err
        }
        r.Recorder.Eventf(&demoTask, corev1.EventTypeNormal, "Completed",
            "DemoTask %s completed: %d/%d succeeded", demoTask.Name, succeededJobs, demoTask.Spec.Completions)
        return ctrl.Result{}, nil
    }

    if failedJobs > 0 && totalFinished >= demoTask.Spec.Completions+failedJobs {
        // 失败数量超过预期
        demoTask.Status.Phase = "Failed"
        if err := r.Status().Update(ctx, &demoTask); err != nil {
            return ctrl.Result{}, err
        }
        r.Recorder.Eventf(&demoTask, corev1.EventTypeWarning, "Failed",
            "DemoTask %s failed: %d failed, %d succeeded", demoTask.Name, failedJobs, succeededJobs)
        return ctrl.Result{}, nil
    }

    // ========== 8. 创建新 Job ==========
    if totalFinished+int32(len(activeJobs)) < demoTask.Spec.Completions {
        // 计算需要创建的 Job 数量
        remaining := demoTask.Spec.Completions - totalFinished - int32(len(activeJobs))
        createCount := min(remaining, demoTask.Spec.Parallelism-int32(len(activeJobs)))

        for i := int32(0); i < createCount; i++ {
            job := r.buildJob(&demoTask)
            if err := r.Create(ctx, job); err != nil {
                logger.Error(err, "创建 Job 失败")
                return ctrl.Result{}, err
            }
            logger.Info("创建 Job", "jobName", job.Name)
        }

        demoTask.Status.Phase = "Running"
    }

    if err := r.Status().Update(ctx, &demoTask); err != nil {
        return ctrl.Result{}, err
    }

    // ========== 9. 重新入队检查 ==========
    // 如果还有活跃 Job，5 秒后重新检查
    if demoTask.Status.Active > 0 || demoTask.Status.Phase == "Running" {
        return ctrl.Result{RequeueAfter: 5 * time.Second}, nil
    }

    return ctrl.Result{}, nil
}

// buildJob 根据 DemoTask 构建 Job 对象
func (r *DemoTaskReconciler) buildJob(demoTask *examplev1.DemoTask) *batchv1.Job {
    jobName := fmt.Sprintf("%s-%d", demoTask.Name, time.Now().UnixNano()%100000)

    completions := int32(1)
    backoffLimit := demoTask.Spec.BackoffLimit
    ttlSeconds := demoTask.Spec.TTLSecondsAfterFinished

    job := &batchv1.Job{
        ObjectMeta: metav1.ObjectMeta{
            Name:      jobName,
            Namespace: demoTask.Namespace,
            Labels: map[string]string{
                "demotask.example.com/name": demoTask.Name,
                "app.kubernetes.io/created-by": "demo-operator",
            },
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(demoTask, examplev1.GroupVersion.WithKind("DemoTask")),
            },
        },
        Spec: batchv1.JobSpec{
            Completions:            &completions,
            Parallelism:            &completions,
            BackoffLimit:           &backoffLimit,
            TTLSecondsAfterFinished: &ttlSeconds,
            Template: corev1.PodTemplateSpec{
                Spec: corev1.PodSpec{
                    RestartPolicy: corev1.RestartPolicyNever,
                    Containers: []corev1.Container{
                        {
                            Name:    "worker",
                            Image:   demoTask.Spec.Image,
                            Command: demoTask.Spec.Command,
                        },
                    },
                },
            },
        },
    }
    return job
}

// handleFinalizer 处理 CR 删除时的清理逻辑
func (r *DemoTaskReconciler) handleFinalizer(ctx context.Context, demoTask *examplev1.DemoTask) (ctrl.Result, error) {
    logger := log.FromContext(ctx)

    if controllerutil.ContainsFinalizer(demoTask, demoTaskFinalizer) {
        // 执行清理逻辑：删除所有子 Job
        var childJobs batchv1.JobList
        if err := r.List(ctx, &childJobs,
            client.InNamespace(demoTask.Namespace),
            client.MatchingLabels{"demotask.example.com/name": demoTask.Name},
        ); err != nil {
            return ctrl.Result{}, err
        }

        for i := range childJobs.Items {
            if err := r.Delete(ctx, &childJobs.Items[i]); err != nil {
                logger.Error(err, "清理子 Job 失败", "job", childJobs.Items[i].Name)
                return ctrl.Result{}, err
            }
        }

        // 移除 finalizer，允许 K8s 完成删除
        controllerutil.RemoveFinalizer(demoTask, demoTaskFinalizer)
        if err := r.Update(ctx, demoTask); err != nil {
            return ctrl.Result{}, err
        }
    }
    return ctrl.Result{}, nil
}

// SetupWithManager 设置 Controller 与 Manager 的关联
func (r *DemoTaskReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&examplev1.DemoTask{}).                          // 监听的主资源
        Owns(&batchv1.Job{}).                                 // 监听拥有的子资源
        WithOptions(controller.Options{
            MaxConcurrentReconciles: 4,                       // 并发 Worker 数量
        }).
        WithEventFilter(predicate.Funcs{
            // 过滤 Update 事件：只在 Spec 变化时触发
            UpdateFunc: func(e event.UpdateEvent) bool {
                oldTask := e.ObjectOld.(*examplev1.DemoTask)
                newTask := e.ObjectNew.(*examplev1.DemoTask)
                // Generation 只在 Spec 变化时递增
                return oldTask.Generation != newTask.Generation
            },
            // 过滤 Delete 事件
            DeleteFunc: func(e event.DeleteEvent) bool {
                return false // Delete 由 finalizer 处理，不需要单独触发
            },
        }).
        Complete(r)
}

// 工具函数
func min(a, b int32) int32 {
    if a < b {
        return a
    }
    return b
}
```

### 5.3 入口文件

`main.go`：

```go
package main

import (
    "flag"
    "os"

    "k8s.io/apimachinery/pkg/runtime"
    utilruntime "k8s.io/apimachinery/pkg/util/runtime"
    clientgoscheme "k8s.io/client-go/kubernetes/scheme"
    ctrl "sigs.k8s.io/controller-runtime"
    "sigs.k8s.io/controller-runtime/pkg/log/zap"

    examplev1 "github.com/example/demo-operator/api/v1"
    "github.com/example/demo-operator/controllers"
)

var scheme = runtime.NewScheme()

func init() {
    utilruntime.Must(clientgoscheme.AddToScheme(scheme))
    utilruntime.Must(examplev1.AddToScheme(scheme))
}

func main() {
    var metricsAddr string
    var enableLeaderElection bool
    var probeAddr string
    flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "metrics 绑定地址")
    flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "健康检查绑定地址")
    flag.BoolVar(&enableLeaderElection, "leader-elect", false,
        "启用 Leader Election（多副本部署时需要）")
    flag.Parse()

    ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

    mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
        Scheme:                 scheme,
        MetricsBindAddress:     metricsAddr,
        Port:                   9443,
        HealthProbeBindAddress: probeAddr,
        LeaderElection:         enableLeaderElection,
        LeaderElectionID:       "demotask-leader.example.com",
    })
    if err != nil {
        ctrl.Log.Error(err, "创建 Manager 失败")
        os.Exit(1)
    }

    if err = (&controllers.DemoTaskReconciler{
        Client:   mgr.GetClient(),
        Scheme:   mgr.GetScheme(),
        Recorder: mgr.GetEventRecorderFor("demotask-controller"),
    }).SetupWithManager(mgr); err != nil {
        ctrl.Log.Error(err, "注册 Controller 失败")
        os.Exit(1)
    }

    ctrl.Log.Info("启动 Manager")
    if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
        ctrl.Log.Error(err, "Manager 运行失败")
        os.Exit(1)
    }
}
```

---

## 六、Step 5：生成代码和清单

```shell
# 重新生成 DeepCopy 和 CRD YAML
make generate
make manifests

# 生成的文件：
# api/v1/zz_generated.deepcopy.go          ← 不可手动编辑
# config/crd/bases/example.com_demotasks.yaml  ← CRD 定义
# config/rbac/role.yaml                    ← RBAC 规则
```

生成的 CRD YAML 关键部分示例（`config/crd/bases/example.com_demotasks.yaml`）：

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: demotasks.example.com
spec:
  group: example.com
  names:
    kind: DemoTask
    plural: demotasks
    singular: demotask
    shortNames:
      - dt
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      subresources:
        status: {}
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [image]
              properties:
                image:
                  type: string
                  minLength: 1
                command:
                  type: array
                  minItems: 1
                  items:
                    type: string
                completions:
                  type: integer
                  minimum: 1
                  default: 1
                parallelism:
                  type: integer
                  minimum: 1
                  default: 1
                backoffLimit:
                  type: integer
                  minimum: 0
                  default: 6
                ttlSecondsAfterFinished:
                  type: integer
                  default: 3600
                paused:
                  type: boolean
                  default: false
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: [Pending, Running, Succeeded, Failed]
                succeeded:
                  type: integer
                failed:
                  type: integer
                active:
                  type: integer
                startTime:
                  type: string
                  format: date-time
                completionTime:
                  type: string
                  format: date-time
```

---

## 七、Step 6：本地测试

### 7.1 安装 CRD

```shell
# 安装 CRD 到集群
make install

# 验证
kubectl get crd demotasks.example.com
```

### 7.2 本地运行 Controller

```shell
# 本地运行（通过 kubeconfig 连接集群）
make run

# 或带参数运行
go run main.go \
    --metrics-bind-address=:8080 \
    --health-probe-bind-address=:8081
```

### 7.3 创建测试 CR

创建 `config/samples/demotask.yaml`：

```yaml
apiVersion: example.com/v1
kind: DemoTask
metadata:
  name: demo-task-test
spec:
  image: busybox:1.36
  command:
    - sh
    - -c
    - "echo 'Hello from DemoTask!' && sleep 5 && echo 'Done!'"
  completions: 2
  parallelism: 2
  backoffLimit: 3
  ttlSecondsAfterFinished: 120
```

```shell
# 创建 DemoTask
kubectl apply -f config/samples/demotask.yaml

# 观察状态
kubectl get demotasks -w
kubectl describe demotask demo-task-test

# 查看自动创建的 Job
kubectl get jobs -l demotask.example.com/name=demo-task-test

# 查看 Job 下的 Pod
kubectl get pods -l demotask.example.com/name=demo-task-test

# 查看 Pod 日志
kubectl logs -l demotask.example.com/name=demo-task-test
```

### 7.4 验证状态更新

```shell
# DemoTask Status 应包含执行结果
kubectl get demotask demo-task-test -o yaml | grep -A10 status

# 预期输出：
# status:
#   phase: Succeeded
#   succeeded: 2
#   failed: 0
#   active: 0
#   startTime: "..."
#   completionTime: "..."
```

### 7.5 测试暂停功能

```shell
# 暂停
kubectl patch demotask demo-task-test --type=merge \
    -p '{"spec":{"paused":true}}'

# 恢复
kubectl patch demotask demo-task-test --type=merge \
    -p '{"spec":{"paused":false}}'
```

### 7.6 测试删除清理

```shell
# 删除 DemoTask，Finalizer 会自动清理子 Job
kubectl delete demotask demo-task-test

# 确认 Job 也被清理
kubectl get jobs -l demotask.example.com/name=demo-task-test
# 应返回：No resources found
```

---

## 八、Step 7：部署上线

### 8.1 构建镜像

```shell
# 构建 Docker 镜像
make docker-build IMG=registry.example.com/demo-operator:v1.0.0

# 推送到镜像仓库
make docker-push IMG=registry.example.com/demo-operator:v1.0.0
```

### 8.2 部署到集群

```shell
# 部署（会创建 Deployment、RBAC 等）
make deploy IMG=registry.example.com/demo-operator:v1.0.0

# 验证
kubectl get deploy -n demo-operator-system
kubectl get pods -n demo-operator-system
kubectl logs -n demo-operator-system deploy/demo-operator-controller-manager
```

### 8.3 多副本与 Leader Election

```yaml
# config/manager/manager.yaml 中设置
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: manager
          args:
            - "--leader-elect"              # 启用 Leader Election
            - "--metrics-bind-address=:8080"
```

---

## 九、Operator 开发关键检查点

### 9.1 幂等性

```go
// ✅ 正确：使用确定性名称 + AlreadyExists 处理
job := r.buildJob(demoTask, index)
job.Name = fmt.Sprintf("%s-%d", demoTask.Name, index)
if err := r.Create(ctx, job); err != nil {
    if !apierrors.IsAlreadyExists(err) {
        return ctrl.Result{}, err
    }
    // 已存在则跳过
}

// ✅ 正确：先 Get 再判断是否需要 Update
var existing batchv1.Job
if err := r.Get(ctx, client.ObjectKey{...}, &existing); err == nil {
    // 已存在，比较是否需要更新
    if needsUpdate(&existing, job) {
        r.Update(ctx, &existing)
    }
} else if apierrors.IsNotFound(err) {
    r.Create(ctx, job)
}
```

### 9.2 并发安全

```go
// ✅ 使用 WorkQueue，天然支持并发 Worker
// Reconcile 内部不要依赖共享内存状态
// 所有状态从 API Server 读取

// ❌ 错误：使用全局 map 缓存状态
var taskCache = make(map[string]*TaskState)  // Reconcile 间会数据竞争
```

### 9.3 OwnerReference

```go
// 子资源设置 OwnerReference → 父资源删除时自动清理
ownerRef := metav1.NewControllerRef(
    demoTask,
    examplev1.GroupVersion.WithKind("DemoTask"),
)
job.ObjectMeta.OwnerReferences = []metav1.OwnerReference{*ownerRef}
```

### 9.4 Event 和 Condition

```go
// 记录 Event（用户通过 kubectl describe 可见）
r.Recorder.Eventf(demoTask, corev1.EventTypeNormal, "JobCreated",
    "Created Job %s", job.Name)

// 更新 Condition（结构化状态）
meta.SetStatusCondition(&demoTask.Status.Conditions, metav1.Condition{
    Type:               "Progressing",
    Status:             metav1.ConditionTrue,
    Reason:             "JobsRunning",
    Message:            fmt.Sprintf("%d/%d jobs running", active, spec.Completions),
    ObservedGeneration: demoTask.Generation,
})
```

### 9.5 指标（Metrics）

```go
import (
    "sigs.k8s.io/controller-runtime/pkg/metrics"
    "github.com/prometheus/client_golang/prometheus"
)

var (
    reconcileTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "demotask_controller_reconcile_total",
            Help: "Reconcile 总次数",
        },
        []string{"result"},  // "success" / "error"
    )
    reconcileDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "demotask_controller_reconcile_duration_seconds",
            Help:    "Reconcile 耗时分布",
            Buckets: prometheus.DefBuckets,
        },
        []string{},
    )
)

func init() {
    metrics.Registry.MustRegister(reconcileTotal, reconcileDuration)
}
```

---

## 十、完整代码文件清单

参见 `examples/demo-operator/` 目录：

```
examples/demo-operator/
├── PROJECT
├── Makefile
├── go.mod
├── main.go                              # 入口
├── api/v1/
│   ├── demotask_types.go                # CRD 类型定义
│   └── groupversion_info.go             # API 注册
├── controllers/
│   ├── demotask_controller.go           # Controller 实现
│   └── suite_test.go                    # 测试
└── config/
    ├── crd/bases/
    │   └── example.com_demotasks.yaml   # CRD YAML
    ├── rbac/
    │   └── role.yaml                    # RBAC
    └── samples/
        └── demotask.yaml                # CR 示例
```
