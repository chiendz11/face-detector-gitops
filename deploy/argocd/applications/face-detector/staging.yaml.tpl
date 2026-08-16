apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: face-detector-staging
  namespace: ${ARGOCD_NAMESPACE}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  labels:
    app.kubernetes.io/part-of: face-detector
spec:
  project: face-detector
  source:
    repoURL: "${ARGOCD_REPO_URL}"
    targetRevision: "${TARGET_REVISION}"
    path: deploy/helm/face-detector
    helm:
      valueFiles:
        - values.yaml
        - values-staging.yaml
      parameters:
        - name: backend.image.repository
          value: ${BACKEND_IMAGE_REPOSITORY}
        - name: worker.image.repository
          value: ${BACKEND_IMAGE_REPOSITORY}
        - name: frontendAdmin.image.repository
          value: ${FRONTEND_IMAGE_REPOSITORY}
        - name: nginx.image.repository
          value: ${NGINX_IMAGE_REPOSITORY}
${IMAGE_DIGEST_PARAMETER}
${IMAGE_PULL_SECRET_PARAMETER}
${PUBLIC_ENDPOINT_PARAMETER}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${APP_NAMESPACE}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
