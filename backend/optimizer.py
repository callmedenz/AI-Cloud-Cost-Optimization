from datetime import datetime, timedelta, timezone

# save cpu history
instance_stats = {}

IDLE_CPU_THRESHOLD = 10.0
IDLE_CONFIDENCE_THRESHOLD = 0.80
CPU_RETENTION_DAYS = 8


def _utcnow():
    return datetime.now(timezone.utc)


def _to_utc(ts):
    if ts is None:
        return _utcnow()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


# function to update cpu list
def update_instance_stats(instance_id, cpu_usage, cost, timestamp=None):
    if instance_id not in instance_stats:
        instance_stats[instance_id] = {
            "cpu_history": [],
            "cost_history": [],
            "cpu_samples": [],
        }

    stats = instance_stats[instance_id]
    stats["cpu_history"].append(cpu_usage)
    stats["cost_history"].append(cost)
    stats["cpu_samples"].append({"ts": _to_utc(timestamp), "cpu": float(cpu_usage)})

    # Keep short rolling arrays for old behavior
    if len(stats["cpu_history"]) > 30:
        stats["cpu_history"] = stats["cpu_history"][-30:]
    if len(stats["cost_history"]) > 30:
        stats["cost_history"] = stats["cost_history"][-30:]

    # Retain up to ~8 days of timed samples so we can calculate 24h/7d windows.
    cutoff = _utcnow() - timedelta(days=CPU_RETENTION_DAYS)
    stats["cpu_samples"] = [s for s in stats["cpu_samples"] if s["ts"] >= cutoff]


def _window_report(samples, window_hours):
    now = _utcnow()
    cutoff = now - timedelta(hours=window_hours)
    in_window = [s for s in samples if s["ts"] >= cutoff]

    if not in_window:
        return {
            "window": f"{window_hours}h",
            "sample_count": 0,
            "coverage_hours": 0.0,
            "avg_cpu": None,
            "max_cpu": None,
            "idle_confidence": 0.0,
            "is_idle": False,
            "status": "collecting_data",
            "recommended_action": "Collect more data",
        }

    cpus = [s["cpu"] for s in in_window]
    idle_points = sum(1 for v in cpus if v <= IDLE_CPU_THRESHOLD)
    confidence = idle_points / len(cpus)
    coverage_hours = (in_window[-1]["ts"] - in_window[0]["ts"]).total_seconds() / 3600
    is_idle = confidence >= IDLE_CONFIDENCE_THRESHOLD

    if is_idle:
        action = "Right-size (smaller EC2) or schedule stop/start for non-prod hours"
        status = "idle_likely"
    else:
        action = "Keep current size and keep monitoring"
        status = "active_or_mixed"

    return {
        "window": f"{window_hours}h",
        "sample_count": len(cpus),
        "coverage_hours": round(max(0.0, coverage_hours), 2),
        "avg_cpu": round(sum(cpus) / len(cpus), 2),
        "max_cpu": round(max(cpus), 2),
        "idle_confidence": round(confidence, 3),
        "is_idle": is_idle,
        "status": status,
        "recommended_action": action,
    }


def get_idle_confidence_report():
    report = []
    for instance_id, stats in instance_stats.items():
        samples = stats.get("cpu_samples", [])
        if not samples:
            continue

        window_24h = _window_report(samples, 24)
        window_7d = _window_report(samples, 24 * 7)
        overall_idle = window_24h["is_idle"] or window_7d["is_idle"]

        report.append(
            {
                "instance_id": instance_id,
                "idle_24h": window_24h,
                "idle_7d": window_7d,
                "overall_idle_likely": overall_idle,
            }
        )
    return report


# Heuristic optimization suggestions based on CPU history
def analyze_instances():
    suggestions = []

    for instance_id, stats in instance_stats.items():
        cpu_history = stats["cpu_history"]

        if len(cpu_history) < 5:
            continue

        avg_cpu = sum(cpu_history) / len(cpu_history)

        # if low cpu, downsize it
        if avg_cpu < 10:
            suggestions.append(
                {
                    "instance_id": instance_id,
                    "type": "downsizing",
                    "message": f"Low CPU ({avg_cpu:.1f}%). Consider smaller instance.",
                    "savings": "30-50%",
                }
            )

        # check for high cpu spikes
        elif max(cpu_history) > 80:
            suggestions.append(
                {
                    "instance_id": instance_id,
                    "type": "investigate",
                    "message": f"High CPU spike ({max(cpu_history):.1f}%). Check for issues.",
                    "savings": "N/A",
                }
            )

        # if high cpu constantly, use reserved instance
        elif avg_cpu > 60:
            suggestions.append(
                {
                    "instance_id": instance_id,
                    "type": "reserved_instance",
                    "message": f"High CPU ({avg_cpu:.1f}%). Consider Reserved Instance.",
                    "savings": "20-40%",
                }
            )

    return suggestions


# return all of them
def get_all_suggestions(total_cost_history):
    return analyze_instances()
