from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def detect_bash() -> tuple[str, str]:
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for candidate in (
            program_files / "Git/bin/bash.exe",
            program_files / "Git/usr/bin/bash.exe",
        ):
            if candidate.exists():
                return str(candidate), "git-bash"
    return "bash", "default"


BASH_EXECUTABLE, BASH_FLAVOR = detect_bash()


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in document and "on" not in document:
        document["on"] = document.pop(True)
    return document


def extract_run_step(document: dict[str, Any], job_name: str, step_name: str) -> str:
    steps = document["jobs"][job_name]["steps"]
    for step in steps:
        if step.get("name") == step_name:
            return str(step["run"])
    raise AssertionError(f"Unable to find step {step_name!r} in job {job_name!r}")


def extract_uses_step(document: dict[str, Any], job_name: str, step_name: str) -> str:
    steps = document["jobs"][job_name]["steps"]
    for step in steps:
        if step.get("name") == step_name:
            return str(step["uses"])
    raise AssertionError(f"Unable to find step {step_name!r} in job {job_name!r}")


def extract_step(document: dict[str, Any], job_name: str, step_name: str) -> dict[str, Any]:
    steps = document["jobs"][job_name]["steps"]
    for step in steps:
        if step.get("name") == step_name:
            return step
    raise AssertionError(f"Unable to find step {step_name!r} in job {job_name!r}")


def replace_command(script: str, command: str, replacement: str) -> str:
    return re.sub(rf'(?<![A-Za-z0-9_./-]){re.escape(command)}(?=\s)', replacement, script)


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def to_bash_path(path: Path | str) -> str:
    value = str(path)
    if len(value) >= 2 and value[1] == ":":
        drive = value[0].lower()
        rest = value[2:].replace("\\", "/")
        if BASH_FLAVOR == "git-bash":
            return f"/{drive}/{rest.lstrip('/')}"
        return f"/mnt/{drive}/{rest.lstrip('/')}"
    return value


def shell_python_command() -> str:
    return shlex.quote(to_bash_path(Path(sys.executable)))


def write_fake_jq(path: Path) -> None:
    write_executable(
        path,
        r'''
        #!/usr/bin/env python3
        import json
        import sys


        def main() -> int:
            args = sys.argv[1:]
            raw = False
            compact = False
            vars_map = {}
            index = 0

            while index < len(args):
                arg = args[index]
                if arg == "-r":
                    raw = True
                    index += 1
                    continue
                if arg == "-c":
                    compact = True
                    index += 1
                    continue
                if arg == "--arg":
                    vars_map[args[index + 1]] = args[index + 2]
                    index += 3
                    continue
                break

            query = args[index]
            query = query.replace('\\"', '"')
            index += 1
            input_path = args[index] if index < len(args) else None

            if input_path:
                with open(input_path, encoding="utf-8") as handle:
                    data = json.load(handle)
            else:
                payload = sys.stdin.read().strip()
                data = json.loads(payload) if payload else None

            while isinstance(data, str):
                stripped = data.strip()
                if not stripped or stripped[0] not in "[{":
                    break
                data = json.loads(stripped)

            def emit(obj):
                if raw and isinstance(obj, str):
                    sys.stdout.write(obj)
                    return
                separators = (",", ":") if compact else None
                sys.stdout.write(json.dumps(obj, separators=separators))

            if query == ".[]":
                for item in data:
                    sys.stdout.write(json.dumps(item, separators=(",", ":")) + "\n")
                return 0

            if query in {".name", ".repository", ".ref", ".sbom"}:
                emit(data[query[1:]])
                return 0

            if query == '. + [{"name": $n, "repository": $repo, "subject_digest": $d, "sbom_path": $sbom}]':
                data.append(
                    {
                        "name": vars_map["n"],
                        "repository": vars_map["repo"],
                        "subject_digest": vars_map["d"],
                        "sbom_path": vars_map["sbom"],
                    }
                )
                emit(data)
                return 0

            if query == '. + [{"name": $n, "repository": $r, "tag": $t, "digest": $d}]':
                data.append(
                    {
                        "name": vars_map["n"],
                        "repository": vars_map["r"],
                        "tag": vars_map["t"],
                        "digest": vars_map["d"],
                    }
                )
                emit(data)
                return 0

            if query == '. + [{"ref": $ref, "sbom": $sbom}]':
                data.append({"ref": vars_map["ref"], "sbom": vars_map["sbom"]})
                emit(data)
                return 0

            raise SystemExit(f"Unsupported jq query: {query}")


        if __name__ == "__main__":
            raise SystemExit(main())
        ''',
    )


