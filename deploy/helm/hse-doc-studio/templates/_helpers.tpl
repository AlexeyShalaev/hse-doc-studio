{{- define "hds.name" -}}
{{- .Chart.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "hds.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "hds.labels" -}}
app.kubernetes.io/name: {{ include "hds.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "hds.selector" -}}
app.kubernetes.io/name: {{ include "hds.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "hds.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{- define "hds.secretName" -}}
{{- default (printf "%s-secrets" (include "hds.fullname" .)) .Values.secrets.existingSecret -}}
{{- end -}}

{{- define "hds.pvcName" -}}
{{- default (printf "%s-data" (include "hds.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}

{{/* Общее окружение api и Job миграций. Секреты берутся из Secret, не из values. */}}
{{- define "hds.env" -}}
- {name: HSE_STUDIO__MODE, value: server}
- {name: HSE_STUDIO__SERVER__HOST, value: "0.0.0.0"}
- {name: HSE_STUDIO__SERVER__PORT, value: "8000"}
- {name: HSE_STUDIO__DATA_DIR, value: /data}
- {name: HSE_STUDIO__LOGGING__USE_JSON, value: "true"}
- {name: HSE_STUDIO__AUTH__PUBLIC_URL, value: {{ required "publicUrl обязателен" .Values.publicUrl | quote }}}
- {name: HSE_STUDIO__AUTH__TRUSTED_PROXIES, value: {{ .Values.trustedProxies | toJson | quote }}}
- {name: HSE_STUDIO__S3__ENDPOINT, value: {{ .Values.s3.endpoint | quote }}}
- {name: HSE_STUDIO__S3__BUCKET, value: {{ .Values.s3.bucket | quote }}}
- {name: HSE_STUDIO__S3__REGION, value: {{ .Values.s3.region | quote }}}
- {name: HSE_STUDIO__MAIL__HOST, value: {{ .Values.mail.host | quote }}}
- {name: HSE_STUDIO__MAIL__PORT, value: {{ .Values.mail.port | quote }}}
- {name: HSE_STUDIO__MAIL__USERNAME, value: {{ .Values.mail.username | quote }}}
- {name: HSE_STUDIO__MAIL__FROM_ADDRESS, value: {{ .Values.mail.fromAddress | quote }}}
{{- range $key, $value := .Values.api.extraEnv }}
- {name: {{ $key }}, value: {{ $value | quote }}}
{{- end }}
{{- $secret := include "hds.secretName" . }}
- {name: HSE_STUDIO__DB__DSN, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: dsn}}}
- {name: HSE_STUDIO__SECRETS__KEY, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: secrets-key}}}
- {name: HSE_STUDIO__S3__ACCESS_KEY, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: s3-access-key}}}
- {name: HSE_STUDIO__S3__SECRET_KEY, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: s3-secret-key}}}
- {name: HSE_STUDIO__JOBS__RUNNER_BOOTSTRAP_TOKEN, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: runner-bootstrap-token, optional: true}}}
- {name: HSE_STUDIO__MAIL__PASSWORD, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: smtp-password, optional: true}}}
- {name: HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: health-token, optional: true}}}
- {name: HSE_STUDIO__OBSERVABILITY__METRICS_TOKEN, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: metrics-token, optional: true}}}
{{- end -}}
