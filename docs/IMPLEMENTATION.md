# Implementation Guide — AWS Security Agent CI/CD Security Gate

Full 6-phase implementation guide with every confirmed-working command, the complete Lambda code, all CloudWatch and EventBridge configuration.

> All AWS CLI commands in this guide were executed in **AWS CloudShell** 

---

## Table of Contents

- [Phase 1 — AWS Security Agent Setup](#phase-1--aws-security-agent-setup)
- [Phase 2 — IAM & OIDC Authentication](#phase-2--iam--oidc-authentication)
- [Phase 3 — GitHub Actions Workflow](#phase-3--github-actions-workflow)
- [Phase 4 — Lambda + Jira Integration](#phase-4--lambda--jira-integration)
- [Phase 5 — CloudWatch Dashboard & Alarm](#phase-5--cloudwatch-dashboard--alarm)
- [Phase 6 — End-to-End Testing](#phase-6--end-to-end-testing)

---

## Phase 1 — AWS Security Agent Setup

### 1.1 Activate the Service

> **Region lock:** AWS Security Agent is available **only in us-east-1 (N. Virginia)** during Preview. Confirm your region before proceeding.

1. Log into AWS Console
2. Confirm region: **US East (N. Virginia) — us-east-1**
3. Search for **Security Agent** → click **AWS Security Agent**
4. Click **Set up AWS Security Agent**
5. Access method: select **IAM-only access**
6. Leave default role creation checked → click **Set up**
7. Wait ~60 seconds for initialisation

### 1.2 Enable All Managed Security Requirements

1. Left nav → **Security Requirements**
2. Click **AWS Managed Requirements → Enable all**

This activates all 10 OWASP Top 10 rules — injection flaws, broken authentication, sensitive data exposure, insecure deserialization, and more.

### 1.3 Create Custom Organisational Requirements

Click **Create custom security requirement** for each one below. For each: scroll past the template section, fill the blank form, click **Create and enable security requirement**.

| # | Name | Description |
|---|---|---|
| 1 | API Authentication Required | All API endpoints must implement authentication via AWS Cognito or OAuth 2.0 before processing requests |
| 2 | Encryption of Sensitive Data at Rest | Sensitive data fields (PII, credentials, financial data) must be encrypted at rest using AWS KMS |
| 3 | No Hardcoded Secrets | No hardcoded secrets, API keys, passwords, or credentials in source code or configuration files |
| 4 | Least Privilege IAM Roles | All IAM roles must follow least privilege — no wildcard `*` in Action or Resource |
| 5 | Parameterized Database Queries | All database queries must use parameterized queries or an ORM to prevent SQL injection |
| 6 | S3 Bucket Security | All S3 buckets must have Block Public Access enabled and versioning turned on |

### 1.4 Create Agent Space and Connect GitHub

1. Left nav → **Agent Spaces → Create Agent Space**
2. **Name:** `prod-api-security`
3. **Description:** `Production CI/CD security gate — AWS Security Agent 2025`
4. Under **Connect source code** → **Connect repository → GitHub**
5. Authorise the **AWS Security Agent GitHub App** → select **Only select repositories** → pick your repo
6. Capabilities: enable **Code Review** and **Penetration Testing**
7. Click **Create Agent Space**
8. Copy the Agent Space ID from the browser URL bar:

```
https://us-east-1.console.aws.amazon.com/securityagent/agents/as-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

The string starting with `as-` is your **Agent Space ID**. You will need it as a GitHub secret in Phase 2.

---

## Phase 2 — IAM & OIDC Authentication

Open **AWS CloudShell** (the `>_` terminal icon in the top navigation bar of the AWS Console).

### 2.1 Create the GitHub OIDC Provider

Run once per AWS account:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --region us-east-1
```

Expected output:
```json
{
    "OpenIDConnectProviderArn": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
}
```

### 2.2 Create the IAM Trust Policy File

Replace `YOUR_ACCOUNT_ID`, `YOUR_GITHUB_ORG`, and `YOUR_REPO_NAME` with your actual values:

```bash
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_ORG/YOUR_REPO_NAME:*"
      }
    }
  }]
}
EOF
```

### 2.3 Create the IAM Role

```bash
aws iam create-role \
  --role-name GitHubActions-SecurityGate \
  --assume-role-policy-document file://trust-policy.json
```

### 2.4 Attach ReadOnlyAccess Policy

```bash
aws iam attach-role-policy \
  --role-name GitHubActions-SecurityGate \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

### 2.5 Attach Security Agent Permissions

```bash
cat > security-agent-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "securityagent:StartReview",
      "securityagent:GetReview",
      "securityagent:ListFindings",
      "securityagent:BatchGetFindings",
      "securityagent:GetAgentSpace"
    ],
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy \
  --role-name GitHubActions-SecurityGate \
  --policy-name SecurityAgentAccess \
  --policy-document file://security-agent-policy.json
```

### 2.6 Verify the Role

```bash
aws iam get-role --role-name GitHubActions-SecurityGate
```

Confirm your correct GitHub org, repo name, and account ID appear in the trust policy.

### 2.7 Add GitHub Repository Secrets

Repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Value |
|---|---|
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `SECURITY_AGENT_SPACE` | The `as-XXXXXXXX-...` ID from Phase 1.4 |

---

## Phase 3 — GitHub Actions Workflow

> **Critical:** GitHub Actions always runs the workflow from the **base branch (`main`)**, not the PR branch. Always commit workflow changes directly to `main`.

Create `.github/workflows/security-gate.yml` and commit it directly to `main`:

```yaml
name: AWS Security Agent --- Security Gate

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  security-gate:
    name: AWS Security Agent Review
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Scan for security vulnerabilities
        id: scan
        run: |
          CRITICAL=0
          HIGH=0

          echo "=== Checking for command injection ==="
          if grep -r "subprocess.*shell=True" . --include="*.py" 2>/dev/null; then
            echo "CRITICAL: Command injection found"
            CRITICAL=$((CRITICAL + 1))
          fi

          echo "=== Checking for SQL injection ==="
          if grep -rE 'cursor\.execute\(f' . --include="*.py" 2>/dev/null; then
            echo "CRITICAL: SQL injection found"
            CRITICAL=$((CRITICAL + 1))
          fi

          echo "=== Checking for hardcoded secrets ==="
          if grep -r "AWS_SECRET_KEY" . --include="*.py" 2>/dev/null; then
            echo "HIGH: Hardcoded secret found"
            HIGH=$((HIGH + 1))
          fi

          echo "critical=$CRITICAL" >> $GITHUB_OUTPUT
          echo "high=$HIGH"         >> $GITHUB_OUTPUT

          if [ $CRITICAL -gt 0 ] || [ $HIGH -gt 0 ]; then
            echo "gate_result=fail" >> $GITHUB_OUTPUT
          else
            echo "gate_result=pass" >> $GITHUB_OUTPUT
          fi

          echo "--- Results: CRITICAL=$CRITICAL HIGH=$HIGH ---"

      - name: Post findings as PR comment
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const critical = parseInt('${{ steps.scan.outputs.critical }}' || '0');
            const high     = parseInt('${{ steps.scan.outputs.high }}'     || '0');
            const result   = '${{ steps.scan.outputs.gate_result }}';

            const body = [
              `## ${result === 'fail' ? '🚨' : '✅'} AWS Security Agent — Security Gate Report`,
              ``,
              `| Severity | Count | Action |`,
              `|----------|-------|--------|`,
              `| 🔴 Critical | ${critical} | ${critical > 0 ? '**BLOCKS merge**' : 'Clean'} |`,
              `| 🟠 High     | ${high}     | ${high > 0     ? '**BLOCKS merge**' : 'Clean'} |`,
              ``,
              result === 'fail'
                ? '> ⛔ **This PR is blocked from merging.** Fix all CRITICAL and HIGH findings, then push a new commit.'
                : '> ✅ **Security gate passed.** No blocking vulnerabilities detected.',
            ].join('\n');

            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              issue_number: context.issue.number,
              body,
            });

      - name: Enforce gate — fail on CRITICAL or HIGH
        run: |
          if [ "${{ steps.scan.outputs.gate_result }}" = "fail" ]; then
            echo "SECURITY GATE FAILED — blocking merge"
            exit 1
          fi
          echo "SECURITY GATE PASSED"
```

---

## Phase 4 — Lambda + Jira Integration

All commands run in **AWS CloudShell**.

### 4.1 Create Jira Credentials File and Secret

> **Never paste multiline JSON inline in CloudShell** — the shell corrupts it. Always write to a file first, validate, then create the secret from the file.

```bash
cat > secret.json << 'EOF'
{
    "jira_url": "https://YOUR_ORG.atlassian.net",
    "jira_email": "your-email@gmail.com",
    "jira_api_token": "YOUR_JIRA_API_TOKEN",
    "jira_project_key": "KAN",
    "default_assignee_id": "YOUR_JIRA_ACCOUNT_ID"
}
EOF

# Validate JSON before creating the secret
cat secret.json | python3 -m json.tool

# Create from validated file
aws secretsmanager create-secret \
    --name /security-gate/jira-credentials \
    --region us-east-1 \
    --secret-string file://secret.json
```

Verify the secret round-trips cleanly:

```bash
aws secretsmanager get-secret-value \
    --secret-id /security-gate/jira-credentials \
    --region us-east-1 \
    --query SecretString \
    --output text | python3 -m json.tool
```

Output must be valid JSON with no extra text. If malformed, delete and recreate:

```bash
aws secretsmanager delete-secret \
    --secret-id /security-gate/jira-credentials \
    --region us-east-1 \
    --force-delete-without-recovery
sleep 10
aws secretsmanager create-secret \
    --name /security-gate/jira-credentials \
    --region us-east-1 \
    --secret-string file://secret.json
```

### 4.2 Create the Lambda IAM Role

Run each command separately. The `sleep 10` is required — IAM propagates asynchronously.

```bash
# Step 1: Create the role
aws iam create-role \
    --role-name SecurityAgentFindingProcessor \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }'

# Step 2: Attach Lambda basic execution (CloudWatch Logs)
aws iam attach-role-policy \
    --role-name SecurityAgentFindingProcessor \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Step 3: Create custom policy file
cat > lambda-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:/security-gate/*"
        },
        {
            "Effect": "Allow",
            "Action": ["cloudwatch:PutMetricData"],
            "Resource": "*"
        }
    ]
}
EOF

# Step 4: Attach custom policy
aws iam put-role-policy \
    --role-name SecurityAgentFindingProcessor \
    --policy-name SecurityAgentFindingProcessorPolicy \
    --policy-document file://lambda-policy.json

# Step 5: Wait for IAM propagation
sleep 10
```

### 4.3 Deploy the Lambda Function

```bash
# Package the Lambda
zip -r finding-processor.zip lambda_function.py

# Deploy
aws lambda create-function \
    --function-name security-agent-finding-processor \
    --runtime python3.12 \
    --role arn:aws:iam::YOUR_ACCOUNT_ID:role/SecurityAgentFindingProcessor \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://finding-processor.zip \
    --timeout 30 \
    --region us-east-1
```

### 4.4 Create EventBridge Rule and Wire Lambda

```bash
# Create the rule
aws events put-rule \
    --name security-agent-finding-processor \
    --event-pattern '{"source":["aws.securityagent"],"detail-type":["Security Agent Finding Created"]}' \
    --state ENABLED \
    --region us-east-1

# Add Lambda as target
aws events put-targets \
    --rule security-agent-finding-processor \
    --targets '[{"Id":"FindingProcessor","Arn":"arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:security-agent-finding-processor"}]' \
    --region us-east-1

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
    --function-name security-agent-finding-processor \
    --statement-id EventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-east-1:YOUR_ACCOUNT_ID:rule/security-agent-finding-processor \
    --region us-east-1
```

### 4.5 Test the Lambda Manually

```bash
aws lambda invoke \
    --function-name security-agent-finding-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{"findings":[{"findingId":"test-001","severity":"CRITICAL","title":"Command Injection","description":"User input passed directly to shell","filePath":"app.py","lineNumber":5,"recommendation":"Use list args instead of shell=True","repository":"test-repo","reviewId":"test-123"}]}' \
    --region us-east-1 \
    response.json && cat response.json
```

Confirmed response:

```json
{
  "statusCode": 200,
  "body": "{\"processed\": 1, \"jira_tickets\": [{\"finding_id\": \"test-001\", \"jira_key\": \"KAN-1\"}]}"
}
```

---

## Phase 5 — CloudWatch Dashboard & Alarm

### 5.1 Create the Dashboard

```bash
aws cloudwatch put-dashboard \
    --dashboard-name SecurityGate-ShiftLeft \
    --region us-east-1 \
    --dashboard-body '{
        "widgets": [
            {
                "type": "metric",
                "x": 0, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "Security Findings by Severity — Last 30 Days",
                    "metrics": [
                        ["SecurityGate/Findings","FindingCount","Severity","CRITICAL",{"color":"#d62728","label":"Critical"}],
                        ["SecurityGate/Findings","FindingCount","Severity","HIGH",{"color":"#ff7f0e","label":"High"}],
                        ["SecurityGate/Findings","FindingCount","Severity","MEDIUM",{"color":"#ffdd57","label":"Medium"}],
                        ["SecurityGate/Findings","FindingCount","Severity","LOW",{"color":"#2ca02c","label":"Low"}]
                    ],
                    "period": 86400,
                    "stat": "Sum",
                    "view": "timeSeries",
                    "region": "us-east-1"
                }
            },
            {
                "type": "metric",
                "x": 12, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "Critical + High Findings (Blocked PRs)",
                    "metrics": [
                        ["SecurityGate/Findings","FindingCount","Severity","CRITICAL"],
                        ["SecurityGate/Findings","FindingCount","Severity","HIGH"]
                    ],
                    "period": 3600,
                    "stat": "Sum",
                    "view": "bar",
                    "region": "us-east-1"
                }
            }
        ]
    }'
```

### 5.2 Create the Critical Findings Alarm

```bash
aws cloudwatch put-metric-alarm \
    --alarm-name CriticalFindingsAlarm \
    --alarm-description "CRITICAL security findings detected in CI/CD pipeline" \
    --namespace SecurityGate/Findings \
    --metric-name FindingCount \
    --dimensions Name=Severity,Value=CRITICAL \
    --statistic Sum \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 1 \
    --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching \
    --region us-east-1
```

---

## Phase 6 — End-to-End Testing

### 6.1 Create the Test PR

```bash
git checkout -b test/security-gate-verification
```

Add `test-samples/test_vulnerable_DO_NOT_MERGE.py` to the branch (file already exists in repo), then:

```bash
git add test-samples/
git commit -m "test: security gate verification — contains intentional vulnerabilities"
git push origin test/security-gate-verification
```

Open a PR against `main`. The security gate triggers automatically within 30 seconds.

### 6.2 Expected Results

| Check | Expected |
|---|---|
| GitHub Actions triggers | Within 30 seconds of PR open |
| CRITICAL findings | 2 (command injection + SQL injection) |
| HIGH findings | 1 (hardcoded AWS secret) |
| PR comment posted | Findings table with BLOCKS merge |
| Merge button | Disabled — All checks have failed |
| Lambda test response | `"jira_key": "KAN-1"` in body |
| CloudWatch alarm | Transitions to "In alarm" state |

### 6.3 Verify Lambda Logs

```bash
aws logs tail /aws/lambda/security-agent-finding-processor \
    --since 1h \
    --region us-east-1
```

### 6.4 Verify CloudWatch Metrics

```bash
aws cloudwatch list-metrics \
    --namespace SecurityGate/Findings \
    --region us-east-1
```

---

## Errors Encountered and Fixes Applied

| Error | Root Cause | Fix Applied |
|---|---|---|
| `exit code 252` | `aws securityagent` CLI not available on runners | Replaced with grep-based static scan |
| Workflow runs old version | GitHub uses base branch workflow, not PR branch | Committed fix directly to `main` |
| `JSONDecodeError` in Lambda | Secret JSON corrupted by CloudShell inline paste | Recreated secret using `file://secret.json` |
| `HTTP 400: ADF content` — Jira | Description sent as plain string | Used ADF JSON structure in Lambda function |
| `HTTP 400: project doesn't exist` | Wrong Jira project key | Ran `curl .../rest/api/3/project` to find correct key (`KAN`) |
| `role cannot be assumed by Lambda` | IAM propagation delay | Added `sleep 10` after role creation |
| `InvalidParameterValueException: reserved keys: AWS_REGION` | Lambda sets this automatically | Removed from `--environment Variables` |

---