def run_bash(
    script: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    commands: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    shell_env = os.environ.copy()
    export_block = ""
    if env:
        shell_env.update(env)
        export_block = "\n".join(
            f"export {key}={shlex.quote(value)}"
            for key, value in env.items()
        )

    command_block = ""
    if commands:
        command_block = "\n".join(
            f"{name}() {{ {command} \"$@\"; }}"
            for name, command in commands.items()
        )

    return subprocess.run(
        [BASH_EXECUTABLE, "-c", f"set -euo pipefail\n{export_block}\n{command_block}\n{script}"],
        cwd=cwd,
        env=shell_env,
        text=True,
        capture_output=True,
        check=False,
    )


class SignImagesActionContractTest(unittest.TestCase):
    def test_sign_images_action_executes_expected_cosign_sequence(self) -> None:
        action = load_yaml(REPO_ROOT / ".github/actions/sign-images/action.yml")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            artifacts = root / ".artifacts"
            artifacts.mkdir()
            (artifacts / "sign-targets.json").write_text(
                json.dumps(
                    [
                        {"ref": "ghcr.io/example/backend@sha256:" + "1" * 64, "sbom": ".artifacts/sbom/backend.spdx.json"},
                        {"ref": "ghcr.io/example/admin@sha256:" + "2" * 64, "sbom": ".artifacts/sbom/admin.spdx.json"},
                    ]
                ),
                encoding="utf-8",
            )

            bin_dir = root / "bin"
            bin_dir.mkdir()
            write_fake_jq(bin_dir / "jq")
            write_executable(
                bin_dir / "python",
                '''
                #!/usr/bin/env bash
                exec python3 "$@"
                ''',
            )
            write_executable(
                bin_dir / "cosign",
                '''
                #!/usr/bin/env python3
                import json
                import os
                import sys

                with open(os.environ["COSIGN_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(sys.argv[1:]) + "\\n")
                ''',
            )
            cosign_log = root / "cosign-log.jsonl"
            run_script = str(action["runs"]["steps"][0]["run"])
            run_script = replace_command(
                run_script,
                "jq",
                f"{shell_python_command()} {shlex.quote(to_bash_path(bin_dir / 'jq'))}",
            )
            run_script = replace_command(
                run_script,
                "cosign",
                f"{shell_python_command()} {shlex.quote(to_bash_path(bin_dir / 'cosign'))}",
            )

            result = run_bash(
                run_script,
                cwd=root,
                env={
                    "COSIGN_LOG": to_bash_path(cosign_log),
                    "GITHUB_REPOSITORY": "chiendz11/Face_dectector",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            commands = [json.loads(line) for line in cosign_log.read_text(encoding="utf-8").splitlines()]
            identity = "^https://github.com/chiendz11/Face_dectector/.github/workflows/[^@]+@.*$"
            expected = [
                ["sign", "--yes", "ghcr.io/example/backend@sha256:" + "1" * 64],
                [
                    "attest",
                    "--yes",
                    "--type",
                    "spdxjson",
                    "--predicate",
                    ".artifacts/sbom/backend.spdx.json",
                    "ghcr.io/example/backend@sha256:" + "1" * 64,
                ],
                [
                    "verify",
                    "--certificate-identity-regexp",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    "ghcr.io/example/backend@sha256:" + "1" * 64,
                ],
                [
                    "verify-attestation",
                    "--type",
                    "spdxjson",
                    "--certificate-identity-regexp",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    "ghcr.io/example/backend@sha256:" + "1" * 64,
                ],
                ["sign", "--yes", "ghcr.io/example/admin@sha256:" + "2" * 64],
                [
                    "attest",
                    "--yes",
                    "--type",
                    "spdxjson",
                    "--predicate",
                    ".artifacts/sbom/admin.spdx.json",
                    "ghcr.io/example/admin@sha256:" + "2" * 64,
                ],
                [
                    "verify",
                    "--certificate-identity-regexp",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    "ghcr.io/example/admin@sha256:" + "2" * 64,
                ],
                [
                    "verify-attestation",
                    "--type",
                    "spdxjson",
                    "--certificate-identity-regexp",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    "ghcr.io/example/admin@sha256:" + "2" * 64,
                ],
            ]
            self.assertEqual(commands, expected)


class GitOpsPromotionContractTest(unittest.TestCase):
    def _run_gitops_update_step(self, workflow_name: str, step_name: str, values_file: str) -> dict[str, Any]:
        workflow = load_yaml(REPO_ROOT / f".github/workflows/{workflow_name}")
        run_script = extract_run_step(workflow, "promote", step_name)
        run_script = run_script.replace('${{ steps.image-digests.outputs.backend_digest }}', 'sha256:' + '1' * 64)
        run_script = run_script.replace('${{ steps.image-digests.outputs.frontend_digest }}', 'sha256:' + '2' * 64)
        run_script = run_script.replace('${{ steps.image-digests.outputs.nginx_digest }}', 'sha256:' + '3' * 64)
        run_script = replace_command(run_script, "python", shell_python_command())

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            target_values = root / values_file
            target_values.parent.mkdir(parents=True)
            target_values.write_text(
                "backend:\n  image:\n    repository: ghcr.io/example/backend\nfeatureFlags:\n  demoMode: true\n",
                encoding="utf-8",
            )

            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            shutil.copy2(REPO_ROOT / "scripts/update_gitops_image_locks.py", scripts_dir / "update_gitops_image_locks.py")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            write_executable(
                bin_dir / "python",
                '''
                #!/usr/bin/env bash
                exec python3 "$@"
                ''',
            )

            result = run_bash(
                run_script,
                cwd=root,
                env={
                    "IMAGE_TAG": "commit-sha",
                },
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            return yaml.safe_load(target_values.read_text(encoding="utf-8"))

    def test_gitops_staging_contract_runs_lock_mutation_in_dry_run(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/gitops-staging.yml")
        self.assertEqual(workflow["on"]["workflow_run"]["workflows"], ["App Release"])
        self.assertIn("github.event.repository.default_branch", workflow["jobs"]["promote"]["if"])
        self.assertEqual(
            extract_run_step(workflow, "promote", "Commit staging promotion").splitlines()[0].strip(),
            'if git diff --quiet -- deploy/helm/face-detector/values-staging.yaml; then',
        )

        written = self._run_gitops_update_step(
            "gitops-staging.yml",
            "Update staging image digests",
            "deploy/helm/face-detector/values-staging.yaml",
        )

        self.assertEqual(written["backend"]["image"]["tag"], "commit-sha")
        self.assertEqual(written["backend"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertTrue(written["backend"]["image"]["requireDigest"])
        self.assertEqual(written["worker"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertTrue(written["worker"]["image"]["requireDigest"])
        self.assertEqual(written["frontendAdmin"]["image"]["digest"], "sha256:" + "2" * 64)
        self.assertTrue(written["frontendAdmin"]["image"]["requireDigest"])
        self.assertEqual(written["nginx"]["image"]["digest"], "sha256:" + "3" * 64)
        self.assertTrue(written["nginx"]["image"]["requireDigest"])
        self.assertEqual(written["featureFlags"], {"demoMode": True})

    def test_gitops_production_contract_runs_lock_mutation_in_dry_run(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/gitops-production.yml")
        self.assertEqual(workflow["on"]["release"]["types"], ["published"])
        self.assertEqual(workflow["jobs"]["promote"]["environment"], "production")
        self.assertIn('git rev-list -n 1 "$RELEASE_TAG"', extract_run_step(workflow, "promote", "Resolve release commit"))

        written = self._run_gitops_update_step(
            "gitops-production.yml",
            "Update production image digests",
            "deploy/helm/face-detector/values-production.yaml",
        )

        self.assertEqual(written["backend"]["image"]["tag"], "commit-sha")
        self.assertEqual(written["backend"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertTrue(written["backend"]["image"]["requireDigest"])
        self.assertEqual(written["worker"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertTrue(written["worker"]["image"]["requireDigest"])
        self.assertEqual(written["frontendAdmin"]["image"]["digest"], "sha256:" + "2" * 64)
        self.assertTrue(written["frontendAdmin"]["image"]["requireDigest"])
        self.assertEqual(written["nginx"]["image"]["digest"], "sha256:" + "3" * 64)
        self.assertTrue(written["nginx"]["image"]["requireDigest"])
        self.assertEqual(written["featureFlags"], {"demoMode": True})

    def test_shared_environment_values_require_immutable_digests(self) -> None:
        for values_name in ("values-staging.yaml", "values-production.yaml"):
            values = yaml.safe_load(
                (REPO_ROOT / "deploy/helm/face-detector" / values_name).read_text(encoding="utf-8")
            )
            for component in ("backend", "worker", "frontendAdmin", "nginx"):
                image = values[component]["image"]
                self.assertEqual(image["tag"], "unpromoted")
                self.assertEqual(image["digest"], "")
                self.assertTrue(image["requireDigest"], msg=f"{values_name}:{component}")

    def test_helm_digest_guard_and_ci_render_overrides_are_present(self) -> None:
        helper = (REPO_ROOT / "deploy/helm/face-detector/templates/_helpers.tpl").read_text(encoding="utf-8")
        infra_ci = (REPO_ROOT / ".github/workflows/reusable-infra-ci.yml").read_text(encoding="utf-8")

        self.assertIn("image.requireDigest=true", helper)
        self.assertIn("regexMatch \"^sha256:[0-9a-f]{64}$\"", helper)
        self.assertIn("image.digest is required", helper)
        self.assertIn("--set backend.image.digest=sha256:1111111111111111111111111111111111111111111111111111111111111111", infra_ci)
        self.assertIn("--set frontendAdmin.image.digest=sha256:2222222222222222222222222222222222222222222222222222222222222222", infra_ci)
        self.assertIn("--set nginx.image.digest=sha256:3333333333333333333333333333333333333333333333333333333333333333", infra_ci)


class AppCdSandboxBootstrapContractTest(unittest.TestCase):
    def test_sandbox_bootstrap_publishes_pr_images_and_overrides_helm_digests(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")
        bootstrap = workflow["jobs"]["bootstrap"]
        self.assertEqual(bootstrap["permissions"]["packages"], "write")

        digest_check = extract_step(workflow, "bootstrap", "Verify promoted image digests exist in Git")
        self.assertIn("deployment_environment != 'sandbox'", digest_check["if"])

        self.assertEqual(
            extract_uses_step(workflow, "bootstrap", "Set up Docker Buildx for sandbox images"),
            "docker/setup-buildx-action@8d2750c68a42422c14e847fe6c8ac0403b4cbd6f",
        )
        self.assertEqual(
            extract_uses_step(workflow, "bootstrap", "Build sandbox deploy images"),
            "./.github/actions/build-images",
        )
        self.assertEqual(
            extract_uses_step(workflow, "bootstrap", "Log in to GHCR for sandbox image publish"),
            "docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9",
        )

        resolve_script = extract_run_step(workflow, "bootstrap", "Resolve sandbox image digests")
        self.assertIn("face-detector-backend", resolve_script)
        self.assertIn("face-detector-admin", resolve_script)
        self.assertIn("face-detector-nginx", resolve_script)
        self.assertIn("backend.image.digest", resolve_script)
        self.assertIn("worker.image.digest", resolve_script)
        self.assertIn("frontendAdmin.image.digest", resolve_script)
        self.assertIn("nginx.image.digest", resolve_script)

        template = (REPO_ROOT / "deploy/argocd/staging-application.yaml.tpl").read_text(encoding="utf-8")
        self.assertIn("${IMAGE_DIGEST_PARAMETER}", template)

    def test_bootstrap_waits_for_argocd_sync_before_rollout_and_dumps_diagnostics(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")

        sync_script = extract_run_step(workflow, "bootstrap", "Wait for ArgoCD sync to requested revision")
        self.assertIn("argocd.argoproj.io/refresh=hard", sync_script)
        self.assertIn(".status.sync.revision", sync_script)
        self.assertIn('revision" = "$SOURCE_GIT_SHA"', sync_script)
        self.assertIn("Timed out waiting for ArgoCD application", sync_script)

        diagnostics = extract_step(workflow, "bootstrap", "Dump rollout diagnostics")
        self.assertIn("failure()", diagnostics["if"])
        diagnostics_script = diagnostics["run"]
        self.assertIn("kubectl get application", diagnostics_script)
        self.assertIn("kubectl get events", diagnostics_script)
        self.assertIn("kubectl describe deployment/${deployment}", diagnostics_script)
        self.assertIn("kubectl logs", diagnostics_script)

    def test_smoke_test_reads_admin_credentials_without_sourcing_dotenv(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")

        credentials_script = extract_run_step(workflow, "bootstrap", "Resolve smoke test credentials")
        self.assertIn('Path(".env.runtime")', credentials_script)
        self.assertIn('write_output("admin_username"', credentials_script)
        self.assertIn('write_output("admin_password"', credentials_script)

        smoke_step = extract_step(workflow, "bootstrap", "Run post-deploy smoke test")
        self.assertEqual(smoke_step["env"]["FACE_DETECTOR_ADMIN_USERNAME"], "${{ steps.smoke-credentials.outputs.admin_username }}")
        self.assertEqual(smoke_step["env"]["FACE_DETECTOR_ADMIN_PASSWORD"], "${{ steps.smoke-credentials.outputs.admin_password }}")
        self.assertNotIn(". ./.env.runtime", smoke_step["run"])
        self.assertNotIn("set -a", smoke_step["run"])

    def test_bootstrap_waits_for_public_dns_and_health_before_smoke(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")

        readiness_script = extract_run_step(workflow, "bootstrap", "Wait for public app readiness")
        self.assertIn("getent hosts", readiness_script)
        self.assertIn("/health", readiness_script)
        self.assertIn("curl --fail", readiness_script)
        self.assertIn("Timed out waiting for public app readiness", readiness_script)

    def test_bootstrap_prefers_stable_public_dns_when_enabled(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")
        workflow_text = (REPO_ROOT / ".github/workflows/app-cd.yml").read_text(encoding="utf-8")
        staging_template = (REPO_ROOT / "deploy/argocd/staging-application.yaml.tpl").read_text(encoding="utf-8")
        production_template = (REPO_ROOT / "deploy/argocd/production-application.yaml.tpl").read_text(encoding="utf-8")

        self.assertIn("FACE_DETECTOR_BASE_DOMAIN", workflow_text)
        self.assertIn("FACE_DETECTOR_DNS_PROVIDER", workflow_text)
        self.assertIn("FACE_DETECTOR_PUBLIC_DNS_ENABLED", workflow_text)
        self.assertIn("FACE_DETECTOR_PUBLIC_TLS_ENABLED", workflow_text)
        self.assertIn("CLOUDFLARE_ZONE_ID", workflow_text)
        self.assertIn("PUBLIC_ENDPOINT_PARAMETER", staging_template)
        self.assertIn("PUBLIC_ENDPOINT_PARAMETER", production_template)

        resolve_script = extract_run_step(workflow, "bootstrap", "Resolve public endpoint Helm parameters")
        self.assertIn('hostname = base_domain', resolve_script)
        self.assertIn('hostname = f"staging.{base_domain}"', resolve_script)
        self.assertIn('label = f"sandbox-pr-{pr_number}"', resolve_script)
        self.assertIn("publicDns.enabled", resolve_script)
        self.assertIn("publicTls.certificateArn", resolve_script)

        endpoint_script = extract_run_step(workflow, "bootstrap", "Resolve public app endpoint")
        self.assertIn("STABLE_BASE_URL", endpoint_script)
        self.assertIn("LOAD_BALANCER_HOSTNAME", endpoint_script)
        self.assertIn('source="stable-dns"', endpoint_script)
        self.assertIn('source="load-balancer"', endpoint_script)

        smoke_step = extract_step(workflow, "bootstrap", "Run post-deploy smoke test")
        self.assertEqual(smoke_step["env"]["FACE_DETECTOR_BASE_URL"], "${{ steps.public-endpoint.outputs.base_url }}")

    def test_argocd_uses_dedicated_project_and_fine_grained_repo_credentials(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")
        workflow_text = (REPO_ROOT / ".github/workflows/app-cd.yml").read_text(encoding="utf-8")
        project_template = (REPO_ROOT / "deploy/argocd/face-detector-project.yaml.tpl").read_text(encoding="utf-8")
        staging_template = (REPO_ROOT / "deploy/argocd/staging-application.yaml.tpl").read_text(encoding="utf-8")
        production_template = (REPO_ROOT / "deploy/argocd/production-application.yaml.tpl").read_text(encoding="utf-8")

        self.assertIn("kind: AppProject", project_template)
        self.assertIn("name: face-detector", project_template)
        self.assertIn('sourceRepos:\n    - "${ARGOCD_REPO_URL}"', project_template)
        self.assertIn("namespace: ${APP_NAMESPACE}", project_template)
        self.assertIn("clusterResourceWhitelist: []", project_template)
        self.assertIn("namespaceResourceWhitelist", project_template)
        self.assertIn("kind: Deployment", project_template)
        self.assertIn("kind: Service", project_template)
        self.assertIn("kind: Job", project_template)
        self.assertIn("kind: HorizontalPodAutoscaler", project_template)
        self.assertIn("kind: ScaledObject", project_template)
        self.assertIn("kind: ServiceMonitor", project_template)
        self.assertIn("kind: PrometheusRule", project_template)
        self.assertIn("kind: AlertmanagerConfig", project_template)
        self.assertIn("namespaceResourceBlacklist", project_template)
        self.assertIn("kind: Secret", project_template)

        self.assertIn("project: face-detector", staging_template)
        self.assertIn("project: face-detector", production_template)
        self.assertNotIn("project: default", staging_template)
        self.assertNotIn("project: default", production_template)
        self.assertIn('repoURL: "${ARGOCD_REPO_URL}"', staging_template)
        self.assertIn('repoURL: "${ARGOCD_REPO_URL}"', production_template)

        credential_step = extract_step(workflow, "bootstrap", "Configure ArgoCD repository credentials")
        self.assertEqual(credential_step["id"], "argocd-repo")
        credential_script = credential_step["run"]
        self.assertIn("ARGOCD_REPO_DEPLOY_KEY", workflow_text)
        self.assertIn("ARGOCD_GITHUB_APP_PRIVATE_KEY", workflow_text)
        self.assertIn("ARGOCD_GITHUB_APP_INSTALLATION_ID", workflow_text)
        self.assertIn("CREDENTIAL_MODE=\"deploy-key\"", credential_script)
        self.assertIn("CREDENTIAL_MODE=\"github-app\"", credential_script)
        self.assertIn("CREDENTIAL_MODE=\"legacy-token\"", credential_script)
        self.assertLess(
            credential_script.index("CREDENTIAL_MODE=\"github-app\""),
            credential_script.index("CREDENTIAL_MODE=\"deploy-key\""),
        )
        self.assertIn("sshPrivateKey", credential_script)
        self.assertIn("githubAppPrivateKey", credential_script)
        self.assertIn("githubAppInstallationID", credential_script)
        self.assertIn("ARGOCD_REPO_TOKEN", credential_script)
        self.assertIn("repo_url=${REPO_URL}", credential_script)

        project_step = extract_step(workflow, "bootstrap", "Apply ArgoCD project")
        self.assertEqual(project_step["env"]["ARGOCD_REPO_URL"], "${{ steps.argocd-repo.outputs.repo_url }}")
        self.assertIn("face-detector-project.yaml.tpl", project_step["run"])

        application_step = extract_step(workflow, "bootstrap", "Apply ArgoCD application")
        self.assertEqual(application_step["env"]["ARGOCD_REPO_URL"], "${{ steps.argocd-repo.outputs.repo_url }}")

    def test_argocd_control_plane_is_internal_rbac_logged_and_notifies(self) -> None:
        eks_main = (REPO_ROOT / "terraform/eks/main.tf").read_text(encoding="utf-8")
        eks_variables = (REPO_ROOT / "terraform/eks/variables.tf").read_text(encoding="utf-8")

        self.assertIn('type = "ClusterIP"', eks_main)
        self.assertIn('"server.insecure" = false', eks_main)
        self.assertIn('"server.disable.auth"', eks_main)
        self.assertIn('"exec.enabled"', eks_main)
        self.assertIn('"server.rbac.log.enforce.enable" = true', eks_main)
        self.assertIn('format = "json"', eks_main)
        self.assertIn('"policy.default" = "role:face-detector-readonly"', eks_main)
        self.assertIn("role:face-detector-admin", eks_main)
        self.assertIn("argocd_oidc_config", eks_main)
        self.assertIn('"oidc.config" = var.argocd_oidc_config', eks_main)
        self.assertIn("notifications = {", eks_main)
        self.assertIn("enabled       = true", eks_main)
        self.assertIn("argocd_notifications_recipients", eks_main)
        self.assertIn("trigger.on-sync-failed", eks_main)
        self.assertIn("trigger.on-health-degraded", eks_main)
        self.assertIn("serviceMonitor = {", eks_main)

        self.assertIn('variable "argocd_oidc_config"', eks_variables)
        self.assertIn('variable "argocd_admin_rbac_subjects"', eks_variables)
        self.assertIn('variable "argocd_notifications_recipients"', eks_variables)

        for workflow_path in (
            ".github/workflows/infrastructure.yml",
            ".github/workflows/terraform-plan-reusable.yml",
        ):
            with self.subTest(workflow=workflow_path):
                workflow_text = (REPO_ROOT / workflow_path).read_text(encoding="utf-8")
                self.assertIn("TF_VAR_argocd_oidc_config", workflow_text)
                self.assertIn("TF_VAR_argocd_admin_rbac_subjects", workflow_text)
                self.assertIn("TF_VAR_argocd_notifications_recipients", workflow_text)

    def test_production_argocd_sync_is_manual_with_sync_window(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/app-cd.yml")
        project_template = (REPO_ROOT / "deploy/argocd/face-detector-project.yaml.tpl").read_text(encoding="utf-8")
        staging_template = (REPO_ROOT / "deploy/argocd/staging-application.yaml.tpl").read_text(encoding="utf-8")
        production_template = (REPO_ROOT / "deploy/argocd/production-application.yaml.tpl").read_text(encoding="utf-8")

        self.assertIn("automated:", staging_template)
        self.assertIn("prune: true", staging_template)
        self.assertIn("selfHeal: true", staging_template)
        self.assertNotIn("automated:", production_template)
        self.assertNotIn("prune: true", production_template)
        self.assertNotIn("selfHeal: true", production_template)

        self.assertIn("syncWindows:", project_template)
        self.assertIn("face-detector-production", project_template)
        self.assertIn("manualSync: true", project_template)

        manual_step = extract_step(workflow, "bootstrap", "Show production manual sync gate")
        self.assertIn("deployment_environment == 'production'", manual_step["if"])

        wait_sync = extract_step(workflow, "bootstrap", "Wait for ArgoCD sync to requested revision")
        self.assertIn("deployment_environment != 'production'", wait_sync["if"])
        rollout = extract_step(workflow, "bootstrap", "Wait for application rollout")
        self.assertIn("deployment_environment != 'production'", rollout["if"])
        smoke = extract_step(workflow, "bootstrap", "Run post-deploy smoke test")
        self.assertIn("deployment_environment != 'production'", smoke["if"])

    def test_sandbox_auto_apply_allows_package_publish_for_bootstrap(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-auto-apply.yml")
        permissions = workflow["jobs"]["bootstrap-sandbox"]["permissions"]
        self.assertEqual(permissions["packages"], "write")

    def test_sandbox_auto_apply_label_jobs_can_write_pull_request_labels(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-auto-apply.yml")

        for job_name in ("signal-apply-ready", "mark-sandbox-validated"):
            with self.subTest(job_name=job_name):
                permissions = workflow["jobs"][job_name]["permissions"]
                self.assertEqual(permissions["issues"], "write")
                self.assertEqual(permissions["pull-requests"], "write")


class SandboxPolicyContractTest(unittest.TestCase):
    def test_policy_refreshes_after_sandbox_auto_apply_completes(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-policy.yml")

        self.assertIn("workflow_run", workflow["on"])
        self.assertIn("Sandbox Auto Apply", workflow["on"]["workflow_run"]["workflows"])
        self.assertIn("completed", workflow["on"]["workflow_run"]["types"])
        self.assertIn("workflow_run.conclusion == 'success'", workflow["jobs"]["evaluate"]["if"])

        context_script = extract_step(workflow, "evaluate", "Resolve PR context")["with"]["script"]
        self.assertIn("listPullRequestsAssociatedWithCommit", context_script)
        self.assertIn("core.setOutput('head_sha'", context_script)

        materialize_script = extract_step(workflow, "evaluate", "Materialize sandbox policy event")["with"][
            "script"
        ]
        self.assertIn(".sandbox-policy-event.json", materialize_script)

        evaluate_step = extract_step(workflow, "evaluate", "Evaluate sandbox blast radius policy")
        self.assertIn("--event-path .sandbox-policy-event.json", evaluate_step["run"])

    def test_trusted_label_resolution_reads_live_pr_labels(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-policy.yml")

        script = extract_step(workflow, "evaluate", "Resolve trusted governance labels")["with"]["script"]
        self.assertIn("github.rest.pulls.get", script)
        self.assertIn("Unable to resolve live PR labels", script)
        self.assertIn("const presentLabels = new Set((pr.labels || []).map(l => l.name));", script)


class SandboxDestroyContractTest(unittest.TestCase):
    def test_destroy_gate_reads_live_labels_and_logs_decision(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-auto-destroy.yml")

        self.assertIn("labeled", workflow["on"]["pull_request_target"]["types"])
        script = extract_step(workflow, "evaluate-destroy", "Evaluate sandbox destroy policy")["with"]["script"]
        self.assertIn("github.rest.pulls.get", script)
        self.assertIn("Unable to resolve live PR labels", script)
        self.assertIn("const trustedActor = context.actor === context.payload.repository.owner.login;", script)
        self.assertIn("const removedLastDeployLabel", script)
        self.assertIn("const explicitTeardownRequested", script)
        self.assertIn("teardown-sandbox", script)
        self.assertIn("Sandbox destroy decision: should_destroy=", script)

        destroy_job = workflow["jobs"]["destroy-sandbox"]
        self.assertEqual(destroy_job["permissions"]["actions"], "write")
        dispatch_script = extract_step(workflow, "destroy-sandbox", "Dispatch sandbox destroy workflow")["with"][
            "script"
        ]
        self.assertIn("github.rest.actions.createWorkflowDispatch", dispatch_script)
        self.assertIn("workflow_id: 'infrastructure.yml'", dispatch_script)
        self.assertIn("action: 'destroy'", dispatch_script)


class SandboxJanitorContractTest(unittest.TestCase):
    def test_janitor_uses_default_branch_destroy_dispatch_for_stale_sandboxes(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/sandbox-janitor.yml")

        select_job = workflow["jobs"]["select-candidates"]
        self.assertEqual(select_job["permissions"]["issues"], "read")
        self.assertEqual(select_job["permissions"]["pull-requests"], "read")

        select_script = extract_step(workflow, "select-candidates", "Select expired sandbox environments")["with"][
            "script"
        ]
        self.assertIn("state: 'all'", select_script)
        self.assertIn("github.rest.issues.listComments", select_script)
        self.assertIn("github.rest.issues.listEvents", select_script)
        self.assertIn("teardown-sandbox", select_script)
        self.assertIn("teardownLabelTrusted", select_script)
        self.assertIn("context.payload.repository.owner.login", select_script)
        self.assertIn("Ignoring untrusted teardown-sandbox label", select_script)
        self.assertIn("closed_pr_with_active_sandbox", select_script)
        self.assertIn("explicit_teardown_label", select_script)
        self.assertIn("draft_pr_with_active_sandbox", select_script)
        self.assertIn("ttl_expired_", select_script)
        self.assertNotIn("reason = 'nightly_cleanup'", select_script)
        self.assertIn("no trusted teardown signal exists", select_script)

        destroy_job = workflow["jobs"]["destroy-candidates"]
        self.assertEqual(destroy_job["permissions"], {"actions": "write", "contents": "read"})

        dispatch_script = extract_step(workflow, "destroy-candidates", "Dispatch sandbox destroy workflow")["with"][
            "script"
        ]
        self.assertIn("github.rest.actions.createWorkflowDispatch", dispatch_script)
        self.assertIn("workflow_id: 'infrastructure.yml'", dispatch_script)
        self.assertIn("ref: context.payload.repository.default_branch", dispatch_script)
        self.assertIn("action: 'destroy'", dispatch_script)


class GitHubOidcTrustContractTest(unittest.TestCase):
    def test_sandbox_trust_policy_allows_only_default_branch_destroy_workflow(self) -> None:
        policy = json.loads((REPO_ROOT / "aws/github-oidc-trust-policy-sandbox.json").read_text(encoding="utf-8"))
        subjects = policy["Statement"][0]["Condition"]["StringLike"]["token.actions.githubusercontent.com:sub"]

        self.assertIn(
            "repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:refs/heads/master:"
            "job_workflow_ref:${GITHUB_OWNER}/${GITHUB_REPO}/.github/workflows/infrastructure.yml@refs/heads/master",
            subjects,
        )
        self.assertNotIn(
            "repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:refs/heads/*:"
            "job_workflow_ref:${GITHUB_OWNER}/${GITHUB_REPO}/.github/workflows/infrastructure.yml@refs/heads/master",
            subjects,
        )

    def test_bootstrap_can_adopt_sandbox_oidc_role_trust_policy(self) -> None:
        main_tf = (REPO_ROOT / "terraform/bootstrap/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/bootstrap/variables.tf").read_text(encoding="utf-8")

        self.assertIn('resource "aws_iam_role" "github_oidc_sandbox"', main_tf)
        self.assertIn("manage_github_oidc_sandbox_role", main_tf)
        self.assertIn("sts:AssumeRoleWithWebIdentity", main_tf)
        self.assertIn(
            "ref:refs/heads/${var.github_oidc_default_branch}:job_workflow_ref",
            main_tf,
        )
        self.assertIn('variable "manage_github_oidc_sandbox_role"', variables_tf)
        self.assertIn("default     = false", variables_tf)

    def test_bootstrap_can_manage_task_scoped_sandbox_oidc_roles(self) -> None:
        main_tf = (REPO_ROOT / "terraform/bootstrap/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/bootstrap/variables.tf").read_text(encoding="utf-8")

        self.assertIn('resource "aws_iam_role" "github_oidc_sandbox_split"', main_tf)
        self.assertIn('resource "aws_iam_policy" "github_oidc_sandbox_split"', main_tf)
        self.assertIn('resource "aws_iam_role_policy_attachment" "github_oidc_sandbox_split"', main_tf)
        self.assertIn("github_oidc_sandbox_split_policy_documents", main_tf)
        self.assertIn("DenyPlatformRoleMutation", main_tf)
        self.assertIn("DenyStateBucketControlPlaneMutation", main_tf)
        self.assertIn("SandboxOIDCExecutionRoleRead", main_tf)
        self.assertIn("SandboxServiceLinkedRoleRead", main_tf)
        self.assertIn("sandbox_split_role_arns", main_tf)
        self.assertIn('"iam:GetRole"', main_tf)
        self.assertIn("role/aws-service-role/*", main_tf)
        self.assertIn('"s3:GetAccelerateConfiguration"', main_tf)
        self.assertIn('"dynamodb:PutItem"', main_tf)
        self.assertIn("github_oidc_sandbox_split_default_subjects", main_tf)
        self.assertIn("terraform-plan-reusable.yml", main_tf)
        self.assertIn("infrastructure.yml", main_tf)
        self.assertIn("app-cd.yml", main_tf)
        self.assertIn('variable "manage_github_oidc_sandbox_split_roles"', variables_tf)
        self.assertIn('variable "attach_github_oidc_sandbox_split_policies"', variables_tf)
        self.assertIn('"Role-Sandbox-Plan"', variables_tf)
        self.assertIn('"Role-Sandbox-Apply"', variables_tf)
        self.assertIn('"Role-Sandbox-Destroy"', variables_tf)
        self.assertIn('"Role-Sandbox-AppDeploy"', variables_tf)

    def test_bootstrap_workflow_uses_owner_approval_and_bootstrap_role_only(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/terraform-bootstrap-apply.yml")
        workflow_text = (REPO_ROOT / ".github/workflows/terraform-bootstrap-apply.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read", "id-token": "write"})

        bootstrap = workflow["jobs"]["bootstrap"]
        self.assertEqual(bootstrap["if"], "github.actor == github.repository_owner")
        self.assertEqual(bootstrap["environment"], "bootstrap")

        self.assertIn("AWS_ROLE_BOOTSTRAP_ARN", workflow_text)
        self.assertNotIn("AWS_ROLE_SANDBOX_ARN", workflow_text)
        self.assertIn("confirm_apply", workflow_text)
        self.assertIn("apply-bootstrap", workflow_text)
        self.assertIn("terraform/bootstrap", workflow_text)
        self.assertIn("github.event.repository.default_branch", workflow_text)
        self.assertIn("terraform apply -auto-approve tfplan", workflow_text)

    def test_bootstrap_terraform_manages_approved_bootstrap_role(self) -> None:
        main_tf = (REPO_ROOT / "terraform/bootstrap/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/bootstrap/variables.tf").read_text(encoding="utf-8")
        outputs_tf = (REPO_ROOT / "terraform/bootstrap/outputs.tf").read_text(encoding="utf-8")

        self.assertIn('backend "s3"', main_tf)
        self.assertIn('key = "bootstrap/terraform.tfstate"', main_tf)
        self.assertIn('resource "aws_iam_role" "github_oidc_bootstrap"', main_tf)
        self.assertIn('resource "aws_iam_policy" "github_oidc_bootstrap"', main_tf)
        self.assertIn('resource "aws_iam_role_policy_attachment" "github_oidc_bootstrap"', main_tf)
        self.assertIn("terraform-bootstrap-apply.yml", main_tf)
        self.assertIn("environment:bootstrap:job_workflow_ref", main_tf)
        self.assertIn("BootstrapTerraformStateBackend", main_tf)
        self.assertIn('"s3:GetBucketCORS"', main_tf)
        self.assertIn('"s3:GetBucketObjectLockConfiguration"', main_tf)
        self.assertIn('"s3:GetBucketOwnershipControls"', main_tf)
        self.assertIn('"s3:GetBucketPolicy"', main_tf)
        self.assertIn('"dynamodb:ListTagsOfResource"', main_tf)
        self.assertIn("BootstrapManagedIAM", main_tf)
        self.assertIn("DenyNonBootstrapEnvironmentRoleMutation", main_tf)
        self.assertIn('"Role-Bootstrap"', variables_tf)
        self.assertIn('variable "manage_github_oidc_bootstrap_role"', variables_tf)
        self.assertIn('variable "attach_github_oidc_bootstrap_policy"', variables_tf)
        self.assertIn("github_oidc_bootstrap_role_arn", outputs_tf)

    def test_bootstrap_can_manage_public_dns_zone_and_certificate(self) -> None:
        main_tf = (REPO_ROOT / "terraform/bootstrap/main.tf").read_text(encoding="utf-8")
        dns_tf = (REPO_ROOT / "terraform/bootstrap/public_dns.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/bootstrap/variables.tf").read_text(encoding="utf-8")
        outputs_tf = (REPO_ROOT / "terraform/bootstrap/outputs.tf").read_text(encoding="utf-8")
        workflow_text = (REPO_ROOT / ".github/workflows/terraform-bootstrap-apply.yml").read_text(encoding="utf-8")

        self.assertIn('variable "manage_public_dns_zone"', variables_tf)
        self.assertIn('variable "public_dns_base_domain"', variables_tf)
        self.assertIn('variable "validate_public_dns_certificate"', variables_tf)
        self.assertIn('resource "aws_route53_zone" "public"', dns_tf)
        self.assertIn('resource "aws_acm_certificate" "public"', dns_tf)
        self.assertIn('resource "aws_route53_hosted_zone_dnssec" "public"', dns_tf)
        self.assertIn('resource "aws_route53_query_log" "public"', dns_tf)
        self.assertIn('resource "aws_cloudwatch_log_group" "route53_query_logs"', dns_tf)
        self.assertIn("#checkov:skip=CKV_AWS_356:KMS key policies require Resource", dns_tf)
        self.assertIn('resource "aws_route53_record" "public_certificate_validation"', dns_tf)
        self.assertIn('resource "aws_acm_certificate_validation" "public"', dns_tf)
        self.assertIn("BootstrapPublicDns", main_tf)
        self.assertIn('"route53:CreateHostedZone"', main_tf)
        self.assertIn('"route53:EnableHostedZoneDNSSEC"', main_tf)
        self.assertIn('"route53:CreateQueryLoggingConfig"', main_tf)
        self.assertIn('"acm:RequestCertificate"', main_tf)
        self.assertIn("public_dns_hosted_zone_id", outputs_tf)
        self.assertIn("public_dns_name_servers", outputs_tf)
        self.assertIn("public_tls_certificate_arn", outputs_tf)
        self.assertIn("public_dns_dnssec_ds_record", outputs_tf)
        self.assertIn("public_dns_query_log_group_name", outputs_tf)
        self.assertIn("FACE_DETECTOR_BASE_DOMAIN", workflow_text)
        self.assertIn("TF_VAR_manage_public_dns_zone", workflow_text)

    def test_eks_grants_access_to_task_scoped_sandbox_roles(self) -> None:
        main_tf = (REPO_ROOT / "terraform/eks/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/eks/variables.tf").read_text(encoding="utf-8")

        self.assertIn("sandbox_cluster_access_entries", main_tf)
        self.assertIn("access_entries", main_tf)
        self.assertIn("AmazonEKSViewPolicy", main_tf)
        self.assertIn("AmazonEKSClusterAdminPolicy", main_tf)
        self.assertIn('name                 = "${var.cluster_name}-default"', main_tf)
        self.assertIn('iam_role_name        = "${var.cluster_name}-default-node"', main_tf)
        self.assertIn('launch_template_name = "${var.cluster_name}-default"', main_tf)
        self.assertIn('variable "sandbox_plan_role_arn"', variables_tf)
        self.assertIn('variable "sandbox_appdeploy_role_arn"', variables_tf)
        self.assertIn('variable "sandbox_destroy_role_arn"', variables_tf)

    def test_eks_installs_external_dns_for_cloudflare_and_optional_route53(self) -> None:
        main_tf = (REPO_ROOT / "terraform/eks/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/eks/variables.tf").read_text(encoding="utf-8")
        outputs_tf = (REPO_ROOT / "terraform/eks/outputs.tf").read_text(encoding="utf-8")
        infrastructure_workflow = (REPO_ROOT / ".github/workflows/infrastructure.yml").read_text(encoding="utf-8")
        plan_workflow = (REPO_ROOT / ".github/workflows/terraform-plan-reusable.yml").read_text(encoding="utf-8")

        self.assertIn('variable "public_dns_enabled"', variables_tf)
        self.assertIn('variable "public_dns_provider"', variables_tf)
        self.assertIn('variable "public_dns_base_domain"', variables_tf)
        self.assertIn('variable "cloudflare_zone_id"', variables_tf)
        self.assertIn('variable "external_dns_cloudflare_secret_name"', variables_tf)
        self.assertIn('variable "public_tls_enabled"', variables_tf)
        self.assertIn('default     = "cloudflare"', variables_tf)
        self.assertIn('contains(["cloudflare", "route53"]', variables_tf)

        self.assertIn('data "aws_route53_zone" "public"', main_tf)
        self.assertIn('data "aws_acm_certificate" "public"', main_tf)
        self.assertIn('resource "aws_iam_role" "external_dns"', main_tf)
        self.assertIn('resource "aws_iam_policy" "external_dns"', main_tf)
        self.assertIn('resource "helm_release" "external_dns"', main_tf)
        self.assertIn("external-dns.alpha.kubernetes.io/hostname", (REPO_ROOT / "deploy/helm/face-detector/templates/nginx.yaml").read_text(encoding="utf-8"))
        self.assertIn('name = local.public_dns_provider', main_tf)
        self.assertIn("local.public_dns_uses_cloudflare", main_tf)
        self.assertIn("CF_API_TOKEN", main_tf)
        self.assertIn("secretKeyRef", main_tf)
        self.assertIn('key  = "api-token"', main_tf)
        self.assertIn("--zone-id-filter=${local.public_dns_cloudflare_zone_id}", main_tf)
        self.assertIn('wait             = local.public_dns_uses_route53', main_tf)
        self.assertIn("--zone-id-filter=${local.public_dns_route53_zone_id}", main_tf)
        self.assertIn('"arn:aws:route53:::hostedzone/${local.public_dns_route53_zone_id}"', main_tf)
        self.assertIn('"arn:aws:route53:::change/*"', main_tf)
        self.assertIn("route53:ChangeResourceRecordSetsNormalizedRecordNames", main_tf)
        self.assertIn("txtOwnerId", main_tf)
        self.assertIn("public_dns_hosted_zone_id", outputs_tf)
        self.assertIn("public_dns_provider", outputs_tf)
        self.assertIn("public_dns_cloudflare_zone_id", outputs_tf)
        self.assertIn("external_dns_cloudflare_secret_name", outputs_tf)
        self.assertIn("public_tls_certificate_arn", outputs_tf)

        self.assertIn("FACE_DETECTOR_DNS_PROVIDER", infrastructure_workflow)
        self.assertIn("CLOUDFLARE_ZONE_ID", infrastructure_workflow)
        self.assertIn("CLOUDFLARE_API_TOKEN", infrastructure_workflow)
        self.assertIn("Configure Cloudflare ExternalDNS token", infrastructure_workflow)
        self.assertIn("TF_VAR_public_dns_provider", infrastructure_workflow)
        self.assertIn("TF_VAR_cloudflare_zone_id", infrastructure_workflow)
        self.assertIn("TF_VAR_public_dns_provider", plan_workflow)
        self.assertIn("TF_VAR_cloudflare_zone_id", plan_workflow)

    def test_eks_installs_internal_monitoring_stack(self) -> None:
        main_tf = (REPO_ROOT / "terraform/eks/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/eks/variables.tf").read_text(encoding="utf-8")
        outputs_tf = (REPO_ROOT / "terraform/eks/outputs.tf").read_text(encoding="utf-8")
        infrastructure_workflow = (REPO_ROOT / ".github/workflows/infrastructure.yml").read_text(encoding="utf-8")
        logging_docs = (REPO_ROOT / "docs/logging-foundation-enterprise.md").read_text(encoding="utf-8")

        self.assertIn('variable "enable_monitoring"', variables_tf)
        self.assertIn('variable "monitoring_namespace"', variables_tf)
        self.assertIn('variable "kube_prometheus_stack_chart_version"', variables_tf)
        self.assertIn('default     = "85.3.3"', variables_tf)
        self.assertIn('variable "enable_logging"', variables_tf)
        self.assertIn('variable "logging_retention"', variables_tf)
        self.assertIn('variable "logging_namespace_selector_regex"', variables_tf)
        self.assertIn('variable "loki_chart_version"', variables_tf)
        self.assertIn('default     = "7.0.0"', variables_tf)
        self.assertIn('variable "alloy_chart_version"', variables_tf)
        self.assertIn('default     = "1.8.2"', variables_tf)

        self.assertIn('resource "kubernetes_namespace" "monitoring"', main_tf)
        self.assertIn('resource "helm_release" "kube_prometheus_stack"', main_tf)
        self.assertIn('resource "helm_release" "loki"', main_tf)
        self.assertIn('resource "helm_release" "alloy"', main_tf)
        self.assertIn("additionalPrometheusRulesMap", main_tf)
        self.assertNotIn('resource "kubernetes_manifest" "platform_prometheus_rule"', main_tf)
        self.assertIn('chart            = "kube-prometheus-stack"', main_tf)
        self.assertIn('repository       = "https://prometheus-community.github.io/helm-charts"', main_tf)
        self.assertIn('chart            = "loki"', main_tf)
        self.assertIn('chart            = "alloy"', main_tf)
        self.assertIn('repository       = "https://grafana.github.io/helm-charts"', main_tf)
        self.assertIn("alertmanagerConfigSelector", main_tf)
        self.assertIn("alertmanagerConfigNamespaceSelector", main_tf)
        self.assertIn('serviceMonitorSelectorNilUsesHelmValues', main_tf)
        self.assertIn('serviceMonitorNamespaceSelector', main_tf)
        self.assertIn('ruleSelectorNilUsesHelmValues', main_tf)
        self.assertIn('additionalDataSources', main_tf)
        self.assertIn('uid       = "loki"', main_tf)
        self.assertIn('deploymentMode = "SingleBinary"', main_tf)
        self.assertIn('retention_period          = local.logging_retention', main_tf)
        self.assertIn('discovery.kubernetes "pods"', main_tf)
        self.assertIn('field = "spec.nodeName=" + coalesce(sys.env("HOSTNAME"), constants.hostname)', main_tf)
        self.assertIn('loki.source.kubernetes "pod_logs"', main_tf)
        self.assertIn('loki.write "default"', main_tf)
        self.assertIn('regex         = "${local.logging_namespace_selector_regex}"', main_tf)
        self.assertIn('target_label  = "namespace"', main_tf)
        self.assertIn('target_label  = "service"', main_tf)
        self.assertIn('target_label = "env"', main_tf)
        self.assertIn("FaceDetectorArgoCdAppDegraded", main_tf)
        self.assertIn("FaceDetectorArgoCdAppOutOfSync", main_tf)
        self.assertIn("FaceDetectorKubernetesNodeNotReady", main_tf)
        self.assertIn('kubeControllerManager', main_tf)
        self.assertIn('kubeEtcd', main_tf)
        self.assertIn('kubeScheduler', main_tf)
        self.assertIn('type = "ClusterIP"', main_tf)
        self.assertIn("monitoring_enabled", outputs_tf)
        self.assertIn("monitoring_namespace", outputs_tf)
        self.assertIn("logging_enabled", outputs_tf)
        self.assertIn("loki_gateway_url", outputs_tf)
        self.assertIn("helm_release.kube_prometheus_stack[0]|kube-prometheus-stack|monitoring", infrastructure_workflow)
        self.assertIn("Grafana Alloy", logging_docs)
        self.assertIn("Loki", logging_docs)
        self.assertIn("Face Detector Logs", logging_docs)
        self.assertIn("kubectl -n monitoring port-forward svc/loki-gateway 3100:80", logging_docs)

    def test_eks_grants_least_privilege_monitoring_port_forward_access(self) -> None:
        main_tf = (REPO_ROOT / "terraform/eks/main.tf").read_text(encoding="utf-8")
        variables_tf = (REPO_ROOT / "terraform/eks/variables.tf").read_text(encoding="utf-8")
        infrastructure_workflow = (REPO_ROOT / ".github/workflows/infrastructure.yml").read_text(encoding="utf-8")
        plan_workflow = (REPO_ROOT / ".github/workflows/terraform-plan-reusable.yml").read_text(encoding="utf-8")
        monitoring_docs = (REPO_ROOT / "docs/monitoring-observability-enterprise.md").read_text(encoding="utf-8")

        self.assertIn('variable "monitoring_port_forward_principal_arns"', variables_tf)
        self.assertIn("monitoring-port-forwarders", main_tf)
        self.assertIn('resource "kubernetes_role" "monitoring_port_forward"', main_tf)
        self.assertIn('resource "kubernetes_role_binding" "monitoring_port_forward"', main_tf)
        self.assertIn("pods/portforward", main_tf)
        self.assertIn("endpointslices", main_tf)
        self.assertIn("kube-prometheus-stack-grafana", main_tf)
        self.assertIn("kubernetes_groups = [local.monitoring_port_forward_group]", main_tf)
        self.assertIn("MONITORING_PORT_FORWARD_PRINCIPAL_ARNS_JSON", infrastructure_workflow)
        self.assertIn("TF_VAR_monitoring_port_forward_principal_arns", infrastructure_workflow)
        self.assertIn("TF_VAR_monitoring_port_forward_principal_arns", plan_workflow)
        self.assertIn("MONITORING_PORT_FORWARD_PRINCIPAL_ARNS_JSON", monitoring_docs)
        self.assertIn("svc/kube-prometheus-stack-grafana", monitoring_docs)


class WorkflowRoleSplitContractTest(unittest.TestCase):
    def test_sandbox_workflows_load_task_scoped_role_arns_with_legacy_fallback(self) -> None:
        expectations = {
            ".github/workflows/terraform-plan-reusable.yml": [
                "AWS_ROLE_SANDBOX_PLAN_ARN",
                "--role-sandbox-plan-arn",
                "TF_VAR_sandbox_plan_role_arn",
                "TF_VAR_sandbox_appdeploy_role_arn",
                "TF_VAR_sandbox_destroy_role_arn",
            ],
            ".github/workflows/infrastructure.yml": [
                "AWS_ROLE_SANDBOX_APPLY_ARN",
                "AWS_ROLE_SANDBOX_DESTROY_ARN",
                "--role-sandbox-apply-arn",
                "--role-sandbox-destroy-arn",
                "TF_VAR_sandbox_plan_role_arn",
                "TF_VAR_sandbox_appdeploy_role_arn",
                "TF_VAR_sandbox_destroy_role_arn",
            ],
            ".github/workflows/app-cd.yml": [
                "AWS_ROLE_SANDBOX_APPDEPLOY_ARN",
                "--role-sandbox-appdeploy-arn",
            ],
        }

        for relative_path, expected_strings in expectations.items():
            with self.subTest(workflow=relative_path):
                workflow_text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                for expected in expected_strings:
                    self.assertIn(expected, workflow_text)
                self.assertIn("repo_vars.get(\"AWS_ROLE_SANDBOX_ARN\")", workflow_text)

    def test_infrastructure_failure_diagnostics_do_not_mask_pre_cluster_failures(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/infrastructure.yml")

        diagnostics = extract_step(workflow, "infrastructure", "Dump sandbox ArgoCD diagnostics on failure")
        diagnostics_script = diagnostics["run"]
        self.assertIn("aws eks describe-cluster", diagnostics_script)
        self.assertIn("does not exist yet. Skipping ArgoCD diagnostics.", diagnostics_script)
        self.assertIn("Could not update kubeconfig", diagnostics_script)

    def _resolve_context(self, *extra_args: str) -> dict[str, str]:
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts/resolve_workflow_context.py"),
            "--environment",
            "sandbox",
            "--pull-request-number",
            "123",
            "--owner-login",
            "chiendz11",
            "--ref-name",
            "feature/example",
            "--default-branch",
            "master",
            "--repository-id",
            "1210252263",
            "--github-repository",
            "chiendz11/Face_dectector",
            "--github-token",
            "token",
            "--git-sha",
            "a" * 40,
            "--role-sandbox-arn",
            "arn:legacy",
            *extra_args,
        ]

        env = os.environ.copy()
        env.pop("GITHUB_OUTPUT", None)
        result = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)

    def test_resolver_selects_task_scoped_sandbox_role_by_mode_and_action(self) -> None:
        plan = self._resolve_context(
            "--mode",
            "plan",
            "--action",
            "plan",
            "--role-sandbox-plan-arn",
            "arn:plan",
        )
        apply = self._resolve_context(
            "--mode",
            "infrastructure",
            "--action",
            "apply",
            "--role-sandbox-apply-arn",
            "arn:apply",
        )
        destroy = self._resolve_context(
            "--mode",
            "infrastructure",
            "--action",
            "destroy",
            "--role-sandbox-destroy-arn",
            "arn:destroy",
        )
        appdeploy = self._resolve_context(
            "--mode",
            "bootstrap",
            "--action",
            "apply",
            "--role-sandbox-appdeploy-arn",
            "arn:appdeploy",
        )

        self.assertEqual(plan["aws_role_arn"], "arn:plan")
        self.assertEqual(apply["aws_role_arn"], "arn:apply")
        self.assertEqual(destroy["aws_role_arn"], "arn:destroy")
        self.assertEqual(appdeploy["aws_role_arn"], "arn:appdeploy")

    def test_resolver_falls_back_to_legacy_sandbox_role_during_migration(self) -> None:
        outputs = self._resolve_context("--mode", "plan", "--action", "plan")

        self.assertEqual(outputs["aws_role_arn"], "arn:legacy")


class HelmChartContractTest(unittest.TestCase):
    def test_all_private_image_workloads_use_global_image_pull_secrets(self) -> None:
        workloads = [
            "backend-deployment.yaml",
            "frontend-deployment.yaml",
            "migration-job.yaml",
            "nginx.yaml",
            "worker-deployment.yaml",
        ]

        for workload in workloads:
            with self.subTest(workload=workload):
                template = (REPO_ROOT / f"deploy/helm/face-detector/templates/{workload}").read_text(encoding="utf-8")
                self.assertIn("{{- with .Values.imagePullSecrets }}", template)
                self.assertIn("imagePullSecrets:", template)

    def test_nginx_routes_public_health_to_backend(self) -> None:
        template = (REPO_ROOT / "deploy/helm/face-detector/templates/nginx.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("location = /health", template)
        self.assertIn("proxy_pass http://backend_upstream/health;", template)

    def test_nginx_service_supports_external_dns_and_tls_termination(self) -> None:
        template = (REPO_ROOT / "deploy/helm/face-detector/templates/nginx.yaml").read_text(
            encoding="utf-8"
        )
        values = yaml.safe_load((REPO_ROOT / "deploy/helm/face-detector/values.yaml").read_text(encoding="utf-8"))
        infra_ci = (REPO_ROOT / ".github/workflows/reusable-infra-ci.yml").read_text(encoding="utf-8")

        self.assertEqual(values["publicDns"], {"enabled": False, "hostname": ""})
        self.assertEqual(values["publicTls"], {"enabled": False, "certificateArn": ""})
        self.assertIn("external-dns.alpha.kubernetes.io/hostname", template)
        self.assertIn("publicDns.hostname is required", template)
        self.assertIn("service.beta.kubernetes.io/aws-load-balancer-ssl-cert", template)
        self.assertIn("publicTls.certificateArn is required", template)
        self.assertIn("service.beta.kubernetes.io/aws-load-balancer-ssl-ports", template)
        self.assertIn("name: https", template)
        self.assertIn("--set publicDns.enabled=true", infra_ci)
        self.assertIn("--set publicTls.enabled=true", infra_ci)

    def test_backend_chart_exposes_internal_monitoring_resources(self) -> None:
        service_monitor = (REPO_ROOT / "deploy/helm/face-detector/templates/servicemonitor-backend.yaml").read_text(
            encoding="utf-8"
        )
        prometheus_rule = (REPO_ROOT / "deploy/helm/face-detector/templates/prometheusrule-backend.yaml").read_text(
            encoding="utf-8"
        )
        alertmanager_config = (REPO_ROOT / "deploy/helm/face-detector/templates/alertmanagerconfig.yaml").read_text(
            encoding="utf-8"
        )
        dashboard = (REPO_ROOT / "deploy/helm/face-detector/templates/grafana-dashboard-overview.yaml").read_text(
            encoding="utf-8"
        )
        logs_dashboard = (REPO_ROOT / "deploy/helm/face-detector/templates/grafana-dashboard-logs.yaml").read_text(
            encoding="utf-8"
        )
        values = yaml.safe_load((REPO_ROOT / "deploy/helm/face-detector/values.yaml").read_text(encoding="utf-8"))

        self.assertTrue(values["monitoring"]["enabled"])
        self.assertTrue(values["monitoring"]["serviceMonitor"]["enabled"])
        self.assertTrue(values["monitoring"]["prometheusRule"]["enabled"])
        self.assertFalse(values["monitoring"]["alertmanagerConfig"]["enabled"])
        self.assertIn("kind: ServiceMonitor", service_monitor)
        self.assertIn("path: /metrics", service_monitor)
        self.assertIn("namespaceSelector:", service_monitor)
        self.assertIn("kind: PrometheusRule", prometheus_rule)
        self.assertIn("FaceDetectorBackendDown", prometheus_rule)
        self.assertIn("FaceDetectorBackendHighErrorRate", prometheus_rule)
        self.assertIn("FaceDetectorBackendHighLatencyP95", prometheus_rule)
        self.assertIn("FaceDetectorDependencyUnhealthy", prometheus_rule)
        self.assertIn("FaceDetectorDeploymentUnavailable", prometheus_rule)
        self.assertIn("FaceDetectorPodRestartSpike", prometheus_rule)
        self.assertIn("face_detector_http_requests_total", prometheus_rule)
        self.assertIn("face_detector_http_request_duration_seconds_bucket", prometheus_rule)
        self.assertIn("kind: AlertmanagerConfig", alertmanager_config)
        self.assertIn("slackConfigs", alertmanager_config)
        self.assertIn("webhookConfigs", alertmanager_config)
        self.assertIn("kind: ConfigMap", dashboard)
        self.assertIn('grafana_dashboard: "1"', dashboard)
        self.assertIn("Face Detector Overview", dashboard)
        self.assertIn("face_detector_dependency_health_status", dashboard)
        self.assertIn("kind: ConfigMap", logs_dashboard)
        self.assertIn('grafana_dashboard: "1"', logs_dashboard)
        self.assertIn("Face Detector Logs", logs_dashboard)
        self.assertIn('"type": "logs"', logs_dashboard)
        self.assertIn('"uid": "loki"', logs_dashboard)
        self.assertIn('service=\\"backend\\"', logs_dashboard)
        self.assertIn('service=\\"nginx\\"', logs_dashboard)
        self.assertIn("traceback|warning|failed", logs_dashboard)

    def test_local_monitoring_compose_scrapes_backend_metrics(self) -> None:
        compose = load_yaml(REPO_ROOT / "docker-compose.monitoring.yml")
        prometheus = load_yaml(REPO_ROOT / "monitoring/local/prometheus/prometheus.yml")
        local_rules = load_yaml(REPO_ROOT / "monitoring/local/prometheus/rules/face-detector-local.yml")
        datasource = load_yaml(REPO_ROOT / "monitoring/local/grafana/provisioning/datasources/prometheus.yml")
        dashboard_path = REPO_ROOT / "monitoring/local/grafana/dashboards/face-detector-local-overview.json"
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        docs = (REPO_ROOT / "docs/local-monitoring-dev.md").read_text(encoding="utf-8")

        services = compose["services"]
        for service_name in ("prometheus", "grafana", "alertmanager"):
            self.assertIn(service_name, services)
        self.assertIn("${BACKEND_METRICS_PORT:-8000}:8000", services["backend"]["ports"])

        scrape_configs = prometheus["scrape_configs"]
        backend_scrape = next(config for config in scrape_configs if config["job_name"] == "face-detector-backend")
        static_config = backend_scrape["static_configs"][0]
        self.assertEqual(static_config["targets"], ["backend:8000"])
        self.assertEqual(static_config["labels"]["namespace"], "local")
        self.assertEqual(static_config["labels"]["service"], "backend")

        self.assertEqual(prometheus["rule_files"], ["/etc/prometheus/rules/*.yml"])
        alert_names = {rule["alert"] for group in local_rules["groups"] for rule in group["rules"]}
        self.assertIn("LocalFaceDetectorBackendDown", alert_names)
        self.assertIn("LocalFaceDetectorDependencyUnhealthy", alert_names)

        self.assertEqual(datasource["datasources"][0]["uid"], "prometheus")
        self.assertEqual(dashboard["uid"], "face-detector-local-overview")
        dashboard_exprs = [
            target["expr"]
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
            if "expr" in target
        ]
        self.assertTrue(any('namespace="local"' in expr for expr in dashboard_exprs))
        self.assertTrue(any('service="backend"' in expr for expr in dashboard_exprs))

        self.assertIn("docker-compose.monitoring.yml", docs)
        self.assertIn("http://localhost:3000", docs)
        self.assertIn("http://localhost:9090/targets", docs)

    def test_local_logging_compose_ships_docker_logs_to_loki(self) -> None:
        compose = load_yaml(REPO_ROOT / "docker-compose.logging.yml")
        loki = load_yaml(REPO_ROOT / "logging/local/loki/loki.yml")
        alloy = (REPO_ROOT / "logging/local/alloy/config.alloy").read_text(encoding="utf-8")
        datasource = load_yaml(REPO_ROOT / "monitoring/local/grafana/provisioning/datasources/loki.yml")
        dashboard_path = REPO_ROOT / "monitoring/local/grafana/dashboards/face-detector-local-logs.json"
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        docs = (REPO_ROOT / "docs/local-logging-dev.md").read_text(encoding="utf-8")

        services = compose["services"]
        self.assertIn("loki", services)
        self.assertIn("alloy", services)
        self.assertIn("${LOKI_PORT:-3100}:3100", services["loki"]["ports"])
        self.assertIn("${ALLOY_PORT:-12345}:12345", services["alloy"]["ports"])
        self.assertIn("/var/run/docker.sock:/var/run/docker.sock:ro", services["alloy"]["volumes"])

        self.assertFalse(loki["auth_enabled"])
        self.assertEqual(loki["limits_config"]["retention_period"], "168h")

        self.assertIn('discovery.docker "compose"', alloy)
        self.assertIn('loki.source.docker "face_detector_compose"', alloy)
        self.assertIn('loki.write "local"', alloy)
        for label in ("env", "namespace", "app", "service", "container"):
            self.assertRegex(alloy, rf'target_label\s+=\s+"{label}"')
        self.assertIn('url = "http://loki:3100/loki/api/v1/push"', alloy)

        self.assertEqual(datasource["datasources"][0]["uid"], "loki")
        self.assertEqual(datasource["datasources"][0]["url"], "http://loki:3100")
        self.assertEqual(dashboard["uid"], "face-detector-local-logs")
        dashboard_exprs = [
            target["expr"]
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
            if "expr" in target
        ]
        self.assertTrue(any('env="local"' in expr for expr in dashboard_exprs))
        self.assertTrue(any('service="backend"' in expr for expr in dashboard_exprs))
        self.assertTrue(any('service="nginx"' in expr for expr in dashboard_exprs))

        self.assertIn("docker-compose.logging.yml", docs)
        self.assertIn("http://localhost:3100", docs)
        self.assertIn("Face Detector Local Logs", docs)


class ReusableAppReleaseContractTest(unittest.TestCase):
    def test_reusable_app_release_resolve_step_writes_expected_publish_artifacts(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/reusable-app-release.yml")
        self.assertEqual(
            extract_uses_step(workflow, "publish-images", "Sign images and attach SBOM attestations"),
            "./.github/actions/sign-images",
        )

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            (root / ".github").mkdir()
            (root / "scripts").mkdir()
            (root / ".artifacts/sbom").mkdir(parents=True)
            catalog_path = root / ".github/image-catalog.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {"name": "backend", "repository": "face-detector-backend"},
                        {"name": "admin", "repository": "face-detector-admin"},
                    ]
                ),
                encoding="utf-8",
            )
            output_path = root / "github-output.txt"

            write_fake_jq(root / "scripts" / "jq.py")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            write_fake_jq(bin_dir / "jq")
            write_executable(
                bin_dir / "python",
                '''
                #!/usr/bin/env bash
                exec python3 "$@"
                ''',
            )
            write_executable(
                root / "scripts/resolve_registry_digest.py",
                '''
                #!/usr/bin/env python3
                import argparse

                parser = argparse.ArgumentParser()
                parser.add_argument("--repository", required=True)
                parser.add_argument("--reference", required=True)
                parser.add_argument("--username", required=True)
                parser.add_argument("--password", required=True)
                args = parser.parse_args()

                mapping = {
                    "face-detector-backend": "sha256:" + "1" * 64,
                    "face-detector-admin": "sha256:" + "2" * 64,
                }
                print(mapping[args.repository.split("/")[-1]])
                ''',
            )
            run_script = extract_run_step(workflow, "publish-images", "Resolve published image digests")
            run_script = replace_command(
                run_script,
                "jq",
                f"{shell_python_command()} {shlex.quote(to_bash_path(bin_dir / 'jq'))}",
            )
            run_script = replace_command(run_script, "python", shell_python_command())

            result = run_bash(
                run_script,
                cwd=root,
                env={
                    "OWNER": "chiendz11",
                    "IMAGE_TAG": "cb8ddca",
                    "CATALOG": ".github/image-catalog.json",
                    "REGISTRY_USERNAME": "actor",
                    "REGISTRY_PASSWORD": "token",
                    "GITHUB_OUTPUT": to_bash_path(output_path),
                    "GITHUB_REPOSITORY": "chiendz11/Face_dectector",
                    "GITHUB_WORKFLOW": "App Release",
                    "GITHUB_RUN_ID": "123456789",
                    "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_REF": "refs/heads/master",
                    "GITHUB_SHA": "cb8ddca",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            sign_targets = json.loads((root / ".artifacts/sign-targets.json").read_text(encoding="utf-8"))
            published_images = json.loads((root / ".artifacts/published-images.json").read_text(encoding="utf-8"))
            provenance = json.loads((root / ".artifacts/release-provenance.json").read_text(encoding="utf-8"))
            output_line = next(line for line in output_path.read_text(encoding="utf-8").splitlines() if line.startswith("matrix="))
            matrix = json.loads(output_line.split("=", 1)[1])

        self.assertEqual(
            sign_targets,
            [
                {
                    "ref": "ghcr.io/chiendz11/face-detector-backend@sha256:" + "1" * 64,
                    "sbom": ".artifacts/sbom/backend.spdx.json",
                },
                {
                    "ref": "ghcr.io/chiendz11/face-detector-admin@sha256:" + "2" * 64,
                    "sbom": ".artifacts/sbom/admin.spdx.json",
                },
            ],
        )
        self.assertEqual(published_images["commit"], "cb8ddca")
        self.assertEqual(len(published_images["images"]), 2)
        self.assertEqual(provenance["builder"]["repository"], "chiendz11/Face_dectector")
        self.assertEqual(provenance["release"]["image_tag"], "cb8ddca")
        self.assertEqual(len(matrix), 2)
        self.assertEqual(matrix[0]["repository"], "face-detector-backend")
        self.assertEqual(matrix[0]["subject_digest"], "sha256:" + "1" * 64)

    def test_reusable_app_release_attestation_contracts_run_in_pr_safe_mode(self) -> None:
        workflow = load_yaml(REPO_ROOT / ".github/workflows/reusable-app-release.yml")
        attestation_job = workflow["jobs"]["attest-published-images"]

        self.assertEqual(
            attestation_job["if"],
            "needs.publish-images.outputs.matrix != '' && inputs.enable_github_attestations && needs.check-attestation-support.outputs.enabled == 'true'",
        )
        self.assertEqual(
            attestation_job["strategy"]["matrix"]["include"],
            "${{ fromJson(needs.publish-images.outputs.matrix) }}",
        )

        provenance_step = extract_step(
            workflow,
            "attest-published-images",
            "Generate build provenance attestation",
        )
        self.assertEqual(provenance_step["uses"], "actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26")
        self.assertEqual(
            provenance_step["with"]["subject-name"],
            "ghcr.io/${{ steps.image-meta.outputs.owner }}/${{ matrix.repository }}",
        )
        self.assertEqual(provenance_step["with"]["subject-digest"], "${{ matrix.subject_digest }}")
        self.assertTrue(provenance_step["with"]["push-to-registry"])

        sbom_step = extract_step(
            workflow,
            "attest-published-images",
            "Generate SBOM attestation",
        )
        self.assertEqual(sbom_step["uses"], "actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26")
        self.assertEqual(sbom_step["with"]["sbom-path"], "${{ matrix.sbom_path }}")
        self.assertTrue(sbom_step["with"]["push-to-registry"])

        build_verify_script = extract_run_step(
            workflow,
            "attest-published-images",
            "Verify build provenance attestation",
        )
        sbom_verify_script = extract_run_step(
            workflow,
            "attest-published-images",
            "Verify SBOM attestation",
        )

        replacements = {
            "${{ steps.image-meta.outputs.owner }}": "chiendz11",
            "${{ matrix.repository }}": "face-detector-backend",
            "${{ matrix.subject_digest }}": "sha256:" + "1" * 64,
            "${{ github.repository }}": "chiendz11/Face_dectector",
        }

        for source, target in replacements.items():
            build_verify_script = build_verify_script.replace(source, target)
            sbom_verify_script = sbom_verify_script.replace(source, target)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            gh_log = root / "gh-log.jsonl"
            write_executable(
                bin_dir / "gh",
                '''
                #!/usr/bin/env python3
                import json
                import os
                import sys

                with open(os.environ["GH_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(sys.argv[1:]) + "\\n")
                ''',
            )

            verify_script = "\n".join(
                [
                    replace_command(
                        build_verify_script,
                        "gh",
                        f"{shell_python_command()} {shlex.quote(to_bash_path(bin_dir / 'gh'))}",
                    ),
                    replace_command(
                        sbom_verify_script,
                        "gh",
                        f"{shell_python_command()} {shlex.quote(to_bash_path(bin_dir / 'gh'))}",
                    ),
                ]
            )

            result = run_bash(
                verify_script,
                cwd=root,
                env={
                    "GH_LOG": to_bash_path(gh_log),
                    "GH_TOKEN": "token",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            commands = [json.loads(line) for line in gh_log.read_text(encoding="utf-8").splitlines()]

        image_ref = "oci://ghcr.io/chiendz11/face-detector-backend@sha256:" + "1" * 64
        self.assertEqual(
            commands,
            [
                [
                    "attestation",
                    "verify",
                    image_ref,
                    "-R",
                    "chiendz11/Face_dectector",
                ],
                [
                    "attestation",
                    "verify",
                    image_ref,
                    "-R",
                    "chiendz11/Face_dectector",
                    "--predicate-type",
                    "https://spdx.dev/Document/v2.3",
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()
