# Kubernetes CSI 驱动开发完整流程

> 从零实现一个演示 CSI 驱动（demo-csi），支持将目录内容以 Volume 形式挂载到 Pod。
>
> 理解 CSI 内部机制后，可以延伸到 Image CSI、云盘 CSI、Secret CSI 等生产场景。

---

## 一、CSI 架构总览

### 1.1 CSI 组件关系

```
┌──────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│  ┌───────────────┐    ┌──────────────────────────────────┐   │
│  │ API Server    │    │  Node                            │   │
│  │               │    │                                  │   │
│  │ PVC / PV /    │    │  kubelet                         │   │
│  │ VolumeAttachment    │    │                             │   │
│  └───────┬───────┘    │    ├──► CSI Node Plugin          │   │
│          │            │    │    (DaemonSet, 每节点)       │   │
│          ▼            │    │    - NodeStageVolume         │   │
│  ┌───────────────┐    │    │    - NodePublishVolume       │   │
│  │ CSI Controller│    │    │    - NodeUnpublishVolume     │   │
│  │ Plugin        │    │    │    - NodeUnstageVolume       │   │
│  │ (Deployment)  │    │    │    - NodeGetCapabilities     │   │
│  │               │    │    └──────────────────────────────┘   │
│  │ - CreateVolume│    │                                      │
│  │ - DeleteVolume│    │  ┌──────────────────────────────┐   │
│  │ - PublishVol  │    │  │ Sidecar Containers           │   │
│  │ - Snapshot    │    │  │ (external-provisioner,       │   │
│  └───────────────┘    │  │  external-attacher,          │   │
│                       │  │  node-driver-registrar...)   │   │
│                       │  └──────────────────────────────┘   │
│                       └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 三个 gRPC 服务

| 服务 | 运行位置 | 核心接口 | 职责 |
|---|---|---|---|
| **Identity** | Controller + Node | `GetPluginInfo`、`GetPluginCapabilities`、`Probe` | 返回驱动信息、能力声明、健康检查 |
| **Controller** | Deployment（推荐单副本） | `CreateVolume`、`DeleteVolume`、`ControllerPublishVolume`、`ControllerUnpublishVolume`、`CreateSnapshot` | 卷生命周期管理（创建/删除/快照/挂载到节点） |
| **Node** | DaemonSet（每节点） | `NodeStageVolume`、`NodePublishVolume`、`NodeUnpublishVolume`、`NodeUnstageVolume`、`NodeGetCapabilities`、`NodeGetVolumeStats` | 节点侧操作（挂载/卸载/格式化/统计） |

### 1.3 卷挂载完整流程

```
用户创建 PVC (StorageClass = demo-csi)
  │
  ▼
external-provisioner (sidecar) 检测 PVC
  │
  ▼
CSI Controller.CreateVolume()     ← 创建卷（返回 volume_id）
  │
  ▼
PV 创建 + PV → PVC 绑定
  │
用户创建 Pod 引用 PVC
  │
Scheduler 调度 Pod 到节点
  │
external-attacher (sidecar) 创建 VolumeAttachment
  │
  ▼
CSI Controller.ControllerPublishVolume()  ← 将卷发布到目标节点
  │
  ▼
kubelet 调用（通过 Unix socket → gRPC）：
  ├── CSI Node.NodeStageVolume()          ← 挂载到节点全局路径
  │   /var/lib/kubelet/plugins/kubernetes.io/csi/demo-csi/<vol-id>/globalmount
  │
  └── CSI Node.NodePublishVolume()        ← bind mount 到 Pod 目录
      /var/lib/kubelet/pods/<pod-uid>/volumes/.../mount

Pod 运行中访问挂载路径
  │
Pod 删除 → kubelet 调用：
  ├── CSI Node.NodeUnpublishVolume()      ← 卸载 Pod 目录
  └── CSI Node.NodeUnstageVolume()        ← 卸载全局路径

PVC 删除 → external-provisioner 调用：
  └── CSI Controller.DeleteVolume()       ← 删除卷
```

---

## 二、项目结构

```
examples/demo-csi/
├── go.mod
├── main.go                       # 入口：启动 gRPC server
├── cmd/
│   └── server.go                 # 命令行参数和 server 启动逻辑
├── pkg/
│   ├── driver/
│   │   ├── driver.go             # 驱动主结构体
│   │   ├── identity.go           # Identity 服务实现
│   │   ├── controller.go         # Controller 服务实现
│   │   └── node.go               # Node 服务实现
│   └── mount/
│       └── mount.go              # mount/unmount 工具函数
└── deploy/
    ├── CSIDriver.yaml            # CSIDriver 资源
    ├── Controller.yaml           # Controller Plugin Deployment
    ├── DaemonSet.yaml            # Node Plugin DaemonSet
    └── StorageClass.yaml         # StorageClass
