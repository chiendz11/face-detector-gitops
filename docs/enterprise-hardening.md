# Enterprise Hardening Summary

This document records the main changes made to move this repository from a
basic CI/CD setup toward an enterprise-oriented delivery platform.

It focuses on:

- trust boundaries between workflows
- GitHub Actions permission hardening
- policy-as-code adoption
- infrastructure and supply-chain security controls
- release provenance and artifact signing

## Goals

The hardening work was driven by five practical goals:

1. Separate untrusted pull request validation from trusted publish and deploy flows.
2. Reduce implicit trust in GitHub Actions by declaring explicit permissions and approvals.
3. Turn governance rules into executable policy instead of scattered workflow logic.
4. Improve software supply-chain evidence for images and release artifacts.
5. Keep rollout safe by introducing advisory controls before hard gates where needed.

## 1. CI/CD Lanes Were Split By Trust Surface

The repository no longer treats all automation as one mixed pipeline. It is now
split into dedicated lanes with different trust levels and responsibilities.

### Application Verification

- `.github/workflows/app-ci.yml`
- `.github/workflows/reusable-app-ci.yml`

Purpose:

- run pull request safe verification only
- lint and test backend, frontend, and edge client
- run dependency and code security checks
- build images for verification only
- run smoke e2e against the built images

Enterprise value:

- untrusted PR code does not get release-grade publish permissions
- application verification is isolated from trusted deployment concerns

### Application Release

- `.github/workflows/app-release.yml`
- `.github/workflows/reusable-app-release.yml`

Purpose:

- publish images only from the trusted branch flow
- sign release artifacts
- generate release evidence and attestations

Enterprise value:

- image publication is restricted to a trusted lane
- release evidence is now generated from a controlled workflow instead of being implied by logs

### Infrastructure Verification

- `.github/workflows/infra-ci.yml`
- `.github/workflows/reusable-infra-ci.yml`

Purpose:

- validate Terraform and Helm
- run IaC security scanning
- run IaC policy checks

Enterprise value:

- infrastructure changes are reviewed in a dedicated lane
- IaC risk is surfaced before reaching apply workflows

### Platform Governance

- `.github/workflows/platform-ci.yml`
- `.github/workflows/reusable-platform-ci.yml`

Purpose:

- validate workflow governance
- lint workflow syntax
- validate composite action manifests
- enforce policy-as-code for GitHub automation surfaces

Enterprise value:

- the control plane is validated separately from application runtime code
- changes to workflows and actions are treated as security-sensitive changes

## 2. Workflow Permission Hardening Was Standardized

All workflows now declare top-level `permissions` explicitly.

Examples of workflows that were standardized:

- `.github/workflows/infrastructure.yml`
- `.github/workflows/app-cd.yml`
- `.github/workflows/terraform-plan.yml`
- `.github/workflows/terraform-plan-reusable.yml`
- `.github/workflows/sandbox-auto-apply.yml`
- `.github/workflows/sandbox-auto-destroy.yml`
- `.github/workflows/sandbox-devops-verify.yml`
- `.github/workflows/sandbox-workflow-rd.yml`
- `.github/workflows/sandbox-janitor.yml`
- `.github/workflows/gitops-staging.yml`
- `.github/workflows/gitops-production.yml`
- `.github/workflows/reusable-app-release.yml`

What changed:

- workflow-level default permissions were added
- elevated scopes were left only on jobs that actually need them
- `security-events: write` was added only where SARIF upload requires it
- release lanes keep `id-token`, `attestations`, and `packages` only where needed

Enterprise value:

- easier auditability
- less accidental privilege expansion
- stronger least-privilege baseline for all automation

## 3. Workflow Governance Was Upgraded From Script Logic To Policy-As-Code

The repository was already enforcing governance rules in CI, but the rules were
embedded directly inside workflow logic. That meant policy and pipeline were too
tightly coupled.

This has now been moved closer to enterprise-grade Policy as Code.

### New Policy Bundle Layout

- `policies/github/workflows/policy.rego`
- `policies/github/actions/policy.rego`
- `policies/terraform/policy.rego`
- `policies/data/exceptions.yaml`
- `.github/actions/setup-conftest/action.yml`

### What Is Enforced For GitHub Workflows

Current workflow policy checks include:

- top-level `permissions` must exist
- mutable action refs such as `@main`, `@master`, `@head`, and `@latest` are blocked

### What Is Enforced For Composite Actions

Current composite action policy checks include:

- `name` must be present
- `description` must be present
- `runs.using` must be declared
- every composite `run` step must declare `shell`
- mutable action refs are blocked

### Why This Is Better Than Workflow-Embedded Governance

Before:

- governance lived inside one workflow as custom Python logic
- rules were harder to reuse, version, and reason about

Now:

- governance rules live in Rego policies
- CI only calls the policy engine
- exceptions can be declared in a dedicated data file
- policy evolution can move from advisory to hard fail in a controlled way

