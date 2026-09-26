{{- define "agentic.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentic.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "agentic.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/part-of: {{ include "agentic.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "agentic.apiSelector" -}}
app.kubernetes.io/name: {{ include "agentic.fullname" . }}-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "agentic.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end -}}

{{- define "agentic.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (printf "%s-api" (include "agentic.fullname" .)) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "agentic.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "agentic.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "agentic.redisUrl" -}}
{{- if .Values.externalUrls.redisUrl -}}
{{- .Values.externalUrls.redisUrl -}}
{{- else -}}
{{- printf "redis://%s-redis:6379/0" (include "agentic.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "agentic.ollamaUrl" -}}
{{- if .Values.externalUrls.ollamaUrl -}}
{{- .Values.externalUrls.ollamaUrl -}}
{{- else -}}
{{- printf "http://%s-ollama:11434" (include "agentic.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/* Env shared by the API Deployment and the bootstrap Job */}}
{{- define "agentic.env" -}}
- name: DATABASE_URL
  valueFrom: { secretKeyRef: { name: {{ include "agentic.secretName" . }}, key: DATABASE_URL } }
- name: JWT_SECRET
  valueFrom: { secretKeyRef: { name: {{ include "agentic.secretName" . }}, key: JWT_SECRET } }
- name: ADMIN_USERNAME
  valueFrom: { secretKeyRef: { name: {{ include "agentic.secretName" . }}, key: ADMIN_USERNAME } }
- name: ADMIN_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ include "agentic.secretName" . }}, key: ADMIN_PASSWORD } }
{{- end -}}

{{- define "agentic.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile: { type: RuntimeDefault }
{{- end -}}

{{- define "agentic.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities: { drop: ["ALL"] }
{{- end -}}
