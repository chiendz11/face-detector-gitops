{{- define "face-detector.imageRef" -}}
{{- $repository := required "image.repository is required" .repository -}}
{{- $digest := default "" .digest -}}
{{- $requireDigest := default false .requireDigest -}}
{{- if and $requireDigest (not $digest) -}}
{{- fail (printf "image.digest is required for %s when image.requireDigest=true" $repository) -}}
{{- end -}}
{{- if and $digest (not (regexMatch "^sha256:[0-9a-f]{64}$" $digest)) -}}
{{- fail (printf "image.digest for %s must be a sha256 digest" $repository) -}}
{{- end -}}
{{- if $digest -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- printf "%s:%s" $repository .tag -}}
{{- end -}}
{{- end -}}
