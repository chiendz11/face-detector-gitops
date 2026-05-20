# Sandbox Decision Matrix

This document tells reviewers when to use the expensive PR sandbox lane and when to keep a PR in the normal fast lane.

## Default Rule

- Sandbox is reviewer-controlled, not automatic for every PR.
- `deploy-sandbox` is the preferred label. `deploy-preview` remains an accepted compatibility alias for the same reviewer intent.
- Use the fast lane by default. Escalate to sandbox only when the blast radius justifies running the full PR environment.
- Standard sandbox auto-apply only works for same-repository, non-draft PRs and now also waits for the relevant PR verification lanes to be green.
- The `Sandbox Policy` PR check separates recommendation from enforcement:
  - heavy non-critical changes get `sandbox-recommended` and do not block merge by themselves.
  - critical changes get `sandbox-required` and block merge until sandbox validation or an explicit owner waiver.
- `deploy-sandbox` and `deploy-preview` are deployment intent labels only. They allow auto-apply; they are not waiver labels.

## Heavy Lane: Usually Recommended

Use `deploy-sandbox` when the PR has meaningful blast radius and the exact integrated environment is part of the review.

- Cross-service or integration behavior changes that need the real ingress, image, or service-to-service path.
- Release contract changes such as service Dockerfiles or compose overrides when they do not touch the trusted control plane.
- Any PR where reviewer confidence depends on seeing the combined system, not just unit, integration, or static checks.

For these changes the bot may add `sandbox-recommended`. This is advisory; owner/DevOps can still merge after required CI if they decide a sandbox is not worth the cost.

## Critical Lane: Required Validation Or Waiver

Critical changes must either be validated in sandbox or explicitly waived by the repository owner.

- Stateful schema changes such as database migrations.
- Workflow, policy, Terraform, IAM, networking, authentication, and other trust-boundary changes.
- Runtime hardening, deployment contract, or reverse-proxy changes where production-like behavior matters.

Valid outcomes:

- owner adds `deploy-sandbox` or `deploy-preview`, auto-apply runs, and the system refreshes `sandbox-validated`.
- owner adds `skip-sandbox-approved` as an explicit risk waiver.

`allow-self-approve` does not satisfy this gate.

## Fast Lane: Do Not Apply A Sandbox Label By Default

Keep the PR in the normal CI path when the change is local and the blast radius is small.

- Pure logic changes contained to one service or module.
- UI or UX changes that do not alter backend, ingress, or runtime contracts.
- Tests, documentation, or internal refactors with no externally visible behavior shift.
- Non-core dependency updates with small scope and green CI evidence.

## Reviewer Checklist

- Confirm the PR actually needs integrated runtime validation before spending sandbox capacity.
- If `Sandbox Policy` fails with `sandbox-required`, either deploy and wait for `sandbox-validated`, add `skip-sandbox-approved`, or split the change so critical files are isolated.
- Check that `App CI`, `Repo Security`, `Infra CI`, `Platform CI`, and `Terraform PR Plan` are green before expecting the sandbox to auto-apply.
- Respect the one-sandbox-per-owner quota. If a sandbox is already active for the same owner, close or destroy the older one first.
- Remove the deploy label when the sandbox is no longer needed.
- Use the protected manual DevOps lanes for `devops/*` workflow, IAM, or trust-boundary experiments instead of the normal reviewer label path.

## Lifecycle And Governance

- Auto-destroy is mandatory. PR sandboxes are torn down on PR close, convert-to-draft, or final deploy-label removal.
- `sandbox-active` is operational state, not reviewer intent. Reviewers should apply `deploy-sandbox` or `deploy-preview`, not `sandbox-active`.
- `sandbox-validated` is system state for the current PR head. It is refreshed by GitHub Actions after sandbox apply and bootstrap/smoke validation pass.
- `skip-sandbox-approved` is an owner waiver. It should be rare and must remain visible in PR labels and artifacts.
- Sandboxes are ephemeral review environments, not long-lived shared test stacks.
- Janitor cleanup still applies, so stale environments should not be treated as durable infrastructure.

## Escalation Rule

If a change touches both the normal application surface and the trusted control plane, bias toward the heavier lane and get the sandbox plus the relevant protected approvals.
