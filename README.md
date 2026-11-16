---
title: Cloud Cost Copilot
sdk: docker
app_port: 7860
---

# AI Cloud Cost Optimizer

A lightweight cost-observability project with:

- FastAPI backend (metrics + optimization APIs)
- Built-in browser dashboard at `/app` (no frontend build required)
- Prometheus scraping
- Grafana dashboard provisioning
- Two runtime modes:
  - Simulation mode (no AWS account needed)
  - Real AWS mode (AWS CLI/profile + permissions)

## Project Structure

- `backend/` FastAPI app and cost logic
- `grafana/` dashboard and datasource provisioning
- `docker-compose.yml` Prometheus + Grafana services
- `prometheus.yml` Prometheus scrape config
- `.env.example` safe environment template

## Prerequisites

- Python 3.10+
- Docker Desktop (or Docker Engine + Compose)
- Git
- (Optional, real mode only) AWS CLI v2

## 1) Clone And Setup

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

Create your env file:

```bash
cp .env.example .env
```

Windows PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

Install Python dependencies:

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

## 2) Run Prometheus + Grafana

```bash
docker compose up -d
```

## 3) Run Backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 4) Open The App

- API root: `http://localhost:8000/`
- User dashboard: `http://localhost:8000/app`
- API status: `http://localhost:8000/status`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Grafana username is `admin`; set `GRAFANA_ADMIN_PASSWORD` to a strong local
password before starting the containers.
For safety, the compose file binds Prometheus and Grafana to localhost only
and requires `GRAFANA_ADMIN_PASSWORD` before starting. Do not expose either
service directly to the internet.

---

## Mode A: Simulation (No AWS Needed)

In `.env`:

```env
USE_SIMULATION=true
UPDATE_INTERVAL_SECONDS=300
```

This mode generates synthetic instance and cost data so anyone can run the project locally.

---

## Mode B: Real AWS Data (AWS CLI + Profile)

### Step 1: Configure AWS CLI

Use one of these:

```bash
aws configure
```

or (recommended for org accounts):

```bash
aws configure sso
aws sso login --profile <your-profile>
```

### Step 2: Set `.env` for Real Mode

```env
USE_SIMULATION=false
AWS_PROFILE=<your-profile>
AWS_DEFAULT_REGION=ap-south-1
UPDATE_INTERVAL_SECONDS=300
```

If you used `aws configure` without a named profile, you can use:

```env
AWS_PROFILE=default
```

### Step 3: Minimum AWS Permissions Needed

Your IAM user/role should allow:

- `ec2:DescribeInstances`
- `cloudwatch:GetMetricStatistics`
- `ce:GetCostAndUsage`

Without these permissions, the app will fall back or show limited real data.

---

## Security Notes (Important)

- Never commit secrets to GitHub.
- `.env` is ignored by `.gitignore` and should stay local only.
- Use `.env.example` as the shareable template.
- Prefer AWS profiles/SSO over hardcoded keys.

## Share With Friends

1. Push this repo to GitHub.
2. Send the repository link.
3. Ask them to follow the setup steps above in either:
   - Simulation mode (quick start), or
   - Real AWS mode (their own AWS profile + permissions).

## Useful Commands

Stop containers:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
```

Manual metric refresh:

```bash
curl http://localhost:8000/update-metrics
```

## Browser Dashboard

The dashboard is intentionally served by FastAPI so it can be deployed on a
free web service without a separate frontend build. It currently provides:

- Connection/mode status
- Current cost, month-to-date cost, forecast, and idle-resource cards
- EC2 instance table with CPU usage
- A local rules-based assistant for cost, forecast, and idle-resource questions
- AWS role validation form
- Slack/Discord test-alert form
- Link to the advanced Grafana dashboard

The dashboard API is available at:

- `GET /api/dashboard`
- `GET /api/instances`
- `GET /api/recommendations`
- `POST /api/aws/validate-role`
- `POST /api/assistant`
- `POST /api/alerts/test`

Set `FRONTEND_ORIGINS` to a comma-separated list when hosting a separate
frontend. The current `/app` dashboard uses same-origin requests by default.

## SaaS Roadmap

The current app is a single-process prototype. Before connecting multiple
customers, add Supabase Auth/Postgres with Row Level Security, organization
IDs on every customer-owned record, and a cross-account AWS IAM role flow.
Customers should grant a read-only role through
[`aws-connection-template.yaml`](aws-connection-template.yaml), and the service
should use STS AssumeRole; never collect or store AWS access keys.
The initial tenant schema is in [`supabase/schema.sql`](supabase/schema.sql).

### API access protection

Simulation mode is intentionally open for local demos. Live mode protects all
AWS-derived endpoints, `/metrics`, and mutation-like endpoints with the
`X-API-Key` header. Set a strong `API_ACCESS_TOKEN` in the hosting provider's
secret settings before enabling live mode. This is a temporary perimeter for
the prototype; Supabase Auth and organization-level authorization must replace
it before public multi-tenant use.

## Free Hosting

The repository includes [`render.yaml`](render.yaml) for a free Render web
service. Set `DEEPSEEK_API_KEY` as a Render secret and keep
`USE_SIMULATION=true` until a customer AWS role connection is configured.
Supabase Auth/Postgres and per-customer webhook storage still need to be wired
before this is used as a public multi-tenant service.

The [`Dockerfile`](Dockerfile) also supports Hugging Face Spaces. Create a
Docker Space, point it at this repository, and configure `PORT=7860`,
`USE_SIMULATION=true`, `AI_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and a
current OpenRouter model ending in `:free` as Space secrets/variables. Free
model names and quotas can change, so choose the currently available model in
the OpenRouter dashboard rather than hard-coding one in the repository.

## DeepSeek Assistant

Set `AI_PROVIDER=deepseek` and `DEEPSEEK_API_KEY` in the hosting provider's
secret settings to enable the DeepSeek-backed assistant. The integration uses
DeepSeek's OpenAI-compatible `/chat/completions` endpoint with `deepseek-flash`
by default. For free-tier experiments, the same adapter supports `groq` and
`openrouter`; OpenRouter is restricted to models ending in `:free`.

The assistant has default safety boundaries: 20 external requests per process
day, 500-character questions, and 300 output tokens. Configure these with
`AI_MAX_REQUESTS_PER_DAY`, `AI_MAX_QUESTION_CHARS`, and
`AI_MAX_OUTPUT_TOKENS`. The key is never sent to the browser. The request
counter is intentionally in memory for this prototype and must move to
Supabase/Redis before multi-instance hosting.

The alert test endpoint accepts only HTTPS Slack and Discord webhook hosts:
`POST /api/alerts/test` with `provider`, `webhook_url`, and `message`. Store
webhook URLs in a secret manager or Supabase Vault before enabling customer
settings; do not persist them in frontend code or source control.
