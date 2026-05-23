# Terraform bootstrap workflow

Bootstrap Terraform owns the platform foundation that other workflows depend on:

- Terraform state S3 bucket.
- Terraform lock DynamoDB table.
- GitHub OIDC IAM roles and permission policies for sandbox workflows.
- The approved bootstrap role used to update the bootstrap layer itself.

Because this layer controls IAM, normal local `terraform apply` should be treated as a break-glass path. The standard path is the GitHub Actions workflow:

```text
Actions -> Terraform Bootstrap Apply -> Run workflow
```

## Required GitHub configuration

Create a GitHub Environment named `bootstrap` and require owner approval for deployments to that environment.

Configure these repository secrets or variables:

```text
AWS_ROLE_BOOTSTRAP_ARN
AWS_REGION
TF_STATE_BUCKET
TF_STATE_LOCK_TABLE
TF_STATE_REGION
```

`AWS_ROLE_BOOTSTRAP_ARN` must point to the IAM role managed by `terraform/bootstrap`, usually `Role-Bootstrap`.

## Normal flow

```text
PR changes terraform/bootstrap or bootstrap workflow
-> CI validates Terraform syntax/contracts
-> PR merges into master
-> owner runs Terraform Bootstrap Apply with command=plan
-> owner reviews plan output
-> owner runs Terraform Bootstrap Apply with command=apply and confirm_apply=apply-bootstrap
-> GitHub Environment bootstrap asks for owner approval
-> workflow assumes AWS_ROLE_BOOTSTRAP_ARN
-> terraform/bootstrap apply updates AWS IAM/state foundation
```

The workflow always checks out the trusted default branch and fails if dispatched from another ref. It does not fall back to sandbox, staging, or production roles.

## First bootstrap

The very first creation of the Terraform state backend and `Role-Bootstrap` may still require a one-time admin bootstrap from a trusted machine. After that, ongoing changes should go through the approved workflow above.
