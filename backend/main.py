# AI-assisted Cloud Cost Optimizer backend (human-built with AI assistance)
# Main FastAPI service exposing Prometheus metrics + optimization endpoints.
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aws_fetch import get_ec2_instances, get_cpu_utilization
from aws_session import is_aws_configured, use_simulation_mode
from cost_engine import calculate_cost
from cost_explorer import get_cost_last_complete_day_usd, get_cost_month_to_date_usd
from forecast import add_cost_data, predict_future_cost, get_trend
from optimizer import update_instance_stats, get_all_suggestions, get_idle_confidence_report
from aws_connection import validate_aws_role
from ai_assistant import DeepSeekError, ask_deepseek, external_ai_enabled
from alerts import AlertDeliveryError, send_alert
import threading
import time
import random
import hmac
from datetime import datetime
from pathlib import Path

# Create FastAPI app
app = FastAPI()

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", "http://localhost:8000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=frontend_dir), name="frontend-assets")

# My variables for the dashboard graphs
total_cost_metric = Gauge("cloud_estimated_cost", "Estimated Cloud Cost")
cost_mtd_metric = Gauge("cloud_cost_month_to_date", "AWS month-to-date cost (UnblendedCost USD)")
cpu_metric = Gauge("cloud_cpu_usage", "CPU Usage per instance", ["instance_id"])
anomaly_metric = Gauge("cost_anomaly_detected", "Cost anomaly flag")
predicted_cost_metric = Gauge("cloud_predicted_monthly_cost", "Predicted monthly cost")
budget_risk_metric = Gauge("cloud_budget_risk", "Budget Risk Level")
idle_instances_count_metric = Gauge("cloud_idle_instances_count", "Number of likely idle EC2 instances")
idle_confidence_metric = Gauge(
    "cloud_ec2_idle_confidence",
    "Idle confidence score per EC2 instance and time window",
    ["instance_id", "window"],
)
idle_flag_metric = Gauge(
    "cloud_ec2_idle_flag",
    "Idle flag per EC2 instance and time window (1=idle_likely)",
    ["instance_id", "window"],
)

# Store historical values
cost_history = []
total_cost_history = []
latest_instances = []
latest_instance_cpu = {}


