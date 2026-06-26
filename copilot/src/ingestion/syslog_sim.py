"""
Syslog Simulator
Generates RFC 5424-style syslog messages with controllable severity distribution.
Injects correlated pre-failure log bursts (e.g., rising CRC errors, link flaps)
that align with SNMP degradation windows for cross-modal anomaly correlation.
"""

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.config import simulator_cfg, get_path


# ── RFC 5424 severity levels ──
SEVERITIES = {
    0: "EMERG",
    1: "ALERT",
    2: "CRIT",
    3: "ERROR",
    4: "WARNING",
    5: "NOTICE",
    6: "INFO",
    7: "DEBUG",
}

# ── Normal operational log templates ──
NORMAL_TEMPLATES = {
    "router": [
        ("{device} BGP: Neighbor {peer_ip} session established (AS {asn})", 6),
        ("{device} OSPF: SPF calculation completed, {routes} routes updated", 6),
        ("{device} INTERFACE: {iface} link-state UP, speed 10Gbps", 5),
        ("{device} NTP: Clock synchronized to stratum-2 source {ntp_src}", 6),
        ("{device} CONFIG: Configuration saved by admin via SSH", 5),
    ],
    "switch": [
        ("{device} STP: Root bridge election completed for VLAN {vlan}", 6),
        ("{device} MAC: Learned {mac} on port {port}", 7),
        ("{device} LACP: Port-channel {pc} member {iface} bundled", 6),
        ("{device} VLAN: {vlan} state active, {ports} ports assigned", 6),
    ],
    "server": [
        ("{device} KERNEL: Memory pressure normalized, swap usage {swap}%", 6),
        ("{device} SSHD: Accepted publickey for admin from {src_ip}", 6),
        ("{device} SYSTEMD: Service {service} started successfully", 6),
        ("{device} CRON: Job {job} completed in {duration}s", 6),
    ],
    "firewall": [
        ("{device} FW: Session established src={src_ip} dst={dst_ip} proto=TCP/{port}", 6),
        ("{device} IPS: Signature update applied, {sigs} signatures active", 5),
        ("{device} HA: Heartbeat received from peer, state ACTIVE-ACTIVE", 6),
    ],
}

# ── Pre-failure log templates (correlated with SNMP degradation) ──
FAILURE_TEMPLATES = {
    "hardware_degradation": [
        ("{device} HARDWARE: DIMM slot {slot} correctable ECC error count: {count}", 3),
        ("{device} HARDWARE: PSU {psu} voltage fluctuation detected: {voltage}V", 4),
        ("{device} DIAG: Self-test warning on module {module}", 4),
    ],
    "link_flapping": [
        ("{device} INTERFACE: {iface} link-state DOWN", 3),
        ("{device} INTERFACE: {iface} link-state UP (flap count: {flap_count})", 4),
        ("{device} INTERFACE: {iface} CRC errors: {crc_count} in last 60s", 4),
        ("{device} INTERFACE: {iface} input errors incrementing: {err_count}/min", 3),
    ],
    "memory_leak": [
        ("{device} KERNEL: Out-of-memory score adjusted for PID {pid}: {score}", 4),
        ("{device} PROC: Process {proc} RSS growing: {mem_mb}MB (limit {limit_mb}MB)", 4),
        ("{device} KERNEL: Slab cache pressure increasing, reclaim triggered", 3),
    ],
    "thermal_throttling": [
        ("{device} ENVMON: Temperature sensor {sensor}: {temp}°C (warning threshold: 70°C)", 4),
        ("{device} ENVMON: Fan {fan} RPM below minimum: {rpm}", 3),
        ("{device} ENVMON: CPU frequency throttled to {freq}GHz due to thermal limit", 2),
    ],
    "interface_errors": [
        ("{device} INTERFACE: {iface} output drops: {drops}/sec", 4),
        ("{device} INTERFACE: {iface} collision rate exceeding threshold: {collisions}/s", 3),
        ("{device} QOS: Queue {queue} tail-drops: {drops} packets", 4),
        ("{device} INTERFACE: {iface} duplex mismatch detected", 3),
    ],
}


