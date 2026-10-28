#!/usr/bin/env bash
# k3s 版压测脚本：在集群内起临时 Pod 跑 vllm bench serve
# 结果通过 hostPath 直接写入 ~/leon/m2/results/bench/，压测完自动清理 Pod
#
# 用法示例：
#   bash run_bench.sh --service vllm-7b-fp16-tp2 --label fp16-7b-tp2 \
#     --model qwen2.5-7b --input-len 1024 --output-len 128 \
#     --num-prompts 300 --concurrency 8
set -euo pipefail

# ⚠️ 与 k8s/*.yaml 保持同一镜像版本
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.28.0}"
NS="llm-lab-m2"
HOST_BENCH_DIR="${HOME}/leon/m2/results/bench"
HOST_LOG_DIR="${HOME}/leon/m2/logs"
mkdir -p "$HOST_BENCH_DIR" "$HOST_LOG_DIR"

SERVICE="" LABEL="" MODEL="" TOKENIZER="" EXPID=""
INPUT_LEN=1024 OUTPUT_LEN=128 NUM_PROMPTS=300 CONCURRENCY=8 WARMUPS=10 RATE="inf"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)     SERVICE="$2"; shift 2 ;;
    --label)       LABEL="$2"; shift 2 ;;
    --model)       MODEL="$2"; shift 2 ;;
    --tokenizer)   TOKENIZER="$2"; shift 2 ;;
    --exp-id)      EXPID="$2"; shift 2 ;;
    --input-len)   INPUT_LEN="$2"; shift 2 ;;
    --output-len)  OUTPUT_LEN="$2"; shift 2 ;;
    --num-prompts) NUM_PROMPTS="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    --warmups)     WARMUPS="$2"; shift 2 ;;
    --rate)        RATE="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

[[ -z "$SERVICE" || -z "$LABEL" ]] && { echo "--service/--label 必填"; exit 1; }
[[ -z "$MODEL" ]] && MODEL="$SERVICE"
# tokenizer 必须是真实 HF 仓库 ID（用于客户端生成 random dataset 并计数）
# 注意 --model 是 served-model-name（服务别名），两者经常不同
[[ -z "$TOKENIZER" ]] && TOKENIZER="Qwen/Qwen2.5-7B-Instruct"

# 服务必须存在
kubectl -n "$NS" get svc "$SERVICE" >/dev/null || { echo "Service $NS/$SERVICE 不存在"; exit 1; }

TS=$(date +%Y%m%d-%H%M%S)
POD="bench-${LABEL}-${TS}"
RESULT_FILE="bench-${LABEL}-in${INPUT_LEN}-out${OUTPUT_LEN}-c${CONCURRENCY}-${TS}.json"
BASE_URL="http://${SERVICE}.${NS}.svc.cluster.local:8000"
META="label=${LABEL},service=${SERVICE},exp=${EXPID:-EXP-UNTAGGED},input=${INPUT_LEN},output=${OUTPUT_LEN},concurrency=${CONCURRENCY}"

echo "压测 $LABEL: ${INPUT_LEN}in/${OUTPUT_LEN}out 并发${CONCURRENCY} 共${NUM_PROMPTS}请求"
echo "目标: $BASE_URL"
echo "结果: $HOST_BENCH_DIR/$RESULT_FILE"

# 生成压测 Pod：挂 hostPath 让结果与日志直接落服务器磁盘
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: ${NS}
  labels:
    app: bench
    m2-bench: "true"
spec:
  restartPolicy: Never
  activeDeadlineSeconds: 3600
  containers:
  - name: bench
    image: ${VLLM_IMAGE}
    command:
    - vllm
    - bench
    - serve
    - --backend
    - openai-chat
    - --base-url
    - ${BASE_URL}
    - --endpoint
    - /v1/chat/completions
    - --model
    - ${MODEL}
    - --tokenizer
    - ${TOKENIZER}
    - --dataset-name
    - random
    - --input-len
    - "${INPUT_LEN}"
    - --output-len
    - "${OUTPUT_LEN}"
    - --num-prompts
    - "${NUM_PROMPTS}"
    - --max-concurrency
    - "${CONCURRENCY}"
    - --request-rate
    - "${RATE}"
    - --num-warmups
    - "${WARMUPS}"
    - --percentile-metrics
    - ttft,tpot,itl,e2el
    - --metric-percentiles
    - 50,95,99
    - --save-result
    - --save-detailed
    - --result-dir
    - /results
    - --result-filename
    - ${RESULT_FILE}
    - --metadata
    - "${META}"
    volumeMounts:
    - name: results
      mountPath: /results
    - name: hf-cache
      mountPath: /root/.cache/huggingface
  volumes:
  - name: results
    hostPath:
      path: ${HOST_BENCH_DIR}
      type: DirectoryOrCreate
  - name: hf-cache
    hostPath:
      path: /root/leon/m2/models
      type: DirectoryOrCreate
EOF

echo "等待压测 Pod 完成（日志实时输出，Ctrl+C 不影响 Pod）..."
kubectl -n "$NS" logs -f "$POD" 2>/dev/null || true

# 等终态
for _ in $(seq 1 360); do
  PHASE=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Deleted")
  [[ "$PHASE" == "Succeeded" || "$PHASE" == "Failed" || "$PHASE" == "Deleted" ]] && break
  sleep 10
done

# 日志存档
kubectl -n "$NS" logs "$POD" > "${HOST_LOG_DIR}/${POD}.log" 2>/dev/null || true

if [[ "$PHASE" == "Succeeded" ]]; then
  echo "压测完成: $HOST_BENCH_DIR/$RESULT_FILE"
  kubectl -n "$NS" delete pod "$POD" --ignore-not-found
  echo "记得在 --exp-id 传入实验编号，否则 metadata 中为 EXP-UNTAGGED"
else
  echo "压测异常（phase=$PHASE），日志: ${HOST_LOG_DIR}/${POD}.log"
  kubectl -n "$NS" get pod "$POD" -o wide || true
  echo "排查后手动清理: kubectl -n $NS delete pod $POD"
  exit 1
fi
