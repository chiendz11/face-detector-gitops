apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: face-detector-production
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: face-detector
  source:
    repoURL: "${ARGOCD_REPO_URL}"
    targetRevision: ${TARGET_REVISION}
    path: deploy/helm/face-detector
    helm:
      valueFiles:
        - values.yaml
        - values-production.yaml
      parameters:
        - name: backend.image.repository
          value: ${BACKEND_IMAGE_REPOSITORY}
        - name: worker.image.repository
          value: ${BACKEND_IMAGE_REPOSITORY}
        - name: frontendAdmin.image.repository
          value: ${FRONTEND_IMAGE_REPOSITORY}
        - name: nginx.image.repository
          value: ${NGINX_IMAGE_REPOSITORY}
${IMAGE_PULL_SECRET_PARAMETER}
${PUBLIC_ENDPOINT_PARAMETER}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${APP_NAMESPACE}
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