Enterprise value:

- governance becomes portable and reviewable
- policy can be versioned independently from workflow glue
- exception handling becomes explicit instead of hidden in scripts

## 4. Infrastructure Policy-As-Code Was Added In Advisory Mode

Infrastructure policy checks now run through Conftest in addition to Checkov.

Relevant files:

- `.github/workflows/reusable-infra-ci.yml`
- `policies/terraform/policy.rego`
- `policies/data/exceptions.yaml`

Current advisory policies flag the following patterns:

- EKS public control-plane endpoint enabled
- S3 buckets using `force_destroy = true`
- RDS instances using `skip_final_snapshot = true`
- public ingress on sensitive ports where applicable

Why advisory first:

- the current Terraform still contains patterns that are operationally useful but risky
- surfacing warnings first avoids turning the pipeline red before the team agrees on the target posture
- the exception model is already in place for later tightening

Current local validation result:

- the policies execute successfully
- current Terraform emits advisory warnings rather than failures

Enterprise value:

- infrastructure risk becomes visible early
- future hard gates can be introduced rule by rule without redesigning the lane

## 5. Infrastructure Security Scanning Was Expanded

Infra CI now includes advisory Checkov scanning with artifact and code-scanning output.

Relevant files:

- `.github/workflows/infra-ci.yml`
- `.github/workflows/reusable-infra-ci.yml`

What changed:

- Checkov runs in `--soft-fail` mode
- SARIF output is produced
- SARIF is uploaded as an artifact
- SARIF is also uploaded to GitHub code scanning when allowed by the event context

Enterprise value:

- findings are centralized in code scanning instead of buried in logs
- the organization gets visibility before deciding which findings should block merges

## 6. Platform CI Now Validates Governance Surfaces As First-Class Inputs

Platform CI path filters now include policy files.

Relevant file:

- `.github/workflows/platform-ci.yml`

What changed:

- policy changes trigger platform governance checks
- Conftest setup is shared through a pinned composite action
- governance rules for workflows and composite actions are executed consistently

Enterprise value:

- governance code is treated as a protected control-plane surface
- policy drift is caught by the same lane that owns workflow governance

## 7. CODEOWNERS Was Updated For Trust Segmentation

Relevant file:

- `.github/CODEOWNERS`

New governance ownership was added for:

- `.github/actions/setup-conftest/`
- `policies/github/`
- `policies/terraform/`
- `policies/data/`
- image save/load composite actions

Enterprise value:

- policy and platform changes now have explicit ownership
- review responsibility is aligned with the security surface being changed

## 8. App CI Supply-Chain Verification Was Strengthened

Relevant files:

- `.github/workflows/app-ci.yml`
- `.github/workflows/reusable-app-ci.yml`
- `.github/actions/load-images/action.yml`
- `.github/actions/save-images/action.yml`

What changed:

- App CI now uploads Trivy SARIF to code scanning
- Docker images are built once, saved as archives, then reloaded for smoke e2e
- the e2e job no longer rebuilds a potentially different image

Enterprise value:

- verification becomes more reproducible
- build output used in security scan and smoke e2e is the same artifact
- supply-chain evidence is more trustworthy because the same image bits are reused

## 9. Release Provenance And Artifact Signing Were Tightened

This is one of the biggest enterprise upgrades in the release lane.

Relevant files:

- `.github/workflows/app-release.yml`
- `.github/workflows/reusable-app-release.yml`
- `.github/actions/sign-images/action.yml`

### What Was Already Present Before Tightening

The release lane already had:

- trusted publish-only workflow separation
- Cosign image signing
- SBOM generation
- SBOM attachment to released images

### What Was Added Now

#### Release provenance artifact

`reusable-app-release.yml` now emits:

- `.artifacts/release-provenance.json`

This records:

- repository
- workflow name
- run id and run attempt
- git ref and SHA
- image tag
- published image list and digests

#### GitHub artifact attestations

The trusted release lane generates GitHub-native attestations via `actions/attest@v4` when
the repository supports it. A `check-attestation-support` capability gate (using the GitHub
REST API) detects private user-owned repositories and gracefully skips attestation with a
warning rather than failing the release. This ensures the lane is portable across personal,
organization, and enterprise account types without workflow changes.

The caller workflow grants:

- `attestations: write`
- `id-token: write`
- `packages: write`

Cosign-based signing and SBOM attestation run unconditionally regardless of GitHub
attestation capability.

#### Post-attestation verification

The trusted release lane verifies Cosign signatures and SBOM attestations after signing.
GitHub attestation verification (`gh attestation verify`) applies only when the capability
gate allows it.

#### Post-sign verification

The signing action now verifies:

- Cosign image signature
- Cosign SBOM attestation

using the expected GitHub Actions OIDC issuer and certificate identity pattern.

### Why This Matters

This moves the release lane from:

- "images were pushed and signed"

to:

- "images were pushed by a trusted workflow, signed, attested, and verified with traceable provenance"

