# Branch Protection For Solo Maintainer

This repository uses CODEOWNERS and custom policy checks as governance metadata.
For a solo-maintainer project, GitHub native review enforcement should stay off
unless another trusted reviewer exists.

## Recommended Merge Gates

Keep these gates required on `master`:

- `CI Gateway / gateway`
- `Sandbox Policy / evaluate`
- `Repo Security / secret-scan`

Keep these repository rules enabled:

- Require status checks to pass before merging.
- Require branches to be up to date before merging.
- Restrict direct pushes to the protected branch.
- Allow auto-merge after required checks pass.

Disable these native review rules for solo maintenance:

- Require pull request reviews before merging.
- Require review from Code Owners.

## CODEOWNERS Role

Use CODEOWNERS as a metadata and audit layer, not as the native GitHub review
enforcement layer.

For solo ownership, prefer exact usernames:

```text
* @your-username
```

Avoid using team ownership for self-approve bypass paths:

```text
* @org/team
```

The custom sandbox-policy parser should continue to ignore team ownership for
self-approval decisions. This keeps the bypass scope narrow and avoids allowing
future team members to approve their own pull requests through team membership.

## Domain-Aware CI Policy

Enterprise-grade CI should avoid one monolithic app check that scans every
application component for every app pull request. A change in `edge-client/**`
should not be blocked by an unrelated backend, frontend, or nginx image scan.

Use domain lanes behind one required gateway:

- `backend/**` runs backend lint, tests, backend dependency checks, and backend image checks.
- `frontend-admin/**` runs frontend tests, build, dependency checks, and frontend image checks.
- `edge-client/**` runs edge-client tests, dependency checks, and edge image checks.
- `nginx/**` runs nginx image checks.
- Shared app files such as compose files, image catalog, and app CI workflows run the broader app lane.

Branch protection should require the stable aggregator check (`CI Gateway /
gateway`) instead of requiring each individual lane. Individual lane jobs may be
skipped when their domain is not touched, and skipped jobs should not block
merge eligibility.

## Full Verification

Full app image scans and compose-backed smoke tests should run when shared app
contracts change, and should also run on release or scheduled workflows. They do
not need to block an unrelated single-domain pull request.

## Self-Approve Governance

Self-approve remains off by default. A bypass is valid only when:

- The actor is the repository owner.
- The owner explicitly adds the governance label.
- The label event is trusted and auditable.
- The policy report records the actor, trusted label state, matched owners, and approvers.

This gives the solo maintainer a clean merge flow without weakening automated
checks or auditability.
