# Operator / CSI 开发面试常见问题

---

## 一、Operator 开发

### Q1：Controller 的 Reconcile 循环是如何被触发的？

```
触发链路：

方式 1：Informer Watch 到 CR 变化
  API Server ──Watch──▶ Informer ──EventHandler──▶ WorkQueue.Add(key)
                                                    │
                                               Worker.Pop(key)
                                                    │
                                               Reconcile(key)

方式 2：Owns 的子资源变化
  Job 被创建/更新/删除 ──▶ OwnerReference 关联父 CR
                          │
                     └──▶ 触发父 CR 的 Reconcile

方式 3：定时 Requeue
  Reconcile 返回 ctrl.Result{RequeueAfter: 5 * time.Second}

方式 4：外部事件
  channel / webhook 等自定义触发源
```

### Q2：如何保证 Reconcile 幂等？

```
1. 不依赖事件内容，始终以 API Server 当前状态为准重新计算
2. 创建操作使用确定性名称 + 处理 AlreadyExists
3. 更新操作先 Get 再 Compare 再 Update（不是盲目 Update）
4. 状态存储在 Status 中，Spec 和 Status 共同定义检查点
5. 对外部 API 调用记录幂等键或 task ID，防止重复调用
```

### Q3：Update 事件为什么会触发死循环？

```
原因：Reconcile 内部调用 r.Update(ctx, cr) → API Server 产生 Update 事件
→ Informer 收到事件 → 再次入队 → 再次 Reconcile → 再次 Update → 死循环

解决：
1. 只调用 r.Status().Update()，不要调用 r.Update()（Status 变化不触发 Spec 事件）
2. 使用 GenerationChangedPredicate 过滤 Status-only 的 Update
3. 比较新旧对象，只在字段真正变化时才 Update
```

### Q4：如何处理多个 Controller 副本同时运行？

```
1. 启用 Leader Election：
   --leader-elect=true --leader-election-id=my-controller

2. controller-runtime 的 Leader Election 基于 Lease 资源
   - 同一时刻只有 Leader 执行 Reconcile
   - Follower 空闲等待，Leader 宕机后接管
   - 切换时间：LeaseDuration 15s + RetryPeriod 2s ≈ 17s

3. 即使有 Leader Election，Reconcile 仍要幂等
   - 网络分区可能导致双 Leader（split-brain）
   - Leader 切换时上一个 Leader 的事务可能还在执行
```

### Q5：Finalizer 的作用和注意事项？

```
作用：
1. 阻止 K8s 立即删除资源（DeletionTimestamp 置为非零，但 CR 不消失）
2. 让 Controller 在删除前完成清理（外部资源、子资源、缓存等）
3. 清理完成后 Controller 移除 finalizer → K8s 完成删除

注意事项：
- 必须为每个 CR 类型注册 finalizer
- 清理逻辑必须可重入（移除失败可重试）
- 必须设置超时和告警（Controller 故障导致资源卡在 Terminating）
- 不要持有 finalizer 太久
- 实现 DryRun 或 admin 清理工具作为兜底
```

### Q6：如何处理 Operator 的 CRD 版本升级？

```yaml
# CRD 支持多版本（Conversion）
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
spec:
  versions:
    - name: v1alpha1
      served: true
      storage: false
      deprecated: true
    - name: v1
      served: true
      storage: true
  conversion:
    strategy: Webhook
    webhook:
      conversionReviewVersions: ["v1"]
      clientConfig:
        service:
          name: demo-operator-webhook
          namespace: demo-operator-system
          path: /convert
```

```go
// Webhook 实现版本转换
func (h *ConversionHandler) Convert(
    req *apiextensionsv1.ConversionRequest) *apiextensionsv1.ConversionResponse {
    // v1alpha1 → v1 转换逻辑
    // v1 → v1alpha1 转换逻辑
}
```

---

## 二、CSI 开发

### Q7：NodeStageVolume 和 NodePublishVolume 有什么区别？

```
NodeStageVolume（节点级）：
  - 将卷挂载到节点全局路径（staging_target_path）
  - 同一节点上的多个 Pod 可以共享这个挂载
  - 只在第一次被该节点上 Pod 引用时调用
  - 适合：格式化文件系统、设置权限

NodePublishVolume（Pod 级）：
  - 将 staging 路径 bind mount 到 Pod 的 target_path
  - 每个引用该卷的 Pod 都会调用一次
  - 适合：只读/读写控制、subPath 处理

卸载顺序相反：
  NodeUnpublishVolume → NodeUnstageVolume
```

### Q8：CSI 驱动的幂等性如何保证？

```
每个 Node 操作都有标准幂等检查：

NodeStageVolume:
  → 检查 staging_target_path 是否已是挂载点 → 是则返回成功

NodePublishVolume:
  → 检查 target_path 是否已是挂载点 → 是则返回成功

NodeUnpublishVolume:
  → 检查 target_path 是否已不是挂载点 → 是则返回成功

ControllerCreateVolume:
  → 检查 volume_id 是否已存在 → 是则返回已有信息
  → 或使用幂等 name → volume_id 映射

关键：不能仅靠内存状态判断，必须查询实际挂载表（/proc/mounts）
```

