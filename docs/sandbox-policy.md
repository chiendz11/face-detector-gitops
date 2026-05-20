# Sandbox Policy

This document defines the custom sandbox governance gate for pull requests.

## Goals

- Keep normal application changes fast.
- Require production-like validation for critical control-plane changes.
- Keep deployment intent, review bypass, and risk waiver as separate decisions.
- Preserve an audit trail through labels, `report.json`, PR comments, and workflow artifacts.

## Lanes

- `fast`: local, low-blast-radius changes. Sandbox policy passes.
- `heavy` + non-critical: the bot may add `sandbox-recommended`. This is advisory and does not block merge by itself.
- `heavy` + critical: the bot adds `sandbox-required`. Merge is blocked until sandbox validation passes or the owner applies an explicit waiver.

Critical paths include workflow/policy/control-plane files, Terraform, deploy manifests, ingress/reverse proxy files, database migrations, IAM/network/auth paths, and sandbox policy evaluator scripts.

## Labels

- `allow-self-approve`: owner-only review governance opt-in. It does not bypass `sandbox-required`.
- `sandbox-recommended`: bot advisory label for heavy non-critical PRs.
- `sandbox-required`: bot hard-gate label for critical PRs.
- `deploy-sandbox` / `deploy-preview`: owner-only deployment intent labels. They let auto-apply run; they are not waiver labels.
- `sandbox-validated`: bot label refreshed after sandbox apply and smoke/bootstrap validation pass for the current PR head.
- `skip-sandbox-approved`: owner-only explicit waiver. Use rarely, keep it visible, and rely on the report/comment artifact for audit.
- `sandbox-active`: operational state for quota/cleanup, not reviewer intent.

Human-trusted labels are valid only when the latest label event actor is `github.repository_owner` and not a bot. System-trusted labels are valid only when added by `github-actions[bot]` for the current PR head.

## Pass Conditions

Sandbox policy passes when one of these is true:

- the PR is fast lane.
- the PR is heavy but non-critical, producing only `sandbox-recommended`.
- the PR is critical and has trusted `sandbox-validated`.
- the PR is critical and has trusted `skip-sandbox-approved`.

Sandbox policy does not pass merely because `deploy-sandbox`, `deploy-preview`, or `allow-self-approve` exists.

## Auto-Apply

Auto-apply is eligible only when:

- the PR is same-repository, non-draft, and not Dependabot.
- a trusted `deploy-sandbox` or `deploy-preview` label exists.
- the PR is not already `sandbox-validated`.
- no trusted `skip-sandbox-approved` waiver exists.
- required CI gates are green.

For critical PRs, auto-apply can run while `Sandbox Policy` is still failing. The policy passes later when the workflow refreshes `sandbox-validated`.

## Report

The evaluator writes `.artifacts/sandbox-policy/report.json` with the governance decision. Important fields include:

- `classification`
- `riskLevel`
- `sandboxRecommended`
- `sandboxRequired`
- `deployLabelTrusted`
- `sandboxValidatedTrusted`
- `skipSandboxTrusted`
- `autoApplyEligible`
- `blockingReasons`
- `matchedOwners`
- `approvers`

`block: true` is the merge-blocking signal for the `Sandbox Policy` check.

## Operations

- Require the `Sandbox Policy` check on `master` if this gate should enforce mergeability.
- Keep `deploy-sandbox` and `skip-sandbox-approved` owner-only.
- Remove deploy labels when sandbox validation is no longer needed.
- Destroying a sandbox must clear stale `sandbox-validated`.
- For solo projects, `github.repository_owner` is the correct trusted human boundary. For multi-team repos, replace it with an allowlist, environment approver, or team-based authorization.
