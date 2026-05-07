# Sandbox Decision Matrix

This document tells reviewers when to use the expensive PR sandbox lane and when to keep a PR in the normal fast lane.

## Default Rule

- Sandbox is reviewer-controlled, not automatic for every PR.
- `deploy-sandbox` is the preferred label. `deploy-preview` remains an accepted compatibility alias for the same reviewer intent.
- Use the fast lane by default. Escalate to sandbox only when the blast radius justifies running the full PR environment.
- Standard sandbox auto-apply only works for same-repository, non-draft PRs and now also waits for the relevant PR verification lanes to be green.
- The `Sandbox Policy` PR check now enforces this guidance for same-repository non-draft PRs: heavy-lane changes fail the check until `deploy-sandbox` or `deploy-preview` is present.
- `devops/*` branches are intentionally excluded from this label gate because they must use the protected manual `Sandbox DevOps Verify` or `Sandbox Workflow R&D` lanes instead.

## Heavy Lane: Apply A Sandbox Label

Use `deploy-sandbox` when the PR has meaningful blast radius and the exact integrated environment is part of the review.

- Cross-service or integration behavior changes that need the real ingress, image, or service-to-service path.
- Stateful changes such as database schema, migrations, queue semantics, retention, or anything difficult to validate with isolated tests.
- Infrastructure, IAM, security, workflow-trust, Helm, Terraform, networking, or secret-management changes.
- Runtime hardening, deployment contract, or reverse-proxy changes where production-like behavior matters.
- Any PR where reviewer confidence depends on seeing the combined system, not just unit, integration, or static checks.

## Fast Lane: Do Not Apply A Sandbox Label By Default

Keep the PR in the normal CI path when the change is local and the blast radius is small.

- Pure logic changes contained to one service or module.
- UI or UX changes that do not alter backend, ingress, or runtime contracts.
- Tests, documentation, or internal refactors with no externally visible behavior shift.
- Non-core dependency updates with small scope and green CI evidence.

## Reviewer Checklist

- Confirm the PR actually needs integrated runtime validation before spending sandbox capacity.
- If `Sandbox Policy` fails, either add `deploy-sandbox` or `deploy-preview`, or explain why the PR should move to a lighter implementation slice.
- Check that `App CI`, `Repo Security`, `Infra CI`, `Platform CI`, and `Terraform PR Plan` are green before expecting the sandbox to auto-apply.
- Respect the one-sandbox-per-owner quota. If a sandbox is already active for the same owner, close or destroy the older one first.
- Remove the deploy label when the sandbox is no longer needed.
- Use the protected manual DevOps lanes for `devops/*` workflow, IAM, or trust-boundary experiments instead of the normal reviewer label path.

## Lifecycle And Governance

- Auto-destroy is mandatory. PR sandboxes are torn down on PR close, convert-to-draft, or final deploy-label removal.
- `sandbox-active` is operational state, not reviewer intent. Reviewers should apply `deploy-sandbox` or `deploy-preview`, not `sandbox-active`.
- Sandboxes are ephemeral review environments, not long-lived shared test stacks.
- Janitor cleanup still applies, so stale environments should not be treated as durable infrastructure.

## Escalation Rule

If a change touches both the normal application surface and the trusted control plane, bias toward the heavier lane and get the sandbox plus the relevant protected approvals.