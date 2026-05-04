{{- define "face-detector.imageRef" -}}
{{- $repository := required "image.repository is required" .repository -}}
{{- $digest := default "" .digest -}}
{{- if $digest -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- printf "%s:%s" $repository .tag -}}
{{- end -}}
{{- end -}}