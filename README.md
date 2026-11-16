---
title: Cloud Cost Copilot
sdk: docker
app_port: 7860
---

# Cloud Cost Copilot

Cloud Cost Copilot is an AI-assisted AWS cost observability prototype. It
combines a FastAPI backend, a browser dashboard, Prometheus metrics, Grafana
visualizations, forecasting, anomaly detection, and optimization suggestions.

The project supports two operating modes:

- **Simulation mode:** safe local demos without an AWS account.
- **AWS mode:** reads EC2, CloudWatch, and Cost Explorer data through an AWS
  profile or IAM role.

> **Project status:** This repository is a working MVP and learning project.
> It is not yet a production-ready multi-tenant SaaS. Authentication,
> persistent customer storage, and organization-level authorization must be
> completed before exposing live AWS data to multiple customers.

## Features

- FastAPI backend with JSON and Prometheus endpoints
- Browser dashboard served at `/app`
- EC2 inventory and CPU monitoring
- AWS cost and month-to-date cost tracking
- Prophet-based cost forecasting
- Isolation Forest anomaly detection
- Idle-resource and right-sizing suggestions
- Grafana dashboard provisioning
- Read-only AWS cross-account role validation
- DeepSeek, Groq, and OpenRouter-compatible AI assistant
- Request limits for external AI providers
- Slack and Discord webhook test alerts
- Supabase tenant schema with Row Level Security foundation
- Docker and Render deployment configuration

## Architecture

```text
Browser dashboard
        |
      FastAPI
     /      \
 AWS APIs   AI provider
        |
 Prometheus -> Grafana
```

The current process stores monitoring history in memory. Restarting the
backend clears that history. Supabase persistence is prepared in
[`supabase/schema.sql`](supabase/schema.sql), but authentication and database
repository wiring are not complete yet.

## Repository Layout

| Path | Purpose |
| --- | --- |
| [`backend/`](backend/) | FastAPI application and cost logic |
| [`frontend/`](frontend/) | Browser dashboard assets |
| [`grafana/`](grafana/) | Provisioned Grafana dashboards and data sources |
| [`supabase/schema.sql`](supabase/schema.sql) | Initial tenant database schema and RLS policies |
| [`aws-connection-template.yaml`](aws-connection-template.yaml) | Read-only customer IAM role template |
| [`Dockerfile`](Dockerfile) | Container image for hosted deployment |
| [`render.yaml`](render.yaml) | Render deployment blueprint |
| [`.env.example`](.env.example) | Safe environment-variable template |

## Requirements

- Python 3.10 or newer
- Git
- Docker Desktop and Docker Compose, optional for Grafana/Prometheus
- AWS CLI v2, optional for real AWS mode

## Local Setup

Clone the repository:

```bash
git clone https://github.com/<your-username>/<your-repository>.git
cd <your-repository>
```

Create a local environment file:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the Backend

For a local dashboard demo:

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- Dashboard: <http://localhost:8000/app>
- API root: <http://localhost:8000/>
- Status: <http://localhost:8000/status>
- API documentation: <http://localhost:8000/docs>

Simulation mode is the safest default:

```env
USE_SIMULATION=true
UPDATE_INTERVAL_SECONDS=300
```

## Run Prometheus and Grafana

Set a local Grafana password in `.env` before starting the containers:

```env
GRAFANA_ADMIN_PASSWORD=replace-with-a-strong-local-password
```

Start the services:

```bash
docker compose up -d
```

Open:

- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001>

The compose file binds both services to `127.0.0.1`. Do not expose them
directly to the public internet.

Stop the services:

```bash
docker compose down
```

## Use Real AWS Data Locally

Use an AWS CLI profile or SSO instead of putting long-lived access keys in
`.env`.

Configure a profile:

```bash
aws configure
```

Or configure SSO:

```bash
aws configure sso
aws sso login --profile <your-profile>
```

Set the profile and region in `.env`:

```env
USE_SIMULATION=false
AWS_PROFILE=<your-profile>
AWS_DEFAULT_REGION=us-east-1
UPDATE_INTERVAL_SECONDS=300
API_ACCESS_TOKEN=replace-with-a-strong-local-token
```