```

---

## 三、核心代码实现

### 3.1 入口文件 `main.go`

```go
package main

import (
    "flag"
    "os"

    "github.com/example/demo-csi/cmd"
)

func main() {
    var (
        endpoint  = flag.String("endpoint", "unix:///csi/csi.sock", "CSI endpoint")
        driverName = flag.String("driver-name", "demo.csi.example.com", "驱动名称")
        nodeID    = flag.String("node-id", "", "节点 ID")
        version   = flag.String("version", "v1.0.0", "版本")
    )
    flag.Parse()

    if *nodeID == "" {
        *nodeID = os.Getenv("NODE_NAME")
        if *nodeID == "" {
            *nodeID = "unknown-node"
        }
    }

    srv := cmd.NewServer(*endpoint, *driverName, *nodeID, *version)
    if err := srv.Run(); err != nil {
        os.Exit(1)
    }
}
```

### 3.2 命令行和 Server `cmd/server.go`

```go
package cmd

import (
    "fmt"
    "net"
    "os"
    "strings"

    "github.com/example/demo-csi/pkg/driver"
    "google.golang.org/grpc"
    "k8s.io/klog/v2"
)

type Server struct {
    endpoint   string
    driverName string
    nodeID     string
    version    string
    driver     *driver.Driver
}

func NewServer(endpoint, driverName, nodeID, version string) *Server {
    return &Server{
        endpoint:   endpoint,
        driverName: driverName,
        nodeID:     nodeID,
        version:    version,
    }
}

func (s *Server) Run() error {
    // 1. 解析 endpoint
    proto, addr, err := parseEndpoint(s.endpoint)
    if err != nil {
        return fmt.Errorf("解析 endpoint 失败: %v", err)
    }

    // 2. Unix socket: 先清理旧文件
    if proto == "unix" {
        if err := os.Remove(addr); err != nil && !os.IsNotExist(err) {
            return fmt.Errorf("清理旧 socket 文件失败: %v", err)
        }
    }

    // 3. 创建 listener
    listener, err := net.Listen(proto, addr)
    if err != nil {
        return fmt.Errorf("创建 listener 失败: %v", err)
    }

    // 4. 创建 gRPC server
    grpcServer := grpc.NewServer(
        grpc.MaxRecvMsgSize(32*1024*1024),  // 32MB 消息限制
        grpc.MaxSendMsgSize(32*1024*1024),
    )

    // 5. 创建并注册 CSI 驱动
    s.driver = driver.NewDriver(s.driverName, s.nodeID, s.version)
    s.driver.Register(grpcServer)

    // 6. 启动 gRPC server
    klog.Infof("CSI 驱动 %s 启动在 %s, nodeID=%s", s.driverName, s.endpoint, s.nodeID)
    if err := grpcServer.Serve(listener); err != nil {
        return fmt.Errorf("gRPC server 启动失败: %v", err)
    }

    return nil
}

func parseEndpoint(endpoint string) (string, string, error) {
    if strings.HasPrefix(endpoint, "unix://") {
        return "unix", endpoint[7:], nil
    }
    if strings.HasPrefix(endpoint, "tcp://") {
        return "tcp", endpoint[6:], nil
    }
    return "", "", fmt.Errorf("不支持的 endpoint 协议: %s", endpoint)
}
```

### 3.3 驱动主结构体 `pkg/driver/driver.go`

```go
package driver

import (
    "sync"

    "github.com/container-storage-interface/spec/lib/go/csi"
    "google.golang.org/grpc"
    "k8s.io/klog/v2"
)

// Driver 实现 CSI Identity、Controller、Node 三个 gRPC 服务
type Driver struct {
    csi.UnimplementedIdentityServer
    csi.UnimplementedControllerServer
    csi.UnimplementedNodeServer

    name    string
    nodeID  string
    version string

    // 容量限制（单位：字节）
    capacity int64

    // 卷状态管理（volumeID → 卷信息）
    mu     sync.RWMutex
    volumes map[string]*VolumeInfo

    // 节点发布状态（volumeID → 发布到哪个节点）
    publishedVolumes map[string]*PublishedInfo
}

// VolumeInfo 卷信息
type VolumeInfo struct {
    VolumeID   string
    Size       int64  // 请求大小
    TargetPath string // 数据存储路径
    Capacity   int64  // 总容量
    Used       int64  // 已使用
}

// PublishedInfo 卷发布信息
type PublishedInfo struct {
    VolumeID string
    NodeID   string
}

func NewDriver(name, nodeID, version string) *Driver {
    return &Driver{
        name:             name,
        nodeID:           nodeID,
        version:          version,
        capacity:         10 * 1024 * 1024 * 1024, // 默认 10GB
        volumes:          make(map[string]*VolumeInfo),
        publishedVolumes: make(map[string]*PublishedInfo),
    }
}

