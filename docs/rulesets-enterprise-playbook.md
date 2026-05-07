# Enterprise Rulesets Migration Playbook

This playbook moves repository enforcement from legacy branch protection to
GitHub Rulesets with separate controls for workflow/policy changes and
application changes.

## Scope

- Target branch refs: `master`, `main`, `production`
- Required universal check: `CI Gateway / gateway`
- CODEOWNERS-controlled control plane: `.github/workflows/**`, `policies/**`

## Phase 1: Rulesets (The Shield)

Create two branch rulesets and keep bypass limited to emergency break-glass
identities only.

### 1) High Security Ruleset (Workflow + Policies)

Recommended settings:

- Target refs: `refs/heads/master`, `refs/heads/main`, `refs/heads/production`
- File conditions: `.github/workflows/**`, `.github/actions/**`, `policies/**`, `.github/CODEOWNERS`
- Require pull request before merging: enabled
- Required approvals: 1
- Require code owner review: enabled
- Dismiss stale reviews: enabled
- Require approval of the most recent reviewable push: enabled
- Require conversation resolution: enabled
- Restrict deletions: enabled
- Required status checks: `CI Gateway / gateway`
- Bypass list: emergency identities only

### 2) Development Flow Ruleset (App Code)

Recommended settings:

- Target refs: `refs/heads/master`, `refs/heads/main`, `refs/heads/production`
- File conditions: application/runtime paths (`backend/**`, `frontend-admin/**`, `edge-client/**`, etc.)
- Require pull request before merging: enabled
- Required approvals: 1
- Dismiss stale reviews: enabled
- Require conversation resolution: enabled
- Required status checks: `CI Gateway / gateway`

## Phase 2: CI Gateway (The Gatekeeper)

Use a universal workflow that always runs on pull requests and decides which
verification lanes to execute based on changed paths.

Implemented file:

- `.github/workflows/ci-gateway.yml`

Behavior:

- If app paths changed: run reusable app verification lane.
- If platform/workflow/policy paths changed: run reusable platform governance lane.
- Always emit final gate result as `CI Gateway / gateway`.

This prevents blocked PRs caused by required checks that never run.

## Phase 3: Segregation of Duties

Current repository is single-maintainer. To satisfy audit-grade SoD, migrate
owners to team identities:

- `* @org/developers`
- `.github/workflows/ @org/devops-leads`
- `policies/ @org/security-team`
- `docs/ @org/technical-writers`

At least two trusted humans should be able to review workflow/policy changes.

## Operational Checklist

1. Enable Secret Scanning and Push Protection in repository settings.
2. Create the two Rulesets and move required checks from branch protection to rulesets.
3. Set `CI Gateway / gateway` as required status check in both rulesets.
4. Keep emergency bypass identities minimal and documented.
5. Validate with three test PRs:
   - docs-only PR
   - app-code PR
   - workflow/policy PR
