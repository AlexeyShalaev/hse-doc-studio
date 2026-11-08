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

{{- define "hds.backupsPvcName" -}}
{{- default (printf "%s-backups" (include "hds.fullname" .)) .Values.backups.local.persistence.existingClaim -}}
{{- end -}}

{{/* Окружение бэкапов (только api): корень локальных назначений и начальная настройка. */}}
{{- define "hds.backupsEnv" -}}
{{- $b := .Values.backups }}
{{- $secret := include "hds.secretName" . }}
{{- if $b.local.enabled }}
- {name: HSE_STUDIO__BACKUPS__LOCAL_ROOT, value: /backups}
{{- end }}
- {name: HSE_STUDIO__BACKUPS__PROVISION__DESTINATION_KIND, value: {{ $b.destination.kind | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__NAME, value: {{ $b.destination.name | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__LOCAL_PATH, value: {{ $b.destination.path | quote }}}
{{- if eq $b.destination.kind "s3" }}
- {name: HSE_STUDIO__BACKUPS__PROVISION__ENDPOINT, value: {{ $b.destination.endpoint | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__REGION, value: {{ $b.destination.region | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__BUCKET, value: {{ required "backups.destination.bucket обязателен для kind=s3" $b.destination.bucket | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__PREFIX, value: {{ $b.destination.prefix | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__PATH_STYLE, value: {{ $b.destination.pathStyle | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__ACCESS_KEY, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: backup-access-key, optional: true}}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__SECRET_KEY, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: backup-secret-key, optional: true}}}
{{- end }}
- {name: HSE_STUDIO__BACKUPS__PROVISION__SCHEDULE_ENABLED, value: {{ $b.schedule.enabled | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__SCHEDULE_KIND, value: {{ $b.schedule.kind | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__INTERVAL_HOURS, value: {{ $b.schedule.intervalHours | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__CRON, value: {{ $b.schedule.cron | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__KEEP_LAST, value: {{ $b.schedule.keepLast | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__KEEP_DAYS, value: {{ $b.schedule.keepDays | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__ENCRYPTION_MODE, value: {{ $b.encryptionMode | quote }}}
- {name: HSE_STUDIO__BACKUPS__PROVISION__NOTIFY_ADMINS, value: {{ $b.notifyAdmins | quote }}}
{{- if eq $b.encryptionMode "passphrase" }}
- {name: HSE_STUDIO__BACKUPS__PROVISION__PASSPHRASE, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: backup-passphrase, optional: true}}}
{{- end }}
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
{{- with .Values.s3.publicEndpoint }}
- {name: HSE_STUDIO__S3__PUBLIC_ENDPOINT, value: {{ . | quote }}}
{{- end }}
{{- if ne (default "presigned" .Values.s3.outsideRunnerAccess) "presigned" }}
- {name: HSE_STUDIO__S3__OUTSIDE_RUNNER_ACCESS, value: {{ .Values.s3.outsideRunnerAccess | quote }}}
{{- end }}
{{- if .Values.s3.sharedRunnersOutside }}
- {name: HSE_STUDIO__S3__SHARED_RUNNERS_OUTSIDE, value: "true"}
{{- end }}
{{- if .Values.s3.corsOrigins }}
- {name: HSE_STUDIO__S3__CORS_ORIGINS, value: {{ .Values.s3.corsOrigins | toJson | quote }}}
{{- end }}
- {name: HSE_STUDIO__MAIL__HOST, value: {{ .Values.mail.host | quote }}}
- {name: HSE_STUDIO__MAIL__PORT, value: {{ .Values.mail.port | quote }}}
- {name: HSE_STUDIO__MAIL__USERNAME, value: {{ .Values.mail.username | quote }}}
- {name: HSE_STUDIO__MAIL__FROM_ADDRESS, value: {{ .Values.mail.fromAddress | quote }}}
- {name: HSE_STUDIO__LANGUAGETOOL__POOL_REPLICAS, value: {{ .Values.services.languagetoolReplicas | toJson | quote }}}
- {name: HSE_STUDIO__MODEL_SERVERS__LOCAL_ENABLED, value: {{ .Values.modelServers.local.enabled | quote }}}
- {name: HSE_STUDIO__OFFICE_EDITOR__POOL_REPLICAS, value: {{ .Values.services.officeEditorReplicas | toJson | quote }}}
- {name: HSE_STUDIO__OFFICE_EDITOR__BACKEND_INTERNAL_URL, value: {{ default (printf "http://%s:%v" (include "hds.fullname" .) .Values.service.port) .Values.services.backendInternalUrl | quote }}}
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
- {name: HSE_STUDIO__OFFICE_EDITOR__JWT_SECRET, valueFrom: {secretKeyRef: {name: {{ $secret }}, key: office-jwt-secret, optional: true}}}
{{- end -}}

{{/* Namespace подов сборки исполнителя kubernetes: свой или namespace релиза. */}}
{{- define "hds.runnerBuildNamespace" -}}
{{- default .Release.Namespace .Values.runner.kubernetes.namespace -}}
{{- end -}}

{{/*
Выжимка values о раннерах для экрана изоляции в админке (HSE_STUDIO__RUNNER_CLUSTER__DECLARED): то, что задано
в чарте, а не проверенное в кластере. Без секретов и без содержимого extraEgress (только число правил).
*/}}
{{- define "hds.runnerCluster" -}}
{{- $r := .Values.runner -}}
{{- $k := $r.kubernetes -}}
{{- $full := include "hds.fullname" . -}}
{{- $kube := eq $r.executor "kubernetes" -}}
{{- $buildNs := include "hds.runnerBuildNamespace" . -}}
{{- $storageKind := "hostPath" -}}
{{- if $kube -}}{{- $storageKind = ternary "pvc" "emptyDir" $r.persistence.enabled -}}{{- end -}}
{{- $quota := dict "enabled" (and $kube $k.quota.enabled) "hard" (dict "pods" ($k.quota.pods | toString) "requests.cpu" ($k.quota.requestsCpu | toString) "requests.memory" ($k.quota.requestsMemory | toString) "limits.cpu" ($k.quota.limitsCpu | toString) "limits.memory" ($k.quota.limitsMemory | toString) "requests.ephemeral-storage" ($k.quota.requestsEphemeralStorage | toString) "limits.ephemeral-storage" ($k.quota.limitsEphemeralStorage | toString)) -}}
{{- $range := dict "enabled" (and $kube $k.limitRange.enabled) "default" $k.limitRange.default "defaultRequest" $k.limitRange.defaultRequest "max" $k.limitRange.max -}}
{{- $runner := dict "enabled" $r.enabled "executor" $r.executor "replicas" $r.replicas "deployment" (printf "%s-runner" $full) "serviceAccount" (ternary (printf "%s-runner" $full) "" $kube) "resources" $r.resources "tmpSizeLimit" (ternary ($r.tmpSizeLimit | toString) "" $kube) "storageKind" $storageKind "storageClass" (ternary $r.persistence.storageClassName "" $kube) "storageSize" (ternary ($r.persistence.size | toString) "" $kube) "runAsUser" .Values.podSecurityContext.runAsUser -}}
{{- $build := dict "namespace" $buildNs "resources" $k.resources "workSizeLimit" ($k.workSizeLimit | toString) "tmpSizeLimit" ($k.tmpSizeLimit | toString) "activeDeadlineSeconds" $k.activeDeadlineSeconds "runtimeClassName" $k.runtimeClassName "runAsUser" $k.runAsUser "networkPolicy" $k.networkPolicy.enabled "quota" $quota "limitRange" $range -}}
{{- $np := $r.networkPolicy -}}
{{- $egress := dict "enabled" (and $np.enabled (or $r.enabled $r.installFromUi.enabled)) "studioPort" 8000 "apiServerCidrs" $np.apiServerCidrs "apiServerPorts" $np.apiServerPorts "extraRules" (len $np.extraEgress) -}}
{{- toJson (dict "releaseNamespace" .Release.Namespace "runner" $runner "build" $build "runnerEgress" $egress) -}}
{{- end -}}

{{/* Студии нужен ServiceAccount с токеном: установка раннеров из админки или чтение изоляции раннеров. */}}
{{- define "hds.apiNeedsKubeApi" -}}
{{- if or .Values.runner.installFromUi.enabled .Values.runner.isolationInfo.readCluster -}}true{{- end -}}
{{- end -}}
