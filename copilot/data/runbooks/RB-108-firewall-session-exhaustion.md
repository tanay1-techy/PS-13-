# RB-108: Firewall Session Table Exhaustion

## Classification: CONFIDENTIAL
## Applicable Devices: Firewall
## Fault Category: Security / Resource Exhaustion

### Symptoms
- New connections being dropped by the firewall
- Session table utilization exceeding 80%
- Syslog: `FW: Session table approaching limit — N/M sessions active`
- Legitimate traffic being denied while existing sessions remain active

### Diagnosis Steps
1. **Check session table utilization**: Run `show session info` (Palo Alto) or `get session info` (Fortinet) to see current session count vs maximum.
2. **Identify session consumers**: Run `show session all filter sort-by byte` to find the top sessions by traffic volume or duration.
3. **Check for DDoS/scanning**: Look for a single source IP creating thousands of sessions — indicative of a scan or DDoS attack.
4. **Review session timeouts**: Excessively long TCP/UDP timeouts can cause stale sessions to accumulate. Check `show session timeout-settings`.
5. **Verify NAT pool**: If source NAT is in use, check if NAT address exhaustion is contributing to session buildup.

### Remediation
1. **Immediate (attack)**: If a DDoS/scan is identified, create a block rule for the offending source IPs or enable DoS protection profiles.
2. **Session timeout tuning**: Reduce idle timeouts for non-critical traffic:
   - TCP: 1800s → 600s for general traffic
   - UDP: 120s → 30s for DNS
   - ICMP: 6s (default is usually fine)
3. **Session table expansion**: If the hardware supports it, increase the maximum session table size.
4. **Aggressive aging**: Enable aggressive session aging when table utilization exceeds 80%.
5. **Preventive**: Set up capacity monitoring alerts at 60%, 80%, and 95% session table utilization.

### Escalation
If session exhaustion is caused by a sustained DDoS attack, activate the incident response plan and engage the Security Operations Center (SOC).

---
