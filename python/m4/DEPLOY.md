# M4 Day 9 部署手册——vLLM 后端 + LiteLLM 网关（混合部署）

> 2026-10 实测勘误：LiteLLM 官方 OCI chart（ghcr.io）对腾讯云国内 IP 网络级 403，
> 改混合部署：DB 走 bitnami helm（源畅通），LiteLLM 本体走手写 manifest
> （镜像走官方镜像站 docker.litellm.ai）。ghcr 恢复后可切回 umbrella chart。

## 拓扑

```
客户端 ──> LiteLLM 网关 (llm-gateway:4000, 1 副本)
             │  model_list 路由
             ├──> qwen-7b-int4  → vllm-qa        (llm-qa,        T4 #1, 7B AWQ)
             ├──> qwen-1.5b     → vllm-smoke     (llm-lab-m2,    T4 #2, 1.5B)
             └──> Postgres      (记账：虚拟 key / 配额 / spend)
```

## 文件地图

| 路径 | 内容 |
|---|---|
| `helm/vllm-inference/` | vLLM 后端自维护 chart（qa/staging/smoke/prod 共用，values 分环境） |
| `helm/llm-gateway/` | LiteLLM + PG umbrella chart（**暂未启用**，ghcr 403，留作回退） |
| `helm/llm-gateway-postgres/values.yaml` | 现行 DB：bitnami/postgresql 独立 release |
| `k8s/litellm/litellm-gateway.yaml` | 现行 LiteLLM 本体：ConfigMap + Deployment + Service |
| `argocd/application.yaml` | GitOps 纳管入口（当前手动 helm 部署，未启用） |

## 前置条件（一次性，已完成）

1. 节点标签（HAMi/DRA 环境无 GFD 标签，需手动补）：
   `kubectl label node vm-0-2-ubuntu nvidia.com/gpu.product=Tesla-T4`
2. HF 模型缓存在节点 `/root/leon/m2/models`（M2 存量），chart 经
   `cache.hostPath` 直挂，冷启动免下载
3. 服务器可访问：charts.bitnami.com ✓ / registry-1.docker.io ✓ / ghcr.io ✗

## 部署（全新环境按序执行）

```bash
cd /root/leon/ai-infra/python/m4

# ① vLLM 后端 ×2
cd helm/vllm-inference
helm install vllm-qa . -n llm-qa --create-namespace -f values.yaml -f values-qa.yaml
# M2 存量同名资源先删：kubectl -n llm-lab-m2 delete deploy/vllm-smoke svc/vllm-smoke
helm install vllm-smoke . -n llm-lab-m2 -f values.yaml -f values-smoke.yaml

# ② Secret（manifest 引用，不进 Git）
kubectl -n llm-gateway create secret generic litellm-masterkey \
  --from-literal=masterkey='sk-litellm-master-m4lab'
kubectl -n llm-gateway create secret generic litellm-db \
  --from-literal=username=litellm --from-literal=password=litellm-m4lab

# ③ Postgres（bitnami）
cd ../llm-gateway-postgres
helm install llm-gateway-postgresql bitnami/postgresql -n llm-gateway \
  --create-namespace -f values.yaml

# ④ LiteLLM（manifest）
cd /root/leon/ai-infra
kubectl apply -f python/m4/k8s/litellm/litellm-gateway.yaml
kubectl -n llm-gateway get pods -w    # litellm 首启跑 DB 迁移，CrashLoop 1-2 次属正常
```

## 日常变更回路（无 ArgoCD）

mac 改 values/manifest → `git push` → 服务器 `git pull` → `helm upgrade`：

```bash
helm upgrade vllm-qa . -n llm-qa -f values.yaml -f values-qa.yaml
helm upgrade vllm-smoke . -n llm-lab-m2 -f values.yaml -f values-smoke.yaml
kubectl apply -f /root/leon/ai-infra/python/m4/k8s/litellm/litellm-gateway.yaml
```

注意 smoke 的 `maxSurge=0`：滚动升级时新 pod 等旧 pod 退出（含 120s 优雅下线）
才调度，期间零容量，属预期。

## 验证（Day 9 核心）

```bash
kubectl -n llm-gateway port-forward svc/litellm-gateway 4000:4000 &
MKEY='sk-litellm-master-m4lab'

# 1. 路由表
curl -s localhost:4000/v1/models -H "Authorization: Bearer $MKEY" | jq '.data[].id'
# 预期：qwen-7b-int4、qwen-1.5b

# 2. 两个后端各打一发
curl -s localhost:4000/v1/chat/completions -H "Authorization: Bearer $MKEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen-1.5b","messages":[{"role":"user","content":"一句话介绍自己"}],"max_tokens":32}'
curl -s localhost:4000/v1/chat/completions -H "Authorization: Bearer $MKEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen-7b-int4","messages":[{"role":"user","content":"一句话解释 KV Cache"}],"max_tokens":64}'

# 3. 虚拟 key + 配额（服务器无 jq，用 python3 提取）
VKEY=$(curl -s -X POST localhost:4000/key/generate -H "Authorization: Bearer $MKEY" \
  -H 'Content-Type: application/json' \
  -d '{"key_alias":"day9-test","models":["qwen-1.5b"],"max_budget":1,"tpm_limit":1000}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['key'])")
# 用 $VKEY 打请求（换掉 $MKEY）→ 白名单外模型 403；连打超 tpm_limit → 429

# 4. spend 记账入库（psql 要带 PGPASSWORD，见下文速查）
kubectl -n llm-gateway exec statefulset/llm-gateway-postgresql -- \
  sh -c 'PGPASSWORD=litellm-m4lab psql -U litellm -d litellm \
  -c "SELECT key_alias, spend, max_budget, tpm_limit FROM \"LiteLLM_VerificationToken\";"'
```

