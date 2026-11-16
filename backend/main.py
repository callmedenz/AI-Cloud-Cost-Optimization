# AI-assisted Cloud Cost Optimizer backend (human-built with AI assistance)
# Main FastAPI service exposing Prometheus metrics + optimization endpoints.
from fastapi import FastAPI
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
import threading
import time
import random
from datetime import datetime

# Create FastAPI app
app = FastAPI()

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


def _runtime_mode():
    simulation = use_simulation_mode()
    aws_ok = is_aws_configured()
    if simulation:
        return "simulation"
    if aws_ok:
        return "aws_live"
    return "fallback"


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
    instances = get_ec2_instances()
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
@app.get("/")
def root():
    mode = _runtime_mode()
    return {
        "name": "AI-Assisted Cloud Cost Optimizer",
        "version": "1.0.0",
        "mode": mode,
        "aws_status": "Connected" if mode == "aws_live" else ("Simulation Mode" if mode == "simulation" else "Fallback Mode"),
    }


@app.get("/status")
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


@app.get("/update-metrics")
def manual_update():
    update_metrics()
    return {"status": "updated"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/suggestions")
def suggestions():
    return {"suggestions": get_all_suggestions(total_cost_history)}


@app.get("/idle-report")
def idle_report():
    report = get_idle_confidence_report()
    idle_instances = [r for r in report if r.get("overall_idle_likely")]
    return {
        "total_instances_tracked": len(report),
        "idle_instances_count": len(idle_instances),
        "idle_instances": idle_instances,
        "all_instances": report,
    }


@app.get("/forecast")
def forecast():
    predicted_monthly, daily_predictions = predict_future_cost(30)
    return {
        "predicted_monthly_cost": predicted_monthly,
        "trend": get_trend(),
        "daily_predictions": daily_predictions[-7:] if daily_predictions else []
    }


