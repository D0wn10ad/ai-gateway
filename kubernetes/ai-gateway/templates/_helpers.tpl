{{/*
Expand the name of the chart.
*/}}
{{- define "ai-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ai-gateway.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ai-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ai-gateway.labels" -}}
helm.sh/chart: {{ include "ai-gateway.chart" . }}
{{ include "ai-gateway.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ai-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ai-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
LiteLLM specific labels
*/}}
{{- define "ai-gateway.litellm.labels" -}}
{{ include "ai-gateway.labels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{- define "ai-gateway.litellm.selectorLabels" -}}
{{ include "ai-gateway.selectorLabels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{/*
OpenWebUI specific labels
*/}}
{{- define "ai-gateway.openwebui.labels" -}}
{{ include "ai-gateway.labels" . }}
app.kubernetes.io/component: openwebui
{{- end }}

{{- define "ai-gateway.openwebui.selectorLabels" -}}
{{ include "ai-gateway.selectorLabels" . }}
app.kubernetes.io/component: openwebui
{{- end }}

{{/*
PgBouncer specific labels
*/}}
{{- define "ai-gateway.pgbouncer.labels" -}}
{{ include "ai-gateway.labels" . }}
app.kubernetes.io/component: pgbouncer
{{- end }}

{{- define "ai-gateway.pgbouncer.selectorLabels" -}}
{{ include "ai-gateway.selectorLabels" . }}
app.kubernetes.io/component: pgbouncer
{{- end }}

{{/*
Redis specific labels
*/}}
{{- define "ai-gateway.redis.labels" -}}
{{ include "ai-gateway.labels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{- define "ai-gateway.redis.selectorLabels" -}}
{{ include "ai-gateway.selectorLabels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
Create the name of the LiteLLM service account
*/}}
{{- define "ai-gateway.litellm.serviceAccountName" -}}
{{- if .Values.litellm.serviceAccount.create }}
{{- default (printf "%s-litellm" (include "ai-gateway.fullname" .)) .Values.litellm.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.litellm.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the OpenWebUI service account
*/}}
{{- define "ai-gateway.openwebui.serviceAccountName" -}}
{{- if .Values.openwebui.serviceAccount.create }}
{{- default (printf "%s-openwebui" (include "ai-gateway.fullname" .)) .Values.openwebui.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.openwebui.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PgBouncer service name
*/}}
{{- define "ai-gateway.pgbouncer.serviceName" -}}
{{- printf "%s-pgbouncer" (include "ai-gateway.fullname" .) }}
{{- end }}

{{/*
Redis service name
*/}}
{{- define "ai-gateway.redis.serviceName" -}}
{{- printf "%s-redis" (include "ai-gateway.fullname" .) }}
{{- end }}

{{/*
LiteLLM service name
*/}}
{{- define "ai-gateway.litellm.serviceName" -}}
{{- printf "%s-litellm" (include "ai-gateway.fullname" .) }}
{{- end }}

{{/*
OpenWebUI service name
*/}}
{{- define "ai-gateway.openwebui.serviceName" -}}
{{- printf "%s-openwebui" (include "ai-gateway.fullname" .) }}
{{- end }}

{{/*
Database URL for OpenWebUI (via PgBouncer)
*/}}
{{- define "ai-gateway.openwebui.databaseUrl" -}}
postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "ai-gateway.pgbouncer.serviceName" . }}:{{ .Values.pgbouncer.service.port }}/{{ .Values.postgresql.databases.openwebui }}
{{- end }}

{{/*
Database URL for LiteLLM (via PgBouncer)
*/}}
{{- define "ai-gateway.litellm.databaseUrl" -}}
postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "ai-gateway.pgbouncer.serviceName" . }}:{{ .Values.pgbouncer.service.port }}/{{ .Values.postgresql.databases.litellm }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "ai-gateway.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