// Register 注册所有 CSI 服务到 gRPC server
func (d *Driver) Register(s *grpc.Server) {
    csi.RegisterIdentityServer(s, d)
    csi.RegisterControllerServer(s, d)
    csi.RegisterNodeServer(s, d)
}
```

### 3.4 Identity 服务 `pkg/driver/identity.go`

```go
package driver

import (
    "context"

    "github.com/container-storage-interface/spec/lib/go/csi"
    "k8s.io/klog/v2"
)

func (d *Driver) GetPluginInfo(ctx context.Context, req *csi.GetPluginInfoRequest) (*csi.GetPluginInfoResponse, error) {
    klog.V(4).Info("GetPluginInfo called")
    return &csi.GetPluginInfoResponse{
        Name:          d.name,
        VendorVersion: d.version,
    }, nil
}

func (d *Driver) GetPluginCapabilities(ctx context.Context, req *csi.GetPluginCapabilitiesRequest) (*csi.GetPluginCapabilitiesResponse, error) {
    klog.V(4).Info("GetPluginCapabilities called")
    return &csi.GetPluginCapabilitiesResponse{
        Capabilities: []*csi.PluginCapability{
            {
                Type: &csi.PluginCapability_Service_{
                    Service: &csi.PluginCapability_Service{
                        Type: csi.PluginCapability_Service_CONTROLLER_SERVICE,
                    },
                },
            },
            {
                Type: &csi.PluginCapability_VolumeExpansion_{
                    VolumeExpansion: &csi.PluginCapability_VolumeExpansion{
                        Type: csi.PluginCapability_VolumeExpansion_ONLINE,
                    },
                },
            },
        },
    }, nil
}

func (d *Driver) Probe(ctx context.Context, req *csi.ProbeRequest) (*csi.ProbeResponse, error) {
    klog.V(5).Info("Probe called")
    return &csi.ProbeResponse{
        Ready: &csi.ProbeResponse_Ready{Value: true},
    }, nil
}
```

### 3.5 Controller 服务 `pkg/driver/controller.go`

```go
package driver

import (
    "context"
    "fmt"
    "os"
    "path/filepath"

    "github.com/container-storage-interface/spec/lib/go/csi"
    "github.com/google/uuid"
    "k8s.io/klog/v2"
)

const dataRoot = "/tmp/demo-csi-data" // 生产环境改为可持续化路径

func (d *Driver) CreateVolume(ctx context.Context, req *csi.CreateVolumeRequest) (*csi.CreateVolumeResponse, error) {
    klog.Infof("CreateVolume: name=%s, capacity=%d", req.GetName(), req.GetCapacityRange().GetRequiredBytes())

    volumeID := uuid.New().String()
    capacity := req.GetCapacityRange().GetRequiredBytes()

    // 创建数据目录
    volumePath := filepath.Join(dataRoot, volumeID)
    if err := os.MkdirAll(volumePath, 0755); err != nil {
        return nil, fmt.Errorf("创建卷目录失败: %v", err)
    }

    d.mu.Lock()
    d.volumes[volumeID] = &VolumeInfo{
        VolumeID: volumeID,
        Size:     capacity,
        TargetPath: volumePath,
        Capacity: d.capacity,
    }
    d.mu.Unlock()

    klog.Infof("CreateVolume: volumeID=%s, path=%s", volumeID, volumePath)
    return &csi.CreateVolumeResponse{
        Volume: &csi.Volume{
            VolumeId:      volumeID,
            CapacityBytes: capacity,
            VolumeContext: map[string]string{
                "volumePath": volumePath,
            },
        },
    }, nil
}

func (d *Driver) DeleteVolume(ctx context.Context, req *csi.DeleteVolumeRequest) (*csi.DeleteVolumeResponse, error) {
    volumeID := req.GetVolumeId()
    klog.Infof("DeleteVolume: volumeID=%s", volumeID)

    d.mu.Lock()
    volInfo, exists := d.volumes[volumeID]
    if exists {
        delete(d.volumes, volumeID)
    }
    d.mu.Unlock()

    if exists && volInfo.TargetPath != "" {
        // 清理数据目录
        if err := os.RemoveAll(volInfo.TargetPath); err != nil {
            klog.Warningf("清理卷目录失败: %v", err)
        }
    }

    return &csi.DeleteVolumeResponse{}, nil
}

func (d *Driver) ControllerPublishVolume(ctx context.Context, req *csi.ControllerPublishVolumeRequest) (*csi.ControllerPublishVolumeResponse, error) {
    volumeID := req.GetVolumeId()
    nodeID := req.GetNodeId()
    klog.Infof("ControllerPublishVolume: volumeID=%s, nodeID=%s", volumeID, nodeID)

    // 幂等：已发布则返回成功
    d.mu.Lock()
    defer d.mu.Unlock()

    if _, exists := d.publishedVolumes[volumeID]; exists {
        klog.V(4).Infof("卷 %s 已发布", volumeID)
        return &csi.ControllerPublishVolumeResponse{}, nil
    }

    d.publishedVolumes[volumeID] = &PublishedInfo{
        VolumeID: volumeID,
        NodeID:   nodeID,
    }

    return &csi.ControllerPublishVolumeResponse{}, nil
}

