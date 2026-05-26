apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: face-detector
  namespace: ${ARGOCD_NAMESPACE}
spec:
  description: Face Detector GitOps boundary
  sourceRepos:
    - "${ARGOCD_REPO_URL}"
  destinations:
    - server: https://kubernetes.default.svc
      namespace: ${APP_NAMESPACE}
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - group: ""
      kind: ConfigMap
    - group: ""
      kind: Service
    - group: apps
      kind: Deployment
    - group: batch
      kind: Job
    - group: autoscaling
      kind: HorizontalPodAutoscaler
    - group: keda.sh
      kind: ScaledObject
    - group: monitoring.coreos.com
      kind: ServiceMonitor
    - group: monitoring.coreos.com
      kind: PrometheusRule
    - group: monitoring.coreos.com
      kind: AlertmanagerConfig
  namespaceResourceBlacklist:
    - group: ""
      kind: Secret
  syncWindows:
    - kind: deny
      schedule: "* * * * *"
      duration: 24h
      applications:
        - face-detector-production
      manualSync: true
  orphanedResources:
    warn: true
