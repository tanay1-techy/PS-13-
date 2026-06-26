# RB-101: High CPU Utilization on Network Devices

## Classification: RESTRICTED
## Applicable Devices: Router, Switch, Firewall
## Fault Category: Performance Degradation

### Symptoms
- CPU utilization consistently above 80% for more than 5 minutes
- Slow CLI response on the device
- Delayed routing protocol convergence
- SNMP timeout errors from monitoring systems

### Diagnosis Steps
1. **Identify the process consuming CPU**: Run `show processes cpu sorted` (Cisco) or `show system processes extensive` (Juniper) to identify the top CPU-consuming process.
2. **Check for control-plane floods**: Examine `show control-plane host open-ports` and look for unusually high packet rates hitting the CPU.
3. **Review BGP/OSPF activity**: A route flap storm can cause sustained CPU spikes. Check `show bgp summary` for high message counts or frequent state changes.
4. **Check for ACL logging**: Excessive ACL log entries can drive up CPU. Review `show access-lists` for counters on log-enabled entries.
5. **Inspect ARP/ND tables**: An ARP storm from a misconfigured host can overwhelm CPU. Check `show arp` for abnormal entry counts.

### Remediation
1. **Immediate**: Apply CoPP (Control Plane Policing) to rate-limit punted traffic: `policy-map control-plane-policy` with appropriate rate limits.
2. **Short-term**: If a specific process is the culprit (e.g., SNMP polling), adjust the polling interval or disable verbose SNMP walks.
3. **Medium-term**: Upgrade device firmware if a known CPU bug is identified. Check vendor advisory database.
4. **Preventive**: Set up SNMP traps for CPU thresholds at 70% (warning) and 85% (critical). Configure automated script to collect diagnostics when threshold is breached.

### Escalation
If CPU remains above 90% after CoPP and process remediation, escalate to Network Engineering L3 team with diagnostics bundle attached.

---