func (d *Driver) ControllerUnpublishVolume(ctx context.Context, req *csi.ControllerUnpublishVolumeRequest) (*csi.ControllerUnpublishVolumeResponse, error) {
    volumeID := req.GetVolumeId()
    klog.Infof("ControllerUnpublishVolume: volumeID=%s", volumeID)

    d.mu.Lock()
    delete(d.publishedVolumes, volumeID)
    d.mu.Unlock()

    return &csi.ControllerUnpublishVolumeResponse{}, nil
}

func (d *Driver) ValidateVolumeCapabilities(ctx context.Context, req *csi.ValidateVolumeCapabilitiesRequest) (*csi.ValidateVolumeCapabilitiesResponse, error) {
    volumeID := req.GetVolumeId()
    klog.Infof("ValidateVolumeCapabilities: volumeID=%s", volumeID)

    d.mu.RLock()
    _, exists := d.volumes[volumeID]
    d.mu.RUnlock()

    if !exists {
        return nil, fmt.Errorf("卷 %s 不存在", volumeID)
    }

    return &csi.ValidateVolumeCapabilitiesResponse{
        Confirmed: &csi.ValidateVolumeCapabilitiesResponse_Confirmed{
            VolumeCapabilities: req.GetVolumeCapabilities(),
        },
    }, nil
}

func (d *Driver) ControllerGetCapabilities(ctx context.Context, req *csi.ControllerGetCapabilitiesRequest) (*csi.ControllerGetCapabilitiesResponse, error) {
    return &csi.ControllerGetCapabilitiesResponse{
        Capabilities: []*csi.ControllerServiceCapability{
            {
                Type: &csi.ControllerServiceCapability_Rpc{
                    Rpc: &csi.ControllerServiceCapability_RPC{
                        Type: csi.ControllerServiceCapability_RPC_CREATE_DELETE_VOLUME,
                    },
                },
            },
            {
                Type: &csi.ControllerServiceCapability_Rpc{
                    Rpc: &csi.ControllerServiceCapability_RPC{
                        Type: csi.ControllerServiceCapability_RPC_PUBLISH_UNPUBLISH_VOLUME,
                    },
                },
            },
        },
    }, nil
}
```

### 3.6 Node 服务 `pkg/driver/node.go`

```go
package driver

import (
    "context"
    "fmt"
    "os"
    "path/filepath"

    "github.com/container-storage-interface/spec/lib/go/csi"
    "github.com/example/demo-csi/pkg/mount"
    "k8s.io/klog/v2"
)

func (d *Driver) NodeStageVolume(ctx context.Context, req *csi.NodeStageVolumeRequest) (*csi.NodeStageVolumeResponse, error) {
    volumeID := req.GetVolumeId()
    stagingTargetPath := req.GetStagingTargetPath()
    klog.Infof("NodeStageVolume: volumeID=%s, stagingPath=%s", volumeID, stagingTargetPath)

    // 幂等：已挂载则返回成功
    notMnt, err := mount.IsNotMountPoint(stagingTargetPath)
    if err != nil && !os.IsNotExist(err) {
        return nil, fmt.Errorf("检查挂载点失败: %v", err)
    }
    if !notMnt {
        klog.V(4).Infof("卷 %s 已挂载到 %s，跳过", volumeID, stagingTargetPath)
        return &csi.NodeStageVolumeResponse{}, nil
    }

    // 获取卷数据路径
    d.mu.RLock()
    volInfo, exists := d.volumes[volumeID]
    d.mu.RUnlock()
    if !exists {
        // 生产环境应从外部存储获取卷信息
        volInfo = &VolumeInfo{TargetPath: "/tmp/demo-csi-data/" + volumeID}
    }

    // 确保数据目录存在
    if err := os.MkdirAll(volInfo.TargetPath, 0755); err != nil {
        return nil, fmt.Errorf("创建数据目录失败: %v", err)
    }

    // 确保 staging 目录存在
    if err := os.MkdirAll(stagingTargetPath, 0755); err != nil {
        return nil, fmt.Errorf("创建 staging 目录失败: %v", err)
    }

    // bind mount 数据目录到 staging 路径
    if err := mount.Mount(volInfo.TargetPath, stagingTargetPath, "", "bind", ""); err != nil {
        return nil, fmt.Errorf("bind mount 失败: %v", err)
    }

    klog.Infof("NodeStageVolume 完成: %s → %s", volInfo.TargetPath, stagingTargetPath)
    return &csi.NodeStageVolumeResponse{}, nil
}

