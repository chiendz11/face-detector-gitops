apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: face-detector-staging
  namespace: ${ARGOCD_NAMESPACE}
spec:
  project: default
  source:
    repoURL: https://github.com/${GITHUB_REPOSITORY}.git
    targetRevision: ${TARGET_REVISION}
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
${IMAGE_PULL_SECRET_PARAMETER}
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