Enterprise value:

- stronger supply-chain integrity
- better audit evidence for releases
- easier downstream verification in promotion or deployment systems

## 10. Trusted Sandbox And Admin Lanes Were Further Normalized

Relevant files include:

- `.github/workflows/infrastructure.yml`
- `.github/workflows/sandbox-devops-verify.yml`
- `.github/workflows/sandbox-workflow-rd.yml`
- `.github/workflows/sandbox-auto-apply.yml`
- `.github/workflows/sandbox-auto-destroy.yml`
- `.github/workflows/sandbox-janitor.yml`

What changed across the trusted/manual lanes:

- top-level permissions were standardized
- admin and workflow-R&D lanes continue to require protected environments and approval gates
- trusted child workflows are reused instead of duplicating deployment logic

Enterprise value:

- manual or privileged flows are more uniform
- security review becomes easier because trusted lanes share the same foundations

## 11. Runtime Image Hardening Was Improved

Relevant runtime surfaces:

- `frontend-admin/Dockerfile`
- `nginx/Dockerfile`
- `edge-client/Dockerfile`

What changed:

- base OS packages are upgraded during image build

Enterprise value:

- fewer known OS-level CVEs in application container images
- better Trivy scan results and lower release risk

## 12. App CI Dependency License Governance Was Added

Relevant files:

- `.github/workflows/reusable-app-ci.yml`
- `policies/licenses/policy.json`
- `scripts/check_dependency_licenses.py`

What changed:

- App CI now generates license inventories for backend, edge-client, and frontend-admin dependencies
- a repository-owned policy file now classifies licenses into allow, review, and disallow buckets
- the checker blocks unknown or explicitly disallowed licenses before merge
- the private `frontend-admin` workspace package is ignored explicitly so the gate does not fail on the repo's own unpublished package metadata
- App CI uploads the inventory plus summary report as a build artifact for review evidence

Enterprise value:

- dependency license decisions are explicit instead of ad hoc
- legal or procurement review can focus on a smaller review-only queue
- merge-time enforcement catches license drift before release packaging

## 13. Sandbox Reviewer Decision Rules Were Written Down

Relevant files:

- `docs/sandbox-decision-matrix.md`
- `README.md`
- `.github/workflows/sandbox-auto-apply.yml`

What changed:

- reviewer-facing guidance now defines when a PR belongs in the heavy sandbox lane versus the fast non-sandbox lane
- the guidance documents that `deploy-sandbox` and `deploy-preview` stay reviewer-controlled labels, not an automatic preview for every PR
- the written rules now capture the green-PR-lanes prerequisite, one-sandbox-per-owner quota, and mandatory auto-destroy lifecycle

Enterprise value:

- sandbox usage becomes more predictable and auditable
- expensive PR environments are reserved for changes with real blast radius
- the written policy matches the automation already enforced by the repository

## Current State

The repository is now beyond a simple workflow-based CI/CD setup and is moving
toward an enterprise operating model.

### Implemented

- lane split by trust boundary
- top-level workflow permission hardening
- platform governance hard gates for workflows and composite actions
- policy-as-code structure with Conftest and Rego
- infra advisory PaC and advisory Checkov scanning
- code-scanning integration for Trivy and Checkov
- reproducible build-once image verification in App CI
- release provenance artifact generation
- GitHub build provenance and SBOM attestations in the trusted release lane
- Cosign sign plus verification of signatures and attestations
- GitHub attestation capability gate for portable private/org/enterprise support
- SHA-pinned external actions across all workflow and composite action files

### Still Candidate For Future Tightening

- promote selected infra warnings from advisory to hard fail
- add exception expiry dates for temporary risk acceptance
- verify provenance and signatures again at GitOps promotion or deploy time
- add richer policy coverage for Helm, container image metadata, and release rules
- add GHCR image lifecycle cleanup to prune SHA-tagged images and Cosign signature tags

## Recommended Next Steps

1. Convert selected Terraform warnings to hard fails after the team agrees on exceptions.
2. Add expiration dates to policy exceptions in `policies/data/exceptions.yaml`.
3. Verify signed attestations again in promotion or deployment workflows.
4. Extend PaC to Helm chart policies and release metadata rules.

## Files Added Or Introduced As Part Of This Step

- `docs/enterprise-hardening.md`
- `.github/actions/setup-conftest/action.yml`
- `policies/github/workflows/policy.rego`
- `policies/github/actions/policy.rego`
- `policies/terraform/policy.rego`
- `policies/data/exceptions.yaml`

## Summary

The repository now has the foundations of an enterprise-grade delivery system:

- separate trusted and untrusted lanes
- explicit least-privilege permissions
- executable governance policies
- advisory infrastructure risk policies
- stronger supply-chain evidence
- release signing, attestation, and verification

The major shift is architectural, not cosmetic: governance and release trust are
no longer based only on workflow convention. They are increasingly encoded as
machine-verifiable rules and signed release evidence.