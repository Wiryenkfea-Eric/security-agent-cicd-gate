# 🛡️ AWS Security Agent — Enterprise CI/CD Security Gate

[![AWS Security Agent](https://img.shields.io/badge/AWS_Security_Agent-Preview_2025-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/security-agent/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![AWS Lambda](https://img.shields.io/badge/AWS_Lambda-FF9900?style=for-the-badge&logo=awslambda&logoColor=white)](https://aws.amazon.com/lambda/)
[![Jira](https://img.shields.io/badge/Jira-0052CC?style=for-the-badge&logo=jira&logoColor=white)](https://www.atlassian.com/software/jira)
[![CloudWatch](https://img.shields.io/badge/CloudWatch-FF4F8B?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/cloudwatch/)
[![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> Production-grade shift-left security pipeline built on **AWS Security Agent (Preview, Dec 2025)**. Every pull request to `main` is automatically scanned. CRITICAL and HIGH findings block the merge, no exceptions. Findings are routed to Jira automatically. Severity trends are tracked in CloudWatch.

---

## Overview

Security reviews that happen after the PR is merged are not security controls, they are post-mortems. This pipeline enforces security at the first gate: the pull request itself.

> **📸 Screenshot:** *[Insert: PR page showing ❌ "All checks have failed" + security gate comment with Critical: 2, High: 1, BLOCKS merge]*

**When a developer opens a PR against `main`, this pipeline:**

1. Scans every Python file for command injection, SQL injection, and hardcoded credentials
2. Posts a structured findings report as a PR comment — severity-labelled, immediately actionable
3. Exits with code 1 on CRITICAL or HIGH findings — merge button is disabled, non-negotiable
4. Triggers AWS Lambda via EventBridge — creates a Jira ticket for every actionable finding
5. Pushes severity metrics to CloudWatch — dashboard and alarm update automatically

---

## Architecture

> **📸 Screenshot:** *[Insert: the 3-panel architecture diagram — High-Level, OIDC Auth Flow, Findings Processing Flow]*

**Three layers working together:**

- **Enforcement** — GitHub Actions workflow blocks the PR at the source
- **Response** — EventBridge → Lambda → Jira automates the remediation ticket with zero manual steps
- **Observability** — CloudWatch dashboard tracks severity trends; alarm fires on the first CRITICAL finding

---

## What Gets Detected

| Vulnerability | Severity | Detection |
|---|---|---|
| OS Command Injection (`subprocess` with `shell=True`) | 🔴 CRITICAL | Pattern scan |
| SQL Injection (f-string in `cursor.execute()`) | 🔴 CRITICAL | Pattern scan |
| Hardcoded AWS Credentials | 🟠 HIGH | Pattern scan |
| No Hardcoded Secrets — org policy | 🟠 HIGH | AWS Security Agent |
| Least Privilege IAM — org policy | 🟠 HIGH | AWS Security Agent |
| Input Validation Required — org policy | 🔴 CRITICAL | AWS Security Agent |
| Encryption at Rest — org policy | 🟠 HIGH | AWS Security Agent |
| S3 Public Access Blocked — org policy | 🟠 HIGH | AWS Security Agent |
| API Authentication Required — org policy | 🟠 HIGH | AWS Security Agent |
| OWASP Top 10 (10 managed rules) | CRITICAL–LOW | AWS Security Agent |

---

## Stack

| Layer | Service |
|---|---|
| Security platform | AWS Security Agent (Preview, us-east-1) |
| CI/CD | GitHub Actions |
| Authentication | AWS OIDC — zero long-lived keys stored anywhere |
| Finding processor | AWS Lambda — Python 3.12 |
| Event routing | Amazon EventBridge |
| Secret storage | AWS Secrets Manager |
| Ticket management | Jira Cloud REST API v3 (Atlassian Document Format) |
| Observability | Amazon CloudWatch — custom metrics, dashboard, alarm |

---

## Quick Start

> Full step-by-step implementation guide with every confirmed-working command: **[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)**

**Prerequisites:** AWS account (us-east-1), GitHub repo with admin access, Jira Cloud workspace, AWS CloudShell.

### 1. Activate AWS Security Agent

In the AWS Console (`us-east-1` only) → search **Security Agent** → **Set up AWS Security Agent** → IAM-only access → Create Agent Space named `prod-api-security` → connect your GitHub repo → enable Code Review and Penetration Testing.

### 2. Configure OIDC Authentication

```bash
# Run in AWS CloudShell — replace placeholders with your values
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

aws iam create-role \
  --role-name GitHubActions-SecurityGate \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy \
  --role-name GitHubActions-SecurityGate \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

### 3. Add GitHub Repository Secrets

| Secret | Value |
|---|---|
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `SECURITY_AGENT_SPACE` | Agent Space ID from the console URL (`as-XXXXXXXX-...`) |

### 4. Deploy the Workflow

Commit `.github/workflows/security-gate.yml` directly to `main` — GitHub Actions runs the workflow from the base branch, not the PR branch.

### 5. Deploy Lambda + EventBridge

```bash
# Store Jira credentials — always from a file, never inline
aws secretsmanager create-secret \
  --name /security-gate/jira-credentials \
  --secret-string file://secret.json \
  --region us-east-1

# Deploy Lambda and wire EventBridge
# Full commands in docs/IMPLEMENTATION.md → Phase 4
```

---

## Results

| Capability | Status | Evidence |
|---|---|---|
| PR scanned automatically on open | ✅ Confirmed | Workflow triggers within 30 seconds |
| CRITICAL findings block merge | ✅ Confirmed | exit code 1, merge button disabled |
| HIGH findings block merge | ✅ Confirmed | Included in same test run |
| PR comment with findings table | ✅ Confirmed | Comment posted with severity breakdown |
| Jira ticket created automatically | ✅ Confirmed | KAN-1 created via Lambda invocation |
| CloudWatch metrics published | ✅ Confirmed | `SecurityGate/Findings` namespace populated |
| CloudWatch alarm fires | ✅ Confirmed | `CriticalFindingsAlarm` → "In alarm" state |
| Native AWS Security Agent API | ⏳ Pending | AWS CLI update required — see Known Limitations |

> **📸 Screenshot:** *[Insert: CloudWatch CriticalFindingsAlarm showing "In alarm" in red]*

> **📸 Screenshot:** *[Insert: Jira ticket KAN-1 with Finding Details, file path, and recommendation visible]*

---

## Repository Structure

```
security-agent-cicd-gate/
├── .github/
│   └── workflows/
│       └── security-gate.yml              # CI/CD security gate — blocks PRs on CRITICAL/HIGH
├── lambda/
│   └── finding-processor/
│       ├── lambda_function.py             # Finding processor — Jira + CloudWatch (Python 3.12)
│       └── requirements.txt               # No external deps — stdlib + Lambda-provided boto3
├── test-samples/
│   └── test_vulnerable_DO_NOT_MERGE.py    # Verification test — triggers Critical: 2, High: 1
├── docs/
│   ├── IMPLEMENTATION.md                  # Full 6-phase implementation guide
│   └── screenshots/                       # Architecture diagram + console screenshots
├── .gitignore                             # Excludes credentials, zips, CLI output files
└── README.md
```

---

## Known Limitations

**`aws securityagent` CLI not yet available on GitHub Actions runners.**
The service launched in Preview in December 2025. The CLI package has not been updated to include `start-review`, `list-findings`, or related subcommands. The current workflow uses `grep`-based static scanning as a verified, production-deployable fallback.

When AWS ships the CLI update, the scan step is a single drop-in replacement:

```yaml
- name: Trigger AWS Security Agent review
  run: |
    aws securityagent start-review \
      --agent-space-id "${{ secrets.SECURITY_AGENT_SPACE }}" \
      --review-type CODE_REVIEW \
      --region us-east-1
```

**Other known gaps:**
- Vulnerability patterns cover Python only — no JavaScript, Terraform, or Dockerfile scanning yet
- SNS subscription for email/Slack not confirmed end-to-end
- No pagination on findings list — large codebases may truncate at 100 findings
- MTTR not tracked — Jira tickets are created but resolution time is not measured

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `exit code 252` | `aws securityagent` CLI not available | Use the grep-based workflow in Phase 3 |
| Workflow runs old version | GitHub runs base branch (`main`) workflow, not PR branch | Always commit workflow changes directly to `main` |
| `JSONDecodeError` in Lambda | Secret corrupted by CloudShell inline paste | Recreate secret using `file://secret.json` |
| `HTTP 400: ADF content` — Jira | Description sent as plain string | Use the ADF JSON structure in `lambda_function.py` |
| `HTTP 400: project doesn't exist` | Wrong project key | Run `curl -u email:token .../rest/api/3/project` to list accessible keys |
| `role cannot be assumed by Lambda` | IAM propagation delay | Add `sleep 10` after role creation before `create-function` |

---

## Implementation Guide

The full 6-phase guide — every confirmed-working command, the complete Lambda code, all CloudWatch and EventBridge configuration — is in **[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)**.

The companion Medium article covers the same content with debugging narrative and production context:
**[Read on Medium →](https://medium.com/@ericsolavise)**

---

## Contributing

```bash
git checkout -b feat/your-feature
# make changes — security gate runs automatically on your PR
git commit -m "feat: description"
git push origin feat/your-feature
```

Open a PR. The security gate will scan your changes automatically.

---

*AWS Security Agent Preview 2025 · us-east-1 · Python 3.12 · GitHub Actions · Built by [Wiryenkfea Eric](https://github.com/Wiryenkfea-Eric)*
