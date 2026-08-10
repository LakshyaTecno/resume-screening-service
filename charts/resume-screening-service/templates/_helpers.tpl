{{- define "resume-screening-service.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "resume-screening-service.fullname" -}}
{{- .Release.Name -}}-{{- include "resume-screening-service.name" . -}}
{{- end -}}

{{- define "resume-screening-service.labels" -}}
app.kubernetes.io/name: {{ include "resume-screening-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "resume-screening-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "resume-screening-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