### Q9：Node Plugin 为什么必须 privileged？

```
Node Plugin 需要执行的操作：
1. mount / umount 系统调用（需要 CAP_SYS_ADMIN）
2. 访问 /dev 设备文件
3. 操作 /var/lib/kubelet 目录
4. 设置 mount propagation（Bidirectional）
5. 格式化文件系统（mkfs）

这些操作都需要 privileged 或特定 capabilities。
安全缓解：
- 不使用 hostNetwork（除非必须）
- 限制 volumeMount 为只读（除必需的写路径）
- 使用 seccomp / AppArmor 限制
```

### Q10：Controller Plugin 为什么推荐单副本？

```
1. CreateVolume / DeleteVolume 通常涉及云 API 调用
   - 并发创建同一个 volume 可能导致重复资源
   - 即使有幂等 key，也要处理分布式协调

2. ControllerPublishVolume 涉及云盘挂载
   - 同一云盘不能同时挂载到两个节点（大部分云平台限制）

3. 使用 StatefulSet + Leader Election：
   - StatefulSet 提供稳定 pod 名称
   - external-provisioner/attacher 内置 Leader Election
   - CSI Controller Plugin 本身可以多副本（通过 Leader Election）
```

---

## 三、架构设计

### Q11：从零设计一个 Operator，需要考虑哪些方面？

```
1. CRD 设计
   - Spec：声明式意图，字段稳定、有校验
   - Status：控制器反馈，用户不应修改
   - SubResource：/status 分离读写权限
   - 版本策略：v1alpha1 → v1beta1 → v1

2. Controller 设计
   - 幂等 Reconcile
   - WorkQueue + 并发 Worker
   - OwnerReference 子资源管理
   - Finalizer 清理逻辑
   - RateLimit + 指数退避
   - GenerationChangedPredicate 过滤无效事件

3. 可观测性
   - Event 记录关键操作
   - Condition 反映阶段状态
   - Metrics：reconcile_total, reconcile_duration, queue_depth
   - 结构化日志（带上 CR name/namespace）

4. 稳定性
   - Leader Election 多副本
   - Graceful Shutdown（处理中的 Reconcile 完成后退出）
   - Health/Liveness Probe
   - memory/CPU limit

5. 安全
   - RBAC 最小权限
   - Webhook 校验和默认值
   - Secrets 加密或引用 ExternalSecrets
```

### Q12：Image CSI Driver 和普通云盘 CSI 的主要差异？

```
相同点：
- 都实现 CSI Identity / Controller / Node 三个 gRPC 服务
- 都用 external-provisioner / attacher / node-driver-registrar sidecar
- 都通过 Unix socket 与 kubelet 通信

差异点：
┌──────────────┬─────────────────────┬─────────────────────┐
│ 维度          │ Image CSI           │ 云盘 CSI            │
├──────────────┼─────────────────────┼─────────────────────┤
│ CreateVolume  │ 注册镜像引用到元数据 │ 调用云 API 创建云盘  │
│ DeleteVolume  │ 减少引用计数         │ 调用云 API 删除云盘  │
│ NodeStageVol  │ 拉取/解析镜像层      │ 挂载块设备到节点     │
│ Volume 源     │ 容器镜像仓库         │ 云存储(CBS/EBS/PD)  │
│ 可写层        │ 通常只读/临时层      │ 完全读写            │
│ 缓存策略      │ digest 去重 + LRU    │ 不适用              │
│ 内容寻址      │ OCI digest           │ Volume ID           │
└──────────────┴─────────────────────┴─────────────────────┘
```

### Q13：如何处理 CSI 驱动的故障恢复？

```
场景 1：Node Plugin 重启
  - kubelet 检测到 gRPC 连接断开
  - kubelet 重连并重新调用 NodeGetInfo 获取能力
  - 已挂载的卷不受影响（mount table 持久化在 OS）
  - 恢复：从 /proc/mounts 重建内存状态

场景 2：Controller Plugin 重启
  - external-provisioner 重连
  - 通过 List 已有 PV 和 volume metadata 文件重建内存状态
  - 正在进行的外部 API 调用由幂等性保护

场景 3：节点重启
  - kubelet 重新创建 Pod
  - NodeStageVolume / NodePublishVolume 按正常流程挂载
  - 原有的 mount 点应在重启时自动清理

场景 4：kubelet 重启
  - kubelet 扫描 /var/lib/kubelet/pods 重建 Pod 列表
  - 对每个 Pod 的 CSI Volume 调用 NodeStageVolume + NodePublishVolume
  - CSI 驱动必须正确处理"已挂载"的幂等情况
```
