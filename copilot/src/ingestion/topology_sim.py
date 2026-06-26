"""
Network Topology Simulator
Generates a realistic hierarchical network graph (routers → switches → servers/firewalls)
with device metadata, persists as JSON for consumption by downstream components.
"""

import json
import random
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from src.utils.config import simulator_cfg, get_path, project_root


# ── Device templates ──

DEVICE_TEMPLATES = {
    "router": {
        "icon": "🔀",
        "vendor": ["Cisco", "Juniper", "Nokia"],
        "os": ["IOS-XR 7.9", "JunOS 23.2", "SR-OS 23.7"],
        "role": "core",
    },
    "switch": {
        "icon": "🔗",
        "vendor": ["Cisco", "Arista", "HPE"],
        "os": ["NX-OS 10.3", "EOS 4.31", "Comware 7.1"],
        "role": "distribution",
    },
    "server": {
        "icon": "🖥️",
        "vendor": ["Dell", "HPE", "Lenovo"],
        "os": ["RHEL 9.3", "Ubuntu 22.04 LTS", "Rocky 9.3"],
        "role": "compute",
    },
    "firewall": {
        "icon": "🛡️",
        "vendor": ["Palo Alto", "Fortinet", "Check Point"],
        "os": ["PAN-OS 11.1", "FortiOS 7.4", "R81.20"],
        "role": "security",
    },
}


def _generate_device_id(device_type: str, index: int) -> str:
    """Generate a deterministic, human-readable device ID."""
    prefix_map = {"router": "RTR", "switch": "SW", "server": "SRV", "firewall": "FW"}
    prefix = prefix_map.get(device_type, "DEV")
    return f"{prefix}-{index:03d}"


def _generate_ip(subnet_base: int, host: int) -> str:
    return f"10.{subnet_base}.{(host // 256) % 256}.{host % 256 + 1}"


def generate_topology(
    num_devices: Optional[int] = None,
    seed: int = 42,
) -> Tuple[nx.Graph, Dict[str, Dict[str, Any]]]:
    """
    Generate a hierarchical network topology.

    Returns:
        (graph, devices_dict)
        graph: networkx Graph with edges representing physical/logical links
        devices_dict: {device_id: {type, vendor, os, ip, role, location, ...}}
    """
    cfg = simulator_cfg()
    if num_devices is None:
        num_devices = cfg.get("num_devices", 20)
    device_types = cfg.get("device_types", ["router", "switch", "server", "firewall"])

    rng = random.Random(seed)

    # ── Allocate devices across types ──
    # Ratio: 15% routers, 25% switches, 50% servers, 10% firewalls
    type_ratios = {"router": 0.15, "switch": 0.25, "server": 0.50, "firewall": 0.10}
    allocation: Dict[str, int] = {}
    remaining = num_devices
    for dtype in device_types[:-1]:
        count = max(1, int(num_devices * type_ratios.get(dtype, 0.1)))
        allocation[dtype] = count
        remaining -= count
    allocation[device_types[-1]] = max(1, remaining)

    # ── Create devices ──
    devices: Dict[str, Dict[str, Any]] = {}
    type_lists: Dict[str, List[str]] = {t: [] for t in device_types}
    idx = 1
    locations = [
        "DC-North", "DC-South", "DC-East", "DC-West",
        "Ground-Station-A", "Ground-Station-B", "Mission-Control"
    ]

    for dtype, count in allocation.items():
        template = DEVICE_TEMPLATES.get(dtype, DEVICE_TEMPLATES["server"])
        for _ in range(count):
            dev_id = _generate_device_id(dtype, idx)
            devices[dev_id] = {
                "id": dev_id,
                "type": dtype,
                "icon": template["icon"],
                "vendor": rng.choice(template["vendor"]),
                "os": rng.choice(template["os"]),
                "ip": _generate_ip(rng.randint(1, 254), idx),
                "role": template["role"],
                "location": rng.choice(locations),
                "status": "healthy",
                "risk_score": 0.0,
            }
            type_lists[dtype].append(dev_id)
            idx += 1

    # ── Build hierarchical graph ──
    G = nx.Graph()
    for dev_id, meta in devices.items():
        G.add_node(dev_id, **meta)

    # Routers form a mesh core
    routers = type_lists.get("router", [])
    for i in range(len(routers)):
        for j in range(i + 1, len(routers)):
            if rng.random() < 0.7:
                G.add_edge(routers[i], routers[j], link_type="core", bandwidth_gbps=100)

    # Make sure router core is connected
    if routers and not nx.is_connected(G.subgraph(routers)):
        for i in range(len(routers) - 1):
            if not G.has_edge(routers[i], routers[i + 1]):
                G.add_edge(routers[i], routers[i + 1], link_type="core", bandwidth_gbps=100)

    # Firewalls connect to routers
    firewalls = type_lists.get("firewall", [])
    for fw in firewalls:
        target_router = rng.choice(routers) if routers else None
        if target_router:
            G.add_edge(fw, target_router, link_type="security", bandwidth_gbps=40)

    # Switches connect to routers (distribution layer)
    switches = type_lists.get("switch", [])
    for sw in switches:
        uplinks = rng.sample(routers, min(2, len(routers))) if routers else []
        for r in uplinks:
            G.add_edge(sw, r, link_type="distribution", bandwidth_gbps=40)

    # Servers connect to switches (access layer)
    servers = type_lists.get("server", [])
    for srv in servers:
        target_switch = rng.choice(switches) if switches else (rng.choice(routers) if routers else None)
        if target_switch:
            G.add_edge(srv, target_switch, link_type="access", bandwidth_gbps=10)
        # Some servers have redundant links
        if rng.random() < 0.3 and switches:
            alt_switch = rng.choice(switches)
            if alt_switch != target_switch:
                G.add_edge(srv, alt_switch, link_type="access_redundant", bandwidth_gbps=10)

    return G, devices