func (d *Driver) NodeUnstageVolume(ctx context.Context, req *csi.NodeUnstageVolumeRequest) (*csi.NodeUnstageVolumeResponse, error) {
    stagingTargetPath := req.GetStagingTargetPath()
    klog.Infof("NodeUnstageVolume: stagingPath=%s", stagingTargetPath)

    // 幂等：已卸载则返回成功
    notMnt, err := mount.IsNotMountPoint(stagingTargetPath)
    if err != nil && !os.IsNotExist(err) {
        return nil, fmt.Errorf("检查挂载点失败: %v", err)
    }
    if notMnt {
        klog.V(4).Infof("staging 路径 %s 已卸载", stagingTargetPath)
        return &csi.NodeUnstageVolumeResponse{}, nil
    }

    if err := mount.Unmount(stagingTargetPath); err != nil {
        return nil, fmt.Errorf("卸载 staging 路径失败: %v", err)
    }

    klog.Infof("NodeUnstageVolume 完成")
    return &csi.NodeUnstageVolumeResponse{}, nil
}

func (d *Driver) NodePublishVolume(ctx context.Context, req *csi.NodePublishVolumeRequest) (*csi.NodePublishVolumeResponse, error) {
    volumeID := req.GetVolumeId()
    targetPath := req.GetTargetPath()
    stagingTargetPath := req.GetStagingTargetPath()
    klog.Infof("NodePublishVolume: volumeID=%s, targetPath=%s", volumeID, targetPath)

    // 幂等：已挂载则返回成功
    notMnt, err := mount.IsNotMountPoint(targetPath)
    if err != nil && !os.IsNotExist(err) {
        return nil, fmt.Errorf("检查挂载点失败: %v", err)
    }
    if !notMnt {
        klog.V(4).Infof("卷 %s 已发布到 %s", volumeID, targetPath)
        return &csi.NodePublishVolumeResponse{}, nil
    }

    // 确保 target 目录存在
    if err := os.MkdirAll(targetPath, 0755); err != nil {
        return nil, fmt.Errorf("创建 target 目录失败: %v", err)
    }

    // bind mount staging → target
    mountFlags := req.GetVolumeCapability().GetMount().GetMountFlags()
    fsType := req.GetVolumeCapability().GetMount().GetFsType()
    if fsType == "" {
        fsType = "ext4"
    }

    if err := mount.Mount(stagingTargetPath, targetPath, fsType, "bind", mountFlags); err != nil {
        return nil, fmt.Errorf("bind mount 失败: %v", err)
    }

    klog.Infof("NodePublishVolume 完成: %s → %s", stagingTargetPath, targetPath)
    return &csi.NodePublishVolumeResponse{}, nil
}

func (d *Driver) NodeUnpublishVolume(ctx context.Context, req *csi.NodeUnpublishVolumeRequest) (*csi.NodeUnpublishVolumeResponse, error) {
    targetPath := req.GetTargetPath()
    klog.Infof("NodeUnpublishVolume: targetPath=%s", targetPath)

    notMnt, err := mount.IsNotMountPoint(targetPath)
    if err != nil && !os.IsNotExist(err) {
        return nil, fmt.Errorf("检查挂载点失败: %v", err)
    }
    if notMnt {
        klog.V(4).Infof("路径 %s 已卸载", targetPath)
        return &csi.NodeUnpublishVolumeResponse{}, nil
    }

    if err := mount.Unmount(targetPath); err != nil {
        return nil, fmt.Errorf("卸载 target 路径失败: %v", err)
    }

    // 清理 target 目录
    os.Remove(targetPath)

    klog.Infof("NodeUnpublishVolume 完成")
    return &csi.NodeUnpublishVolumeResponse{}, nil
}

func (d *Driver) NodeGetCapabilities(ctx context.Context, req *csi.NodeGetCapabilitiesRequest) (*csi.NodeGetCapabilitiesResponse, error) {
    return &csi.NodeGetCapabilitiesResponse{
        Capabilities: []*csi.NodeServiceCapability{
            {
                Type: &csi.NodeServiceCapability_Rpc{
                    Rpc: &csi.NodeServiceCapability_RPC{
                        Type: csi.NodeServiceCapability_RPC_STAGE_UNSTAGE_VOLUME,
                    },
                },
            },
            {
                Type: &csi.NodeServiceCapability_Rpc{
                    Rpc: &csi.NodeServiceCapability_RPC{
                        Type: csi.NodeServiceCapability_RPC_GET_VOLUME_STATS,
                    },
                },
            },
        },
    }, nil
}

