# AI Cloud Cost Optimizer

A lightweight cost-observability project with:

- FastAPI backend (metrics + optimization APIs)
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
- API status: `http://localhost:8000/status`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Grafana default login (unless changed): `admin` / `admin`.

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
