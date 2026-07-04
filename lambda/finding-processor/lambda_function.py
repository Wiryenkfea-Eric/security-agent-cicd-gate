import json
import boto3
import urllib.request
import base64

REGION = "us-east-1"
secrets_client = boto3.client("secretsmanager", region_name=REGION)
cloudwatch     = boto3.client("cloudwatch",     region_name=REGION)


def get_jira_creds():
    secret = secrets_client.get_secret_value(
        SecretId="/security-gate/jira-credentials"
    )
    return json.loads(secret["SecretString"])


def create_jira_ticket(creds, finding):
    severity       = finding.get("severity",       "UNKNOWN")
    title          = finding.get("title",          "Security Finding")
    description    = finding.get("description",    "No description")
    repo           = finding.get("repository",     "unknown-repo")
    file_path      = finding.get("filePath",       "N/A")
    line_number    = finding.get("lineNumber",     "N/A")
    recommendation = finding.get("recommendation", "See Security Agent console.")
    review_id      = finding.get("reviewId",       "N/A")
    finding_id     = finding.get("findingId",      "N/A")

    priority_map = {
        "CRITICAL": "Highest",
        "HIGH":     "High",
        "MEDIUM":   "Medium",
        "LOW":      "Low",
    }

    description_adf = {
        "type": "doc", "version": 1,
        "content": [
            {
                "type": "heading", "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Finding Details"}]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Description: ",
                     "marks": [{"type": "strong"}]},
                    {"type": "text", "text": description}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text",
                     "text": f"File: {file_path} | Line: {line_number}"}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Recommendation: ",
                     "marks": [{"type": "strong"}]},
                    {"type": "text", "text": recommendation}
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text",
                     "text": f"Review ID: {review_id} | Finding ID: {finding_id}"}
                ]
            },
        ]
    }

    payload = {
        "fields": {
            "project":     {"key": creds["jira_project_key"]},
            "summary":     f"[{severity}] {title}",
            "description": description_adf,
            "issuetype":   {"name": "Task"},
            "priority":    {"name": priority_map.get(severity, "Medium")},
            "labels":      ["security-agent", f"severity-{severity.lower()}", repo]
        }
    }

    auth = base64.b64encode(
        f"{creds['jira_email']}:{creds['jira_api_token']}".encode()
    ).decode()

    req = urllib.request.Request(
        f"{creds['jira_url']}/rest/api/3/issue",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type":  "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["key"]


def push_metrics(findings):
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        counts[f.get("severity", "LOW")] += 1

    cloudwatch.put_metric_data(
        Namespace="SecurityGate/Findings",
        MetricData=[
            {
                "MetricName": "FindingCount",
                "Dimensions": [{"Name": "Severity", "Value": sev}],
                "Value": float(count),
                "Unit": "Count"
            }
            for sev, count in counts.items() if count > 0
        ]
    )


def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")

    findings = event.get("findings", [event.get("detail", event)])
    if not findings:
        return {"statusCode": 200, "body": "No findings"}

    creds = get_jira_creds()
    push_metrics(findings)

    results = []
    for finding in findings:
        if finding.get("severity") in {"CRITICAL", "HIGH", "MEDIUM"}:
            try:
                key = create_jira_ticket(creds, finding)
                print(f"Created {key} for {finding.get('severity')} finding")
                results.append({
                    "finding_id": finding.get("findingId"),