func (d *Driver) NodeGetVolumeStats(ctx context.Context, req *csi.NodeGetVolumeStatsRequest) (*csi.NodeGetVolumeStatsResponse, error) {
    volumePath := req.GetVolumePath()
    klog.V(4).Infof("NodeGetVolumeStats: path=%s", volumePath)

    var stat syscall.Statfs_t
    if err := syscall.Statfs(volumePath, &stat); err != nil {
        return nil, fmt.Errorf("获取卷信息失败: %v", err)
    }

    totalBytes := int64(stat.Blocks) * int64(stat.Bsize)
    availableBytes := int64(stat.Bavail) * int64(stat.Bsize)
    usedBytes := totalBytes - availableBytes

    return &csi.NodeGetVolumeStatsResponse{
        Usage: []*csi.VolumeUsage{
            {Total: totalBytes, Available: availableBytes, Used: usedBytes, Unit: csi.VolumeUsage_BYTES},
        },
    }, nil
}

func (d *Driver) NodeGetInfo(ctx context.Context, req *csi.NodeGetInfoRequest) (*csi.NodeGetInfoResponse, error) {
    return &csi.NodeGetInfoResponse{
        NodeId:            d.nodeID,
        MaxVolumesPerNode: 64,
    }, nil
}
```

### 3.7 Mount 工具 `pkg/mount/mount.go`

```go
package mount

import (
    "os"
    "os/exec"
    "strings"

    "k8s.io/klog/v2"
)

// Mount 挂载文件系统（使用 mount 命令，确保跨平台）
func Mount(source, target, fstype, options string, flags []string) error {
    args := []string{}

    if fstype != "" && fstype != "bind" {
        args = append(args, "-t", fstype)
    }
    if options != "" {
        args = append(args, "-o", options)
    }
    if len(flags) > 0 {
        args = append(args, "-o", strings.Join(flags, ","))
    }

    args = append(args, source, target)

    cmd := exec.Command("mount", args...)
    output, err := cmd.CombinedOutput()
    if err != nil {
        klog.Errorf("mount 失败: %v, output: %s", err, string(output))
        return err
    }
    return nil
}

// Unmount 卸载挂载点
func Unmount(target string) error {
    cmd := exec.Command("umount", target)
    output, err := cmd.CombinedOutput()
    if err != nil {
        // 如果是 lazy unmount 场景，可以尝试 -l
        cmd = exec.Command("umount", "-l", target)
        output, err = cmd.CombinedOutput()
        if err != nil {
            klog.Errorf("umount 失败: %v, output: %s", err, string(output))
            return err
        }
    }
    return nil
}

// IsNotMountPoint 检查路径是否为挂载点
// 返回 (true, nil) 表示不是挂载点
func IsNotMountPoint(target string) (bool, error) {
    // 方法 1: 使用 mountpoint 命令
    cmd := exec.Command("mountpoint", "-q", target)
    if err := cmd.Run(); err != nil {
        return true, nil  // mountpoint -q 返回非 0 = 不是挂载点
    }

    // 方法 2: 检查 /proc/mounts（作为交叉验证）
    data, err := os.ReadFile("/proc/mounts")
    if err != nil {
        return true, nil
    }
    for _, line := range strings.Split(string(data), "\n") {
        fields := strings.Fields(line)
        if len(fields) >= 2 && fields[1] == target {
            return false, nil  // 在 /proc/mounts 中找到 = 是挂载点
        }
    }

    return true, nil
}
```

---

## 四、部署配置

### 4.1 CSIDriver 资源 `deploy/CSIDriver.yaml`

```yaml
apiVersion: storage.k8s.io/v1
kind: CSIDriver
metadata:
  name: demo.csi.example.com
spec:
  attachRequired: true      # 需要 ControllerPublishVolume
  podInfoOnMount: true      # 挂载时传递 Pod 信息
  volumeLifecycleModes:
    - Persistent
    - Ephemeral
  fsGroupPolicy: File
```

### 4.2 Controller Plugin Deployment `deploy/Controller.yaml`

```yaml
apiVersion: apps/v1
kind: StatefulSet   # 使用 StatefulSet 保证单副本 + 稳定标识
metadata:
  name: demo-csi-controller
  namespace: demo-csi
