apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: face-detector-platform-${DEPLOYMENT_ENVIRONMENT}
  namespace: ${ARGOCD_NAMESPACE}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  labels:
    app.kubernetes.io/part-of: face-detector-platform
    face-detector.io/environment: "${DEPLOYMENT_ENVIRONMENT}"
spec:
  project: face-detector-platform
  source:
    repoURL: "${ARGOCD_REPO_URL}"
    targetRevision: "${TARGET_REVISION}"
    path: deploy/helm/platform-applications
    helm:
      parameters:
        - name: global.repoURL
          value: "${ARGOCD_REPO_URL}"
        - name: global.targetRevision
          value: "${TARGET_REVISION}"
        - name: global.environment
          value: "${DEPLOYMENT_ENVIRONMENT}"
        - name: global.environmentIdentity
          value: "${ENVIRONMENT_IDENTITY}"
        - name: global.clusterName
          value: "${CLUSTER_NAME}"
        - name: global.clusterVersion
          value: "${CLUSTER_VERSION}"
        - name: global.awsRegion
          value: "${AWS_REGION}"
        - name: global.automated
          value: "${PLATFORM_AUTOMATED_SYNC}"
        - name: platformResources.monitoringPortForwardGroup
          value: "${MONITORING_PORT_FORWARD_GROUP}"
        - name: clusterAutoscaler.enabled
          value: "${CLUSTER_AUTOSCALER_ENABLED}"
        - name: clusterAutoscaler.roleArn
          value: "${CLUSTER_AUTOSCALER_ROLE_ARN}"
        - name: externalDns.enabled
          value: "${EXTERNAL_DNS_ENABLED}"
        - name: externalDns.provider
          value: "${EXTERNAL_DNS_PROVIDER}"
        - name: externalDns.baseDomain
          value: "${EXTERNAL_DNS_BASE_DOMAIN}"
        - name: externalDns.zoneId
          value: "${EXTERNAL_DNS_ZONE_ID}"
        - name: externalDns.roleArn
          value: "${EXTERNAL_DNS_ROLE_ARN}"
        - name: externalDns.cloudflareSecretName
          value: "${EXTERNAL_DNS_CLOUDFLARE_SECRET_NAME}"
  destination:
    server: https://kubernetes.default.svc
    namespace: ${ARGOCD_NAMESPACE}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