The AWS identity needs these read-only permissions:

```text
ec2:DescribeInstances
cloudwatch:GetMetricStatistics
ce:GetCostAndUsage
```

Run the backend, then open the dashboard. For live mode, protected API
requests require the `X-API-Key` header matching `API_ACCESS_TOKEN`. The
current browser dashboard is designed primarily for simulation mode until
Supabase authentication is connected.

## Dashboard API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/dashboard` | Summary cost and monitoring data |
| `GET` | `/api/instances` | Current EC2 instances and CPU data |
| `GET` | `/api/recommendations` | Optimization suggestions |
| `POST` | `/api/assistant` | Local or external AI assistant |
| `POST` | `/api/aws/validate-role` | Validate a read-only AWS role |
| `POST` | `/api/alerts/test` | Send a Slack/Discord test webhook |
| `GET` | `/metrics` | Prometheus metrics |

Live and AWS-derived endpoints are protected when simulation mode is
disabled. The API token is a temporary prototype perimeter; use Supabase
Auth and organization authorization for a real SaaS deployment.

## AI Providers

The assistant uses the local rules engine when no external provider is
configured. Supported external providers are:

- **OpenRouter:** use a current model ending in `:free`, or `openrouter/free`.
- **Groq:** configure a supported free-tier model.
- **DeepSeek:** configure the DeepSeek API.

Example OpenRouter configuration:

```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=do-not-commit-this
OPENROUTER_MODEL=openrouter/free
AI_MAX_REQUESTS_PER_DAY=20
AI_MAX_QUESTION_CHARS=500
AI_MAX_OUTPUT_TOKENS=300
```

The API key is used only by the backend. The assistant enforces request,
question-length, and output-token limits. The request counter is currently
in memory and must move to Supabase or Redis before multi-instance hosting.

## Slack and Discord Alerts

The dashboard includes a test-alert form. Create an incoming webhook in Slack
or Discord, select the provider in the dashboard, paste the HTTPS webhook URL,
and send a test message.

Webhook URLs are secrets. Never commit them or place them in frontend code.
Persistent customer-specific alert settings and scheduled alert delivery are
planned for the multi-tenant phase.

## AWS Customer Role Template

[`aws-connection-template.yaml`](aws-connection-template.yaml) creates a
read-only cross-account role using an external ID. The service can validate
the role with STS without storing customer access keys.

The hosted multi-customer workflow is not complete yet. Do not collect real
customer AWS credentials through the current public prototype.

## Free Hosting

[`render.yaml`](render.yaml) provides a Render web-service blueprint. The
service should run with:

```env
USE_SIMULATION=true
```

until authentication, tenant isolation, and customer AWS role persistence are
implemented. Add API and AI secrets through the hosting provider's secret
manager, never through Git.

The [`Dockerfile`](Dockerfile) can also be used by any Docker-compatible
hosting provider. Free container availability and quotas vary by provider.

## Security

- Never commit `.env`, API keys, AWS credentials, or webhook URLs.
- Prefer AWS profiles, SSO, or short-lived IAM roles.
- Use read-only AWS permissions until an approval workflow exists.
- Set `API_ACCESS_TOKEN` for live mode.
- Set a strong `GRAFANA_ADMIN_PASSWORD`.
- Keep Prometheus and Grafana private.
- Do not deploy the current prototype publicly with live customer data.
- Review the Supabase RLS policies before enabling multi-tenant access.

## Useful Commands

Refresh metrics manually:

```bash
curl http://localhost:8000/update-metrics
```

View container logs:

```bash
docker compose logs -f
```

Run a syntax check:

```bash
python -m compileall backend
```

## Roadmap

1. Supabase Auth and organization-aware API authorization
2. Persistent cost, metric, recommendation, and alert data
3. Scheduled background workers
4. Customer-specific AWS role connections
5. Scheduled Slack/Discord alerts
6. Approval-based AWS actions
7. Production deployment, monitoring, and billing