spec:
  serviceName: demo-csi-controller
  replicas: 1
  selector:
    matchLabels:
      app: demo-csi-controller
  template:
    metadata:
      labels:
        app: demo-csi-controller
    spec:
      serviceAccountName: demo-csi-controller-sa
      containers:
        # CSI Controller Plugin
        - name: csi-controller
          image: registry.example.com/demo-csi-driver:v1.0.0
          args:
            - "--endpoint=unix:///csi/csi.sock"
            - "--driver-name=demo.csi.example.com"
            - "--node-id=controller"
          volumeMounts:
            - name: socket-dir
              mountPath: /csi
          ports:
            - containerPort: 9808
              name: healthz
          livenessProbe:
            httpGet:
              path: /healthz
              port: healthz
            initialDelaySeconds: 10
            periodSeconds: 30

        # Sidecar: external-provisioner
        - name: csi-provisioner
          image: registry.k8s.io/sig-storage/csi-provisioner:v4.0.0
          args:
            - "--csi-address=/csi/csi.sock"
            - "--leader-election"
            - "--timeout=60s"
          volumeMounts:
            - name: socket-dir
              mountPath: /csi

        # Sidecar: external-attacher
        - name: csi-attacher
          image: registry.k8s.io/sig-storage/csi-attacher:v4.5.0
          args:
            - "--csi-address=/csi/csi.sock"
            - "--leader-election"
            - "--timeout=60s"
          volumeMounts:
            - name: socket-dir
              mountPath: /csi

        # Sidecar: livenessprobe
        - name: liveness-probe
          image: registry.k8s.io/sig-storage/livenessprobe:v2.12.0
          args:
            - "--csi-address=/csi/csi.sock"

      volumes:
        - name: socket-dir
          emptyDir: {}
```

### 4.3 Node Plugin DaemonSet `deploy/DaemonSet.yaml`

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: demo-csi-node
  namespace: demo-csi
spec:
  selector:
    matchLabels:
      app: demo-csi-node
  template:
    metadata:
      labels:
        app: demo-csi-node
    spec:
      serviceAccountName: demo-csi-node-sa
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      containers:
        # CSI Node Plugin
        - name: csi-node
          image: registry.example.com/demo-csi-driver:v1.0.0
          args:
            - "--endpoint=unix:///csi/csi.sock"
            - "--driver-name=demo.csi.example.com"
            - "--node-id=$(NODE_NAME)"
          env:
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
          securityContext:
            privileged: true      # 需要特权以执行 mount
          volumeMounts:
            - name: plugin-dir
              mountPath: /csi
            - name: kubelet-dir
              mountPath: /var/lib/kubelet
              mountPropagation: Bidirectional
            - name: host-dev
              mountPath: /dev
            - name: data-dir
              mountPath: /tmp/demo-csi-data
          ports:
            - containerPort: 9808
              name: healthz
          livenessProbe:
            httpGet:
              path: /healthz
              port: healthz
            initialDelaySeconds: 10
            periodSeconds: 30

        # Sidecar: node-driver-registrar
        - name: node-driver-registrar
          image: registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.10.0
          args:
            - "--csi-address=/csi/csi.sock"
            - "--kubelet-registration-path=/var/lib/kubelet/plugins/demo.csi.example.com/csi.sock"
          volumeMounts:
            - name: plugin-dir
              mountPath: /csi
            - name: registration-dir
              mountPath: /registration

        # Sidecar: livenessprobe
        - name: liveness-probe
          image: registry.k8s.io/sig-storage/livenessprobe:v2.12.0
          args:
            - "--csi-address=/csi/csi.sock"

      volumes:
        - name: plugin-dir
          hostPath:
            path: /var/lib/kubelet/plugins/demo.csi.example.com
            type: DirectoryOrCreate
        - name: registration-dir
          hostPath:
            path: /var/lib/kubelet/plugins_registry
            type: Directory
        - name: kubelet-dir
          hostPath:
            path: /var/lib/kubelet
            type: Directory
        - name: host-dev
          hostPath:
            path: /dev
        - name: data-dir
          hostPath:
            path: /tmp/demo-csi-data
            type: DirectoryOrCreate
```

### 4.4 StorageClass `deploy/StorageClass.yaml`

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: demo-csi-sc
provisioner: demo.csi.example.com
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

---

## 五、测试验证

### 5.1 本地运行测试

```shell
# 1. 构建驱动
cd examples/demo-csi
go mod tidy
go build -o demo-csi-driver ./main.go

# 2. 启动驱动
sudo ./demo-csi-driver \
    --endpoint=unix:///tmp/csi.sock \
    --driver-name=demo.csi.example.com \
    --node-id=test-node

# 3. 用 csc 工具测试（安装 csi-sanity）
go install github.com/kubernetes-csi/csi-test/v5/cmd/csc@latest

# 测试 Identity
csc identity plugin-info --endpoint unix:///tmp/csi.sock

# 测试 Controller
csc controller create-volume \
    --endpoint unix:///tmp/csi.sock \
    --cap 1,1 \
    test-vol

# 测试 Node
csc node stage-volume \
    --endpoint unix:///tmp/csi.sock \
    --staging-target-path /tmp/staging \
    <volume-id>

csc node publish-volume \
    --endpoint unix:///tmp/csi.sock \
    --staging-target-path /tmp/staging \
    --target-path /tmp/publish \
    --cap 1,1 \
    <volume-id>
```

### 5.2 集群测试