def _fill_template(template: str, device_id: str, rng: random.Random) -> str:
    """Fill a log template with random realistic values."""
    replacements = {
        "{device}": device_id,
        "{peer_ip}": f"10.{rng.randint(1,254)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
        "{src_ip}": f"10.{rng.randint(1,254)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
        "{dst_ip}": f"10.{rng.randint(1,254)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
        "{ntp_src}": f"ntp{rng.randint(1,4)}.internal",
        "{asn}": str(rng.randint(64512, 65534)),
        "{routes}": str(rng.randint(100, 5000)),
        "{iface}": f"GigabitEthernet0/{rng.randint(0,47)}",
        "{vlan}": str(rng.randint(10, 4094)),
        "{mac}": ":".join(f"{rng.randint(0,255):02x}" for _ in range(6)),
        "{port}": str(rng.randint(1, 48)),
        "{ports}": str(rng.randint(2, 48)),
        "{pc}": str(rng.randint(1, 8)),
        "{swap}": str(rng.randint(0, 30)),
        "{service}": rng.choice(["nginx", "prometheus", "telegraf", "snmpd"]),
        "{job}": rng.choice(["backup-daily", "log-rotate", "metric-export"]),
        "{duration}": str(rng.randint(1, 120)),
        "{sigs}": str(rng.randint(5000, 30000)),
        "{slot}": str(rng.randint(0, 7)),
        "{count}": str(rng.randint(50, 500)),
        "{psu}": str(rng.randint(1, 2)),
        "{voltage}": f"{rng.uniform(11.5, 12.5):.1f}",
        "{module}": str(rng.randint(1, 4)),
        "{flap_count}": str(rng.randint(5, 50)),
        "{crc_count}": str(rng.randint(100, 10000)),
        "{err_count}": str(rng.randint(50, 5000)),
        "{pid}": str(rng.randint(1000, 65000)),
        "{score}": str(rng.randint(500, 950)),
        "{proc}": rng.choice(["java", "python3", "telegraf", "snmpd"]),
        "{mem_mb}": str(rng.randint(500, 8000)),
        "{limit_mb}": str(rng.randint(4000, 16000)),
        "{sensor}": str(rng.randint(1, 4)),
        "{temp}": str(rng.randint(65, 90)),
        "{fan}": str(rng.randint(1, 6)),
        "{rpm}": str(rng.randint(1000, 3000)),
        "{freq}": f"{rng.uniform(1.0, 2.5):.1f}",
        "{drops}": str(rng.randint(100, 10000)),
        "{collisions}": str(rng.randint(50, 500)),
        "{queue}": str(rng.randint(0, 7)),
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result


def generate_syslog_data(
    devices: Dict[str, Dict[str, Any]],
    failure_events: List[Dict[str, Any]],
    start_time: Optional[datetime] = None,
    duration_hours: Optional[int] = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate syslog messages for all devices.
    Normal logs follow a realistic rate; pre-failure windows get burst patterns.
    """
    cfg = simulator_cfg()
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=cfg.get("history_hours", 24))
    if duration_hours is None:
        duration_hours = cfg.get("history_hours", 24)

    rng = random.Random(seed)
    end_time = start_time + timedelta(hours=duration_hours)

    # Build failure lookup
    failure_lookup: Dict[str, List[Dict]] = {}
    for evt in failure_events:
        did = evt["device_id"]
        if did not in failure_lookup:
            failure_lookup[did] = []
        failure_lookup[did].append(evt)

    records = []

    for device_id, device_meta in devices.items():
        device_type = device_meta.get("type", "server")
        normal_templates = NORMAL_TEMPLATES.get(device_type, NORMAL_TEMPLATES["server"])
        device_failures = failure_lookup.get(device_id, [])

        # Normal log rate: ~1-3 logs per minute
        current = start_time
        while current < end_time:
            # Check if we're in a failure window for any event
            in_failure_window = False
            active_fault = None
            for evt in device_failures:
                ft = evt["failure_timestamp"]
                pre_window = evt["pre_failure_window_min"]
                window_start = ft - timedelta(minutes=pre_window)
                if window_start <= current <= ft:
                    in_failure_window = True
                    active_fault = evt
                    break

            if in_failure_window and active_fault:
                # Generate burst of failure-related logs
                fault_type = active_fault["fault_type"]
                ft_templates = FAILURE_TEMPLATES.get(fault_type, FAILURE_TEMPLATES["interface_errors"])

                # Burst rate increases as we approach failure
                ft = active_fault["failure_timestamp"]
                pre_window = active_fault["pre_failure_window_min"]
                window_start = ft - timedelta(minutes=pre_window)
                progress = (current - window_start).total_seconds() / (pre_window * 60)

                # More logs as failure approaches: 2-10 per minute
                burst_rate = int(2 + 8 * progress)
                for _ in range(burst_rate):
                    template, severity = rng.choice(ft_templates)
                    # Escalate severity as failure approaches
                    if progress > 0.8:
                        severity = max(severity - 1, 1)
                    msg = _fill_template(template, device_id, rng)
                    ts = current + timedelta(seconds=rng.randint(0, 55))
                    records.append({
                        "timestamp": ts,
                        "device_id": device_id,
                        "severity": severity,
                        "severity_name": SEVERITIES.get(severity, "UNKNOWN"),
                        "message": msg,
                        "facility": "local0",
                        "is_failure_related": True,
                        "fault_type": fault_type,
                    })

                # Also mix in some normal logs
                if rng.random() < 0.3:
                    template, severity = rng.choice(normal_templates)
                    msg = _fill_template(template, device_id, rng)
                    records.append({
                        "timestamp": current + timedelta(seconds=rng.randint(0, 55)),
                        "device_id": device_id,
                        "severity": severity,
                        "severity_name": SEVERITIES.get(severity, "UNKNOWN"),
                        "message": msg,
                        "facility": "local0",
                        "is_failure_related": False,
                        "fault_type": None,
                    })
            else:
                # Normal operation: 1-3 logs per minute
                num_logs = rng.randint(1, 3)
                for _ in range(num_logs):
                    template, severity = rng.choice(normal_templates)
                    msg = _fill_template(template, device_id, rng)
                    records.append({
                        "timestamp": current + timedelta(seconds=rng.randint(0, 55)),
                        "device_id": device_id,
                        "severity": severity,
                        "severity_name": SEVERITIES.get(severity, "UNKNOWN"),
                        "message": msg,
                        "facility": "local0",
                        "is_failure_related": False,
                        "fault_type": None,
                    })

            # Advance by ~1 minute
            current += timedelta(seconds=rng.randint(50, 70))

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def save_syslog_to_sqlite(df: pd.DataFrame, db_path: Optional[Path] = None):
    """Save syslog DataFrame to SQLite."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    df_copy = df.copy()
    df_copy["timestamp"] = df_copy["timestamp"].astype(str)
    df_to_save = df_copy
    df_to_save.to_sql("syslog", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syslog_device_ts ON syslog(device_id, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syslog_severity ON syslog(severity)")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    from src.utils.config import ensure_dirs
    from src.ingestion.topology_sim import generate_topology
    from src.ingestion.snmp_sim import plan_failure_events
    ensure_dirs()

    _, devices = generate_topology()
    device_ids = list(devices.keys())
    start = datetime.now() - timedelta(hours=24)

    events = plan_failure_events(device_ids, start, 24)
    df = generate_syslog_data(devices, events, start_time=start, duration_hours=24)
    save_syslog_to_sqlite(df)
    print(f"✅ Generated {len(df)} syslog entries → SQLite")
    print(f"   Severity distribution:")
    for sev, name in SEVERITIES.items():
        count = len(df[df["severity"] == sev])
        if count > 0:
            print(f"   {name}: {count}")