## 排障速查（本日实测踩坑）

| 症状 | 原因 | 解法 |
|---|---|---|
| pod Pending：`didn't match Pod's node affinity/selector` | HAMi/DRA 无 GFD 标签 | `kubectl label node ... nvidia.com/gpu.product=Tesla-T4` |
| 启动卡 `Loading model` 十几分钟 | HF 缓存未挂，容器内冷拉权重 | values 加 `cache.hostPath: /root/leon/m2/models` |
| `helm dependency update` ghcr 403 | ghcr token 端点拒国内云 IP | 改混合部署（本手册）；或 chart 包 vendor 入库 |
| upgrade 时新 pod Pending 数分钟 | maxSurge=0 等旧 pod 退出（120s grace） | 等；超 3 分钟再 force delete |
| 网关 404 `model not found` | served-model-name 与网关 model 不一致 | 后端 `/v1/models` 与 `model: openai/...` 逐字核对 |
| 长流式输出中途断 | request_timeout 过小 | 网关 litellm_settings.request_timeout: 600 |
| 网关 500 `OpenAIException - Connection error` | chart fullname=`release-chart名`，网关 api_base 指向不存在的 Service | values 加 `fullnameOverride: vllm-qa`（短名对齐 api_base） |
| spend 恒 0 | 自托管模型不在 LiteLLM 内置成本表 | model_list 加 `input/output_cost_per_token` 自报价 |
| `/key/info` POST 返回 405 | 1.90x 版本该方法改成了 GET | `GET /key/info?key=sk-xxx`；写操作仍走 POST |
| psql 交互式要密码（kubectl exec 传不进） | bitnami 镜像交互登录 | `sh -c 'PGPASSWORD=xxx psql ...'` 包一层 |
| curl 打网关空响应 / 000 | rollout restart 换 pod，port-forward 绑的是旧 pod sandbox | 重开 port-forward（`pkill -f port-forward` 后再拉起） |
| 升级后新 pod Pending 数分钟 | maxSurge=0 等旧 pod 退出（120s grace） | 等；超 3 分钟再 force delete |
| 改了 ConfigMap 但路由行为没变 | litellm 只在启动时读一次配置；ConfigMap 更新不触发 pod 重启（volume 文件会热更，进程不重读） | `kubectl rollout restart deploy/litellm-gateway` 后验证 `/health` |
| 验证路由器真实状态 | ConfigMap 只说明"应部署什么"，不说明进程加载了什么 | `GET /health` 看 healthy/unhealthy 列表（运行时权威） |

## 虚拟 key 与计费运维速查（Day 9 实测命令）

```bash
MKEY='sk-litellm-master-m4lab'      # master key：管理员，全权限无限额
VKEY='sk-xxx'                        # 虚拟 key：发给用户的，带配额

# 发放（models 白名单 / 预算 / 限速 / 有效期）
curl -s -X POST localhost:4000/key/generate \
  -H "Authorization: Bearer $MKEY" -H 'Content-Type: application/json' \
  -d '{"key_alias":"user-a","models":["qwen-1.5b"],"max_budget":1,
       "tpm_limit":1000,"rpm_limit":10,"duration":"30d"}'

# 查单 key（spend=已花费；注意异步入账，请求后几秒才更新）
curl -s "localhost:4000/key/info?key=$VKEY" -H "Authorization: Bearer $MKEY"

# 改配额 / 吊销
curl -s -X POST localhost:4000/key/update -H "Authorization: Bearer $MKEY" \
  -H 'Content-Type: application/json' -d '{"key":"sk-xxx","max_budget":5}'
curl -s -X POST localhost:4000/key/delete -H "Authorization: Bearer $MKEY" \
  -H 'Content-Type: application/json' -d '{"keys":["sk-xxx"]}'

# DB 对账（按 key 聚合 / 按请求流水）
kubectl -n llm-gateway exec statefulset/llm-gateway-postgresql -- \
  sh -c 'PGPASSWORD=litellm-m4lab psql -U litellm -d litellm \
  -c "SELECT key_alias, spend, max_budget, tpm_limit FROM \"LiteLLM_VerificationToken\";"'
kubectl -n llm-gateway exec statefulset/llm-gateway-postgresql -- \
  sh -c 'PGPASSWORD=litellm-m4lab psql -U litellm -d litellm \
  -c "SELECT model, spend, \"startTime\" FROM \"LiteLLM_SpendLogs\" ORDER BY \"startTime\" DESC LIMIT 5;"'
```

计价说明：自托管模型自报价（config.yaml 每个 model 的
`input_cost_per_token` / `output_cost_per_token`），spend = token × 单价，
异步写入上表；改价只对新请求生效，不补记历史。

## Day 9 验证结论（2026-10-28 实测全过）

| 项 | 结果 |
|---|---|
| /v1/models 虚拟名（qwen-7b-int4 / qwen-1.5b） | ✓ |
| 路由到跨 namespace 后端（llm-qa / llm-lab-m2） | ✓ |
| master / 虚拟 key 鉴权（DB 校验） | ✓ |
| per-key 模型白名单：白名单外模型 → 403 | ✓ |
| per-key 预算：spend 5.72e-05 入账（流水表可对账） | ✓ |
| tpm_limit：3×200 后第 4 发起 429（60s 滑动窗口） | ✓ |
