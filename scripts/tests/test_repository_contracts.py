from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str) -> dict:
    document = yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))
    if True in document and "on" not in document:
        document["on"] = document.pop(True)
    return document


class RepositoryBoundaryTest(unittest.TestCase):
    def test_gitops_repo_has_no_application_or_terraform_sources(self) -> None:
        for path in ("backend", "frontend-admin", "edge-client", "nginx", "terraform", "aws"):
            self.assertFalse((REPO_ROOT / path).exists(), path)

    def test_promotions_accept_only_versioned_dispatch_events(self) -> None:
        staging = load_yaml(".github/workflows/gitops-staging.yml")
        production = load_yaml(".github/workflows/gitops-production.yml")

        self.assertEqual(staging["on"]["repository_dispatch"]["types"], ["promote-staging-v1"])
        self.assertEqual(production["on"]["repository_dispatch"]["types"], ["promote-production-v1"])

    def test_promotion_workflows_authenticate_dispatch_actor(self) -> None:
        for workflow in ("gitops-staging.yml", "gitops-production.yml"):
            text = (REPO_ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            self.assertIn("APP_RELEASE_BOT_LOGIN", text)
            self.assertIn("GITOPS_WRITER_APP_PRIVATE_KEY", text)

    def test_argocd_project_is_limited_to_gitops_repo_and_app_namespace(self) -> None:
        project = (REPO_ROOT / "deploy/argocd/face-detector-project.yaml.tpl").read_text(
            encoding="utf-8"
        )

        self.assertIn('${ARGOCD_REPO_URL}', project)
        self.assertIn('namespace: ${APP_NAMESPACE}', project)
        self.assertIn("clusterResourceWhitelist: []", project)
        self.assertIn("kind: Secret", project)


if __name__ == "__main__":
    unittest.main()
