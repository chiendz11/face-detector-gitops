apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: face-detector-platform
  namespace: ${ARGOCD_NAMESPACE}
spec:
  description: Privileged GitOps boundary for cluster platform workloads
  sourceRepos:
    - "${ARGOCD_REPO_URL}"
    - https://grafana.github.io/helm-charts
    - https://kedacore.github.io/charts
    - https://kubernetes-sigs.github.io/external-dns/
    - https://kubernetes-sigs.github.io/metrics-server/
    - https://kubernetes.github.io/autoscaler
    - https://prometheus-community.github.io/helm-charts
  destinations:
    - server: https://kubernetes.default.svc
      namespace: ${ARGOCD_NAMESPACE}
    - server: https://kubernetes.default.svc
      namespace: monitoring
    - server: https://kubernetes.default.svc
      namespace: kube-system
    - server: https://kubernetes.default.svc
      namespace: keda
  clusterResourceWhitelist:
    - group: "*"
      kind: "*"
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
  syncWindows:
    - kind: deny
      schedule: "* * * * *"
      duration: 24h
      applications:
        - face-detector-platform-production-*
      manualSync: true
  orphanedResources:
    warn: true