def _runtime_mode():
    simulation = use_simulation_mode()
    aws_ok = is_aws_configured()
    if simulation:
        return "simulation"
    if aws_ok:
        return "aws_live"
    return "fallback"


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def require_api_access(x_api_key: str | None = Header(default=None)) -> None:
    """Keep live AWS-derived endpoints private until user authentication is wired."""
    if use_simulation_mode() and not _truthy(os.environ.get("REQUIRE_API_AUTH")):
        return

    expected = os.environ.get("API_ACCESS_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API_ACCESS_TOKEN must be configured for live API access",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key header required")


# Detect cost anomalies (IsolationForest on recent history)
def detect_anomaly(current_cost):
    global cost_history
    
    cost_history.append(current_cost)
    
    # Need at least 10 data points
    if len(cost_history) < 10:
        return 0
    
    # IsolationForest anomaly detection on recent cost points
    from sklearn.ensemble import IsolationForest
    import numpy as np
    
    model = IsolationForest(contamination=0.15)
    data = np.array(cost_history[-20:]).reshape(-1, 1)
    model.fit(data)
    
    prediction = model.predict(data)
    
    if prediction[-1] == -1:
        return 1
    return 0


# Function to get latest data from AWS and update everything
def update_metrics():
    global latest_instances
    instances = get_ec2_instances()
    latest_instances = instances
    now = datetime.now()

    total_cost = None
    cost_mtd = None
    simulated_hours = None

    if (not use_simulation_mode()) and is_aws_configured():
        # Real AWS spend from Cost Explorer (account-level).
        total_cost = get_cost_last_complete_day_usd()
        cost_mtd = get_cost_month_to_date_usd()
    else:
        # Simulation mode: generate synthetic costs.
        if random.random() < 0.3:
            simulated_hours = random.uniform(15, 25)  # spike
        else:
            simulated_hours = random.uniform(1, 5)
        total_cost = 0.0
    
    for instance in instances:
        cpu = get_cpu_utilization(instance["id"])
        latest_instance_cpu[instance["id"]] = cpu
        cpu_metric.labels(instance_id=instance["id"]).set(cpu)

        # Only compute per-instance costs in simulation mode.
        cost = 0.0
        if simulated_hours is not None:
            cost = calculate_cost(instance["type"], simulated_hours)
            total_cost += cost

        # Update optimizer stats
        update_instance_stats(instance["id"], cpu, cost, now)
    
    # If no instances, use baseline cost
    if not instances:
        if total_cost is None:
            total_cost = random.uniform(1, 10)

    if total_cost is None:
        # Cost Explorer not enabled/authorized; fall back to simulation-ish value
        total_cost = random.uniform(1, 5)
    
    total_cost_metric.set(total_cost)
    if cost_mtd is not None:
        cost_mtd_metric.set(cost_mtd)
    total_cost_history.append(total_cost)
    
    # Keep only last 50 values
    if len(total_cost_history) > 50:
        total_cost_history.pop(0)
    
    # Anomaly detection
    anomaly = detect_anomaly(total_cost)
    anomaly_metric.set(anomaly)
    
    # Add to forecast data
    add_cost_data(now, total_cost)
    
    # Predict future cost
    predicted_monthly, _ = predict_future_cost(30)
    if predicted_monthly:
        predicted_cost_metric.set(predicted_monthly)
        
        # Calculate budget risk based on predicted monthly cost
        risk = 0
        if predicted_monthly > 500:
            risk = 2
        elif predicted_monthly > 100:
            risk = 1
        budget_risk_metric.set(risk)

    # Publish idle confidence metrics for Grafana.
    idle_report = get_idle_confidence_report()
    idle_instances_count_metric.set(sum(1 for r in idle_report if r.get("overall_idle_likely")))
    idle_confidence_metric.clear()
    idle_flag_metric.clear()
    for row in idle_report:
        instance_id = row.get("instance_id")
        idle_24h = row.get("idle_24h", {})
        idle_7d = row.get("idle_7d", {})
        for window_key, window_row in (("24h", idle_24h), ("7d", idle_7d)):
            confidence = float(window_row.get("idle_confidence", 0.0))
            is_idle = 1.0 if bool(window_row.get("is_idle")) else 0.0
            idle_confidence_metric.labels(instance_id=instance_id, window=window_key).set(confidence)
            idle_flag_metric.labels(instance_id=instance_id, window=window_key).set(is_idle)


# Run this in a loop so we always have fresh data
def background_updater():
    update_interval = int(os.environ.get("UPDATE_INTERVAL_SECONDS", "300"))
    while True:
        try:
            update_metrics()
        except Exception as e:
            print("Error updating metrics:", e)
        time.sleep(max(15, update_interval))


@app.on_event("startup")
def start_background_task():
    thread = threading.Thread(target=background_updater)
    thread.daemon = True
    thread.start()


# API endpoints
@app.get("/app", include_in_schema=False)
def app_home():
    return FileResponse(frontend_dir / "index.html")


@app.get("/")
def root():
    mode = _runtime_mode()
    return {
        "name": "AI-Assisted Cloud Cost Optimizer",
        "version": "1.0.0",
        "mode": mode,
        "aws_status": "Connected" if mode == "aws_live" else ("Simulation Mode" if mode == "simulation" else "Fallback Mode"),
    }


@app.get("/status", dependencies=[Depends(require_api_access)])
def status():
    mode = _runtime_mode()
    instances = get_ec2_instances()
    return {
        "mode": mode,
        "simulation_mode": use_simulation_mode(),
        "aws_configured": (not use_simulation_mode()) and is_aws_configured(),
        "instances_count": len(instances),
        "instance_ids": [x.get("id") for x in instances],
        "anomaly_detection": "active",
        "forecasting": "active"
    }


@app.get("/api/dashboard", dependencies=[Depends(require_api_access)])
def dashboard():
    predicted_monthly, _ = predict_future_cost(30)
    idle_report = get_idle_confidence_report()
    return {
        "mode": _runtime_mode(),
        "aws_connected": _runtime_mode() == "aws_live",
        "instances_count": len(latest_instances),
        "estimated_cost": total_cost_history[-1] if total_cost_history else None,
        "month_to_date_cost": cost_mtd_metric._value.get(),
        "predicted_monthly_cost": predicted_monthly,
        "trend": get_trend(),
        "anomaly_detected": bool(anomaly_metric._value.get()),
        "idle_instances_count": sum(
            1 for row in idle_report if row.get("overall_idle_likely")
        ),
    }


@app.get("/api/instances", dependencies=[Depends(require_api_access)])
def instances():
    return {
        "mode": _runtime_mode(),
        "instances": [
            {
                **instance,
                "cpu": latest_instance_cpu.get(instance["id"]),
            }
            for instance in latest_instances
        ],
    }


@app.get("/api/recommendations", dependencies=[Depends(require_api_access)])
def recommendations():
    return {
        "recommendations": get_all_suggestions(total_cost_history),
        "idle_report": get_idle_confidence_report(),
    }


@app.post("/api/aws/validate-role", dependencies=[Depends(require_api_access)])
def validate_role(payload: dict):
    role_arn = str(payload.get("role_arn", "")).strip()
    external_id = str(payload.get("external_id", "")).strip()
    try:
        return validate_aws_role(role_arn, external_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/assistant", dependencies=[Depends(require_api_access)])
def assistant(payload: dict):
    question = str(payload.get("question", "")).strip()
    if not question:
        return {"answer": "Ask me about costs, idle instances, forecasts, or savings."}

    dashboard_data = dashboard()
    instance_data = instances()
    recommendation_data = recommendations()
    if external_ai_enabled():
        try:
            answer = ask_deepseek(
                question,
                {
                    "dashboard": dashboard_data,
                    "instances": instance_data["instances"],
                    "recommendations": recommendation_data["recommendations"],
                    "mode": _runtime_mode(),
                },
            )
            return {"answer": answer, "provider": "deepseek"}
        except DeepSeekError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    idle_count = sum(
        1 for row in get_idle_confidence_report() if row.get("overall_idle_likely")
    )
    latest_cost = total_cost_history[-1] if total_cost_history else None
    normalized = question.lower()

    if "idle" in normalized or "waste" in normalized:
        answer = (
            f"I found {idle_count} likely idle instance(s). "
            "Review the recommendation before making any change."
        )
    elif "forecast" in normalized or "future" in normalized or "budget" in normalized:
        predicted, _ = predict_future_cost(30)
        answer = (
            f"The current 30-day forecast is ${predicted:.2f}."
            if predicted is not None
            else "I need more cost history before I can calculate a forecast."
        )
    elif "cost" in normalized or "bill" in normalized:
        answer = (
            f"The latest tracked cost is ${latest_cost:.2f}."
            if latest_cost is not None
            else "Cost data is not available yet. Run a metrics refresh first."
        )
    else:
        answer = (
            "I can currently answer questions about cost, forecasts, idle "
            "instances, and waste. Connect an LLM provider to enable richer answers."
        )
    return {"answer": answer, "provider": "local-rules"}


@app.post("/api/alerts/test", dependencies=[Depends(require_api_access)])
def test_alert(payload: dict):
    provider = str(payload.get("provider", "")).strip().lower()
    webhook_url = str(payload.get("webhook_url", "")).strip()
    message = str(payload.get("message", "Cloud Cost Copilot test alert")).strip()
    try:
        send_alert(provider, webhook_url, message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AlertDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "sent", "provider": provider}


@app.get("/update-metrics", dependencies=[Depends(require_api_access)])
def manual_update():
    update_metrics()
    return {"status": "updated"}


@app.get("/metrics", dependencies=[Depends(require_api_access)])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/suggestions", dependencies=[Depends(require_api_access)])
def suggestions():
    return {"suggestions": get_all_suggestions(total_cost_history)}


@app.get("/idle-report", dependencies=[Depends(require_api_access)])
def idle_report():
    report = get_idle_confidence_report()
    idle_instances = [r for r in report if r.get("overall_idle_likely")]
    return {
        "total_instances_tracked": len(report),
        "idle_instances_count": len(idle_instances),
        "idle_instances": idle_instances,
        "all_instances": report,
    }


@app.get("/forecast", dependencies=[Depends(require_api_access)])
def forecast():
    predicted_monthly, daily_predictions = predict_future_cost(30)
    return {
        "predicted_monthly_cost": predicted_monthly,
        "trend": get_trend(),
        "daily_predictions": daily_predictions[-7:] if daily_predictions else []
    }


