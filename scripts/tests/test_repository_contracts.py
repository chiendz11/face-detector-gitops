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

    def test_argocd_application_project_is_limited_to_app_namespace(self) -> None:
        project = (REPO_ROOT / "deploy/argocd/projects/face-detector.yaml.tpl").read_text(
            encoding="utf-8"
        )

        self.assertIn('${ARGOCD_REPO_URL}', project)
        self.assertIn('namespace: ${APP_NAMESPACE}', project)
        self.assertIn("clusterResourceWhitelist: []", project)
        self.assertIn("kind: Secret", project)

    def test_platform_project_has_a_separate_privileged_boundary(self) -> None:
        project = (REPO_ROOT / "deploy/argocd/projects/platform.yaml.tpl").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: face-detector-platform", project)
        self.assertIn("https://prometheus-community.github.io/helm-charts", project)
        self.assertIn("https://grafana.github.io/helm-charts", project)
        self.assertIn('kind: "*"', project)
        self.assertIn("namespace: monitoring", project)
        self.assertIn("namespace: kube-system", project)

    def test_platform_workloads_are_declared_as_argocd_applications(self) -> None:
        templates = REPO_ROOT / "deploy/helm/platform-applications/templates"
        expected = {
            "alloy.yaml",
            "cluster-autoscaler.yaml",
            "external-dns.yaml",
            "keda.yaml",
            "kube-prometheus-stack.yaml",
            "loki.yaml",
            "metrics-server.yaml",
            "platform-resources.yaml",
        }

        self.assertEqual({path.name for path in templates.glob("*.yaml")}, expected)

        root = (REPO_ROOT / "deploy/argocd/applications/platform.yaml.tpl").read_text(
            encoding="utf-8"
        )
        self.assertIn("path: deploy/helm/platform-applications", root)
        self.assertIn("global.automated", root)
        self.assertIn("clusterAutoscaler.roleArn", root)
        self.assertIn("externalDns.roleArn", root)

    def test_every_platform_addon_has_environment_values(self) -> None:
        addons = {
            "alloy",
            "cluster-autoscaler",
            "external-dns",
            "keda",
            "kube-prometheus-stack",
            "loki",
            "metrics-server",
        }

        for addon in addons:
            root = REPO_ROOT / "deploy/platform" / addon
            self.assertTrue((root / "values-common.yaml").is_file(), addon)
            for environment in ("sandbox", "staging", "production"):
                self.assertTrue((root / f"values-{environment}.yaml").is_file(), f"{addon}:{environment}")

    def test_ci_renders_the_same_pinned_platform_versions(self) -> None:
        values = load_yaml("deploy/helm/platform-applications/values.yaml")
        workflow = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")

        version_keys = {
            "metricsServer": "metrics-server",
            "kubePrometheusStack": "kube-prometheus-stack",
            "loki": "loki",
            "alloy": "alloy",
            "keda": "keda",
            "clusterAutoscaler": "cluster-autoscaler",
            "externalDns": "external-dns",
        }
        for values_key, chart_name in version_keys.items():
            version = str(values[values_key]["chartVersion"])
            self.assertIn(f"{chart_name}", workflow)
            self.assertIn(f"--version {version}", workflow)


if __name__ == "__main__":
    unittest.main()
