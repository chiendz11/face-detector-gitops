{{- define "face-detector-platform.applicationMetadata" -}}
namespace: {{ .Values.global.argocdNamespace }}
finalizers:
  - resources-finalizer.argocd.argoproj.io
labels:
  app.kubernetes.io/part-of: face-detector-platform
  face-detector.io/environment: {{ .Values.global.environment | quote }}
{{- end }}

{{- define "face-detector-platform.destination" -}}
server: https://kubernetes.default.svc
{{- end }}

{{- define "face-detector-platform.syncPolicy" -}}
syncPolicy:
  {{- if .Values.global.automated }}
  automated:
    prune: true
    selfHeal: true
  {{- end }}
  syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
{{- end }}

{{- define "face-detector-platform.valuesSource" -}}
- repoURL: {{ required "global.repoURL is required" .Values.global.repoURL | quote }}
  targetRevision: {{ .Values.global.targetRevision | quote }}
  ref: values
{{- end }}
