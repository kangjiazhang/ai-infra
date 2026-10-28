{{/*
基础命名
*/}}
{{- define "vllm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "vllm.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "vllm.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
标签
*/}}
{{- define "vllm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vllm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "vllm.labels" -}}
helm.sh/chart: {{ include "vllm.chart" . }}
{{ include "vllm.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
ServiceAccount 名称
*/}}
{{- define "vllm.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "vllm.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
HF Token Secret 名称：优先使用用户已有的 Secret
*/}}
{{- define "vllm.hfSecretName" -}}
{{- if .Values.secret.existingSecret }}
{{- .Values.secret.existingSecret }}
{{- else }}
{{- printf "%s-hf" (include "vllm.fullname" .) }}
{{- end }}
{{- end }}

{{/*
vLLM serve 参数（不含模型本身，模型由 entrypoint 作为位置参数传入）

设计说明：
- 参数统一在这里生成，ConfigMap 与文档引用同一来源，避免两处漂移
- 只放"容量/性能"相关参数；权重分发、并行度等由 values 控制
*/}}
{{- define "vllm.serveArgs" -}}
--served-model-name {{ .Values.model.servedName }}
{{- if .Values.model.revision }}
--revision {{ .Values.model.revision }}
{{- end }}
--host 0.0.0.0
--port {{ .Values.service.port }}
--dtype {{ .Values.model.dtype }}
--tensor-parallel-size {{ .Values.model.tp }}
--gpu-memory-utilization {{ .Values.model.gpuMemoryUtilization }}
--max-model-len {{ .Values.model.maxModelLen }}
--max-num-seqs {{ .Values.model.maxNumSeqs }}
--max-num-batched-tokens {{ .Values.model.maxNumBatchedTokens }}
{{- if not .Values.model.prefixCaching }}
--no-enable-prefix-caching
{{- end }}
{{- range .Values.model.extraArgs }}
{{ . }}
{{- end }}
{{- end }}