def save_topology(
    graph: nx.Graph,
    devices: Dict[str, Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Path:
    """Save topology to JSON file."""
    if output_dir is None:
        output_dir = get_path("paths.store_dir")
    output_dir.mkdir(parents=True, exist_ok=True)

    topology_data = {
        "devices": devices,
        "edges": [
            {
                "source": u,
                "target": v,
                **data,
            }
            for u, v, data in graph.edges(data=True)
        ],
        "summary": {
            "total_devices": len(devices),
            "total_links": graph.number_of_edges(),
            "device_type_counts": {},
        },
    }
    # Count by type
    for dev in devices.values():
        dtype = dev["type"]
        topology_data["summary"]["device_type_counts"][dtype] = (
            topology_data["summary"]["device_type_counts"].get(dtype, 0) + 1
        )

    out_path = output_dir / "topology.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(topology_data, f, indent=2)

    return out_path


def load_topology(store_dir: Optional[Path] = None) -> Tuple[nx.Graph, Dict[str, Dict[str, Any]]]:
    """Load topology from saved JSON."""
    if store_dir is None:
        store_dir = get_path("paths.store_dir")
    topo_path = store_dir / "topology.json"
    with open(topo_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    devices = data["devices"]
    G = nx.Graph()
    for dev_id, meta in devices.items():
        G.add_node(dev_id, **meta)
    for edge in data["edges"]:
        src = edge.pop("source")
        tgt = edge.pop("target")
        G.add_edge(src, tgt, **edge)

    return G, devices


if __name__ == "__main__":
    from src.utils.config import ensure_dirs
    ensure_dirs()
    G, devices = generate_topology()
    path = save_topology(G, devices)
    print(f"✅ Topology generated: {len(devices)} devices, {G.number_of_edges()} links")
    print(f"   Saved to: {path}")
    for dtype in ["router", "switch", "server", "firewall"]:
        count = sum(1 for d in devices.values() if d["type"] == dtype)
        print(f"   {dtype}: {count}")
