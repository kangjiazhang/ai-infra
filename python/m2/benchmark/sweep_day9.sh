#!/usr/bin/env bash
# Day 9 二维参数实验：max-num-seqs × max-num-batched-tokens
# 固定：gpu-memory-utilization=0.85、max-model-len=4096、Qwen2.5-7B FP16、TP=2
# 变量：5 组 (seqs, batched-tokens) × 3 类工作负载（Day 7 定义）
#
# 每组流程：patch Deployment → 等 Ready → 记录启动日志容量信息
#           → 3 类负载依次压测（前后各采一次 /metrics，期间后台采 nvidia-smi）
#
# 用法：
#   EXP_ID=EXP-005 bash sweep_day9.sh              # 跑全部 5 组（约 2~4 小时）
#   EXP_ID=EXP-005 bash sweep_day9.sh 8 1024       # 只跑指定组（断点补跑）
#   NUM_PROMPTS=200 CONCURRENCY=8 bash sweep_day9.sh   # 可用环境变量缩小规模先试跑
set -euo pipefail

NS="llm-lab-m2"
DEPLOY="vllm-7b-fp16-tp2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_LOG_DIR="${HOME}/leon/m2/logs/day9"
HOST_RESULT_DIR="${HOME}/leon/m2/results/day9"
EXP_ID="${EXP_ID:-EXP-DAY9}"
mkdir -p "$HOST_LOG_DIR" "$HOST_RESULT_DIR"

# ============ 固定变量（本实验绝不修改） ============
GMU="0.85"
MMLEN="4096"
NUM_PROMPTS="${NUM_PROMPTS:-300}"
CONCURRENCY="${CONCURRENCY:-16}"

# ============ 实验矩阵 ============
MATRIX=(
  "4 1024"
  "8 1024"
  "16 1024"
  "8 2048"
  "8 4096"
)
[[ $# -eq 2 ]] && MATRIX=("$1 $2")

# ============ 工作负载（Day 7 定义） ============
WORKLOADS=(
  "short-short 128 128"
  "long-short 2048 128"
  "short-long 128 512"
)

patch_and_wait() {
  local seqs=$1 mnbt=$2
  echo ">>> [$EXP_ID] 切换配置: max-num-seqs=$seqs max-num-batched-tokens=$mnbt (GMU=$GMU MMLEN=$MMLEN 固定)"
  kubectl -n "$NS" patch deployment "$DEPLOY" --type=strategic -p "
spec:
  template:
    spec:
      containers:
      - name: vllm
        args:
        - --model
        - Qwen/Qwen2.5-7B-Instruct
        - --served-model-name
        - qwen2.5-7b
        - --dtype
        - half
        - --tensor-parallel-size
        - \"2\"
        - --max-model-len
        - \"${MMLEN}\"
        - --gpu-memory-utilization
        - \"${GMU}\"
        - --max-num-seqs
        - \"${seqs}\"
        - --max-num-batched-tokens
        - \"${mnbt}\"
"
  echo ">>> 等待新 Pod Ready（Recreate + 模型加载约 2~3 分钟）..."
  kubectl -n "$NS" rollout status "deployment/${DEPLOY}" --timeout=15m

  local pod
  pod=$(kubectl -n "$NS" get pod -l "app=${DEPLOY}" -o jsonpath='{.items[0].metadata.name}')
  # 启动日志：KV cache 容量、并发倍数（Day 8 答案的容量基线）
  kubectl -n "$NS" logs "$POD" 2>/dev/null \
    | grep -iE 'KV cache size|Maximum concurrency|max_num_seqs|chunked prefill' \
    > "${HOST_LOG_DIR}/startup-s${seqs}-t${mnbt}.log" || true
  echo ">>> 容量信息: $(cat "${HOST_LOG_DIR}/startup-s${seqs}-t${mnbt}.log" | tr '\n' ' ')"
}

metrics_snapshot() {
  # 抢占/水位/排队指标（Day 8 答案第 3 题的三个信号）
  local tag=$1
  local pod
  pod=$(kubectl -n "$NS" get pod -l "app=${DEPLOY}" -o jsonpath='{.items[0].metadata.name}')
  kubectl -n "$NS" exec "$pod" -- curl -s localhost:8000/metrics \
    | grep -E 'preempt|cache_usage|requests_waiting|requests_running' \
    > "${HOST_RESULT_DIR}/metrics-${tag}.txt" || true
}

for cfg in "${MATRIX[@]}"; do
  read -r SEQS MNBT <<< "$cfg"
  TAG="s${SEQS}-t${MNBT}"
  patch_and_wait "$SEQS" "$MNBT"

  for wl in "${WORKLOADS[@]}"; do
    read -r WLNAME ILEN OLEN <<< "$wl"
    echo ">>> 压测 ${TAG} × ${WLNAME} (${ILEN}in/${OLEN}out 并发${CONCURRENCY})"

    metrics_snapshot "${TAG}-${WLNAME}-pre"

    # GPU 后台采样（宿主机）：Util / 显存 / 功耗 / SM 时钟（70W 功耗墙监控）
    GPU_LOG="${HOST_RESULT_DIR}/gpu-${TAG}-${WLNAME}.csv"
    nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used,power.draw,clocks.sm \
      --format=csv -l 5 > "$GPU_LOG" 2>/dev/null &
    GPU_PID=$!

    if bash "${SCRIPT_DIR}/run_bench.sh" \
        --service "$DEPLOY" \
        --label "day9-${TAG}-${WLNAME}" \
        --model qwen2.5-7b \
        --tokenizer Qwen/Qwen2.5-7B-Instruct \
        --input-len "$ILEN" --output-len "$OLEN" \
        --num-prompts "$NUM_PROMPTS" \
        --concurrency "$CONCURRENCY" \
        --warmups 10 \
        --exp-id "${EXP_ID}-${TAG}"; then
      echo ">>> ${TAG} × ${WLNAME} 完成"
    else
      echo "!! ${TAG} × ${WLNAME} 压测失败，日志已保留，继续下一组"
    fi

    kill "$GPU_PID" 2>/dev/null || true
    metrics_snapshot "${TAG}-${WLNAME}-post"
  done

  # 本组完整 Deployment 存档（可追溯）
  kubectl -n "$NS" get deployment "$DEPLOY" -o yaml > "${HOST_LOG_DIR}/deploy-${TAG}.yaml"
done

echo ""
echo "========== Day 9 Sweep 完成 =========="
echo "bench JSON     : ${HOME}/leon/m2/results/bench/"
echo "metrics/GPU 快照: ${HOST_RESULT_DIR}"
echo "启动日志/部署存档: ${HOST_LOG_DIR}"
echo "拉回本地归档:"
echo "  rsync -av root@服务器:~/leon/m2/results/ ~/project/study/python/m2/benchmark/results/raw/"