```shell
# 1. 部署
kubectl create namespace demo-csi
kubectl apply -f deploy/CSIDriver.yaml
kubectl apply -f deploy/Controller.yaml
kubectl apply -f deploy/DaemonSet.yaml
kubectl apply -f deploy/StorageClass.yaml

# 2. 验证组件
kubectl get pods -n demo-csi
kubectl get csidriver
kubectl get storageclass

# 3. 创建 PVC
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: demo-pvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: demo-csi-sc
  resources:
    requests:
      storage: 1Gi
EOF

# 4. 创建测试 Pod
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: demo-csi-test
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command: ["sh", "-c", "echo 'CSI works!' > /data/msg.txt && sleep 3600"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: demo-pvc
EOF

# 5. 验证数据持久化
kubectl exec demo-csi-test -- cat /data/msg.txt
# 预期输出: CSI works!

# 6. 删除 Pod 后重新创建，验证数据仍然存在
kubectl delete pod demo-csi-test
kubectl apply -f demo-csi-test.yaml  # 重新创建
kubectl exec demo-csi-test -- cat /data/msg.txt
# 预期输出: CSI works!
```

---

## 六、开发关键检查点

### 6.1 幂等性（重中之重）

```go
// ✅ 每个 Node 操作都要做幂等检查
func (d *Driver) NodePublishVolume(ctx context.Context, req *csi.NodePublishVolumeRequest) (*csi.NodePublishVolumeResponse, error) {
    notMnt, err := mount.IsNotMountPoint(req.GetTargetPath())
    if err != nil && !os.IsNotExist(err) {
        return nil, status.Errorf(codes.Internal, "check mount: %v", err)
    }
    if !notMnt {
        // 已经是挂载点 → 幂等返回成功
        return &csi.NodePublishVolumeResponse{}, nil
    }
    // ... 执行实际挂载
}
```

### 6.2 gRPC 错误码

```go
import (
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/status"
)

// 标准错误返回方式
return nil, status.Error(codes.InvalidArgument, "volume_id is required")
return nil, status.Error(codes.NotFound, "volume not found")
return nil, status.Error(codes.Internal, "mount failed")
return nil, status.Error(codes.AlreadyExists, "volume already exists")
return nil, status.Error(codes.ResourceExhausted, "disk full")
```

### 6.3 安全

```yaml
# Node Plugin 必须 privileged（需要 mount 操作）
securityContext:
  privileged: true

# 卷挂载传播必须为 Bidirectional
volumeMounts:
  - name: kubelet-dir
    mountPath: /var/lib/kubelet
    mountPropagation: Bidirectional
```

### 6.4 内存状态 vs 持久化

```go
// ❌ 纯内存状态：进程重启后所有卷信息丢失
d.volumes[volumeID] = &VolumeInfo{...}

// ✅ 生产环境：持久化到磁盘 / 数据库
func (d *Driver) persistVolumeInfo(info *VolumeInfo) error {
    data, _ := json.Marshal(info)
    return os.WriteFile(filepath.Join(metadataDir, info.VolumeID+".json"), data, 0600)
}

func (d *Driver) loadVolumeInfo(volumeID string) (*VolumeInfo, error) {
    data, err := os.ReadFile(filepath.Join(metadataDir, volumeID+".json"))
    if err != nil {
        return nil, err
    }
    var info VolumeInfo
    json.Unmarshal(data, &info)
    return &info, nil
}
```

### 6.5 并发安全

```go
// 所有共享状态使用读写锁保护
d.mu.RLock()
info, exists := d.volumes[volumeID]
d.mu.RUnlock()
```

---

## 七、Image CSI 和业务 CSI 的扩展方向

有了上述基础架构，可以按需扩展：

### 7.1 扩展为 Image CSI

```go
// 在 NodeStageVolume 中：
// 1. 从 volCtx 读取镜像引用
// 2. 调用 containerd/CRI 拉取镜像（或解析本地已有镜像）
// 3. 将镜像层解包到 staging 路径
// 4. 通过 overlayfs 合并多层
// 参考：containerd snapshotter、oci image spec

func (d *Driver) NodeStageVolume(ctx context.Context, req *csi.NodeStageVolumeRequest) {
    imageRef := req.GetVolumeContext()["imageRef"]
    imageDigest := req.GetVolumeContext()["imageDigest"]
    // 1. 检查本地缓存
    // 2. 未命中则拉取镜像
    // 3. 解包到 staging
    // 4. 设置引用计数
}
```

### 7.2 扩展为配置热更新 CSI

```go
// 结合 ConfigMapRefresher 项目：
// ConfigMap 变更 → ConfigMapRefresher 触发 → 更新 CSI Volume（新版本）
// → NodePublishVolume 切换 symlink → 业务进程 reload

func (d *Driver) NodePublishVolume(ctx context.Context, req *csi.NodePublishVolumeRequest) {
    version := req.GetVolumeContext()["configVersion"]
    // 1. 定位配置版本目录
    // 2. 原子 symlink 切换
    // 3. 发送 SIGHUP 或调用业务 reload API
}
```

---
