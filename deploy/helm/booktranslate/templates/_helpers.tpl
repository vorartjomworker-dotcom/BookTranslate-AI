{{- define "booktranslate.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "booktranslate.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "booktranslate.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "booktranslate.labels" -}}
app.kubernetes.io/name: {{ include "booktranslate.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "booktranslate.selectorLabels" -}}
app.kubernetes.io/name: {{ include "booktranslate.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "booktranslate.secretEnv" -}}
- name: DATABASE_URL
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.databaseUrl | quote }}}}
- name: REDIS_URL
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.redisUrl | quote }}}}
- name: BOOTSTRAP_ADMIN_TOKEN
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.bootstrapAdminToken | quote }}, optional: true}}
- name: AUTH_SIGNING_SECRET
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.authSigningSecret | quote }}}}
- name: OIDC_CLIENT_SECRET
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.oidcClientSecret | quote }}, optional: true}}
- name: SCIM_BEARER_TOKEN
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.scimBearerToken | quote }}, optional: true}}
- name: S3_ACCESS_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.s3AccessKey | quote }}}}
- name: S3_SECRET_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.s3SecretKey | quote }}}}
- name: OPENAI_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.openaiApiKey | quote }}, optional: true}}
- name: KIMI_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.kimiApiKey | quote }}, optional: true}}
- name: GEMINI_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.geminiApiKey | quote }}, optional: true}}
- name: AITUNNEL_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.aitunnelApiKey | quote }}, optional: true}}
- name: METRICS_TOKEN
  valueFrom: {secretKeyRef: {name: {{ .Values.secrets.existingSecret | quote }}, key: {{ .Values.secrets.keys.metricsToken | quote }}, optional: true}}
{{- end -}}

{{- define "booktranslate.configEnv" -}}
- name: APP_ENVIRONMENT
  value: {{ .Values.config.appEnvironment | quote }}
- name: AUTH_REQUIRED
  value: {{ .Values.config.authRequired | quote }}
- name: AUDIT_ENABLED
  value: {{ .Values.config.auditEnabled | quote }}
- name: CORS_ORIGINS
  value: {{ .Values.config.corsOrigins | quote }}
- name: STORAGE_BACKEND
  value: {{ .Values.config.storageBackend | quote }}
- name: S3_ENDPOINT_URL
  value: {{ .Values.config.s3EndpointUrl | quote }}
- name: S3_BUCKET
  value: {{ .Values.config.s3Bucket | quote }}
- name: S3_REGION
  value: {{ .Values.config.s3Region | quote }}
- name: S3_USE_SSL
  value: {{ .Values.config.s3UseSsl | quote }}
- name: S3_ADDRESSING_STYLE
  value: {{ .Values.config.s3AddressingStyle | quote }}
- name: S3_PRESIGN_DOWNLOADS
  value: {{ .Values.config.s3PresignDownloads | quote }}
- name: OIDC_ENABLED
  value: {{ .Values.config.oidcEnabled | quote }}
- name: OIDC_ISSUER
  value: {{ .Values.config.oidcIssuer | quote }}
- name: OIDC_CLIENT_ID
  value: {{ .Values.config.oidcClientId | quote }}
- name: OIDC_REDIRECT_URI
  value: {{ .Values.config.oidcRedirectUri | quote }}
- name: OIDC_FRONTEND_REDIRECT_URI
  value: {{ .Values.config.oidcFrontendRedirectUri | quote }}
- name: OIDC_SCOPES
  value: {{ .Values.config.oidcScopes | quote }}
- name: OIDC_ROLE_CLAIM
  value: {{ .Values.config.oidcRoleClaim | quote }}
- name: OIDC_DEFAULT_ROLE
  value: {{ .Values.config.oidcDefaultRole | quote }}
- name: SCIM_ENABLED
  value: {{ .Values.config.scimEnabled | quote }}
- name: SCIM_DEFAULT_ROLE
  value: {{ .Values.config.scimDefaultRole | quote }}
- name: SCIM_ROLE_GROUP_PREFIX
  value: {{ .Values.config.scimRoleGroupPrefix | quote }}
- name: VISION_PROVIDER
  value: {{ .Values.config.visionProvider | quote }}
- name: VISION_MODEL
  value: {{ .Values.config.visionModel | quote }}
- name: OTEL_ENABLED
  value: {{ .Values.config.otelEnabled | quote }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ .Values.config.otelExporterOtlpEndpoint | quote }}
- name: SESSION_ACCESS_TTL_SECONDS
  value: {{ .Values.config.sessionAccessTtlSeconds | quote }}
- name: SESSION_REFRESH_TTL_SECONDS
  value: {{ .Values.config.sessionRefreshTtlSeconds | quote }}
- name: PROVIDER_FEEDBACK_TTL_SECONDS
  value: {{ .Values.config.providerFeedbackTtlSeconds | quote }}
- name: PROVIDER_COOLDOWN_DEFAULT_SECONDS
  value: {{ .Values.config.providerCooldownDefaultSeconds | quote }}
- name: FIGURE_RENDER_DEFAULT_MODE
  value: {{ .Values.config.figureRenderDefaultMode | quote }}
{{- end -}}
