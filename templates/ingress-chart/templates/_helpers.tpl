{{- define "ingress-chart.fqdn" -}}
{{- $domainType := .Values.ingress.domainType | default "internal" -}}
{{- $domain := index .Values.global.domains $domainType -}}
{{- $host := .Values.ingress.host -}}
{{- ternary $domain (printf "%s.%s" $host $domain) (eq $host "") -}}
{{- end -}}
