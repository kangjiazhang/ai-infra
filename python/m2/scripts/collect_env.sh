#!/usr/bin/env bash
# 环境快照采集：每次实验前执行，结果只追加不修改（k3s + HAMi 版）
set -euo pipefail

OUT_DIR="${HOME}/leon/m2/results/env"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/env-$(date +%Y%m%d-%H%M%S).txt"

{
  echo "===== 环境快照 $(date -Is) ====="
  echo
  echo "--- nvidia-smi -L ---"
  nvidia-smi -L
  echo
  echo "--- nvidia-smi 摘要 ---"
  nvidia-smi
  echo
  echo "--- 卡间拓扑 ---"
  nvidia-smi topo -m
  echo
  echo "--- GPU 进程占用（应为空） ---"
  nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
  echo
  echo "--- k3s 版本与节点 ---"
  k3s --version
  kubectl get nodes -o wide
  echo
  echo "--- llm-lab-m2 命名空间资源 ---"
  kubectl -n llm-lab-m2 get all 2>/dev/null || echo "命名空间不存在"
  echo
  echo "--- HAMi 组件状态（只读） ---"
  kubectl -n llm-lab-hami get pods
  echo
  echo "--- 节点 GPU 可分配资源 ---"
  kubectl get node -o json | grep -B 2 -A 3 nvidia.com/gpu
  echo
  echo "--- 节点资源水位 ---"
  kubectl top node 2>/dev/null || echo "metrics-server 不可用"
  echo
  echo "--- 内存与磁盘 ---"
  free -h
  df -h / /dev/shm
} > "$OUT" 2>&1

echo "已保存: $OUT"
