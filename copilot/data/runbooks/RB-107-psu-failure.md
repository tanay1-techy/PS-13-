# RB-107: Power Supply Unit (PSU) Failure

## Classification: UNCLASSIFIED
## Applicable Devices: Router, Switch, Server, Firewall
## Fault Category: Hardware Failure

### Symptoms
- PSU status alarm (amber LED on chassis)
- Voltage fluctuation alerts from environmental monitoring
- Syslog: `HARDWARE: PSU X voltage fluctuation detected`
- Redundant PSU taking full load (single point of failure condition)

### Diagnosis Steps
1. **Check PSU status**: Run `show environment power` or `ipmitool sdr type voltage` to identify which PSU is failed/degraded.
2. **Verify load distribution**: Confirm whether the remaining PSU can handle the full chassis load. Check power budget vs actual draw.
3. **Inspect physical indicators**: Check PSU LED status on the chassis (green = OK, amber = warning, red = failure).
4. **Review power circuit**: Verify the power feed (UPS, PDU) for the failed PSU is operational. Check for tripped breakers.
5. **Check event history**: Review `show environment power history` for intermittent failures that may indicate a developing fault.

### Remediation
1. **Immediate**: If only one PSU remains, declare a maintenance risk and schedule emergency replacement. Do NOT perform any other maintenance on the device until redundancy is restored.
2. **PSU replacement**: Hot-swap the failed PSU module (most enterprise devices support hot-swap). Use exact-match replacement part.
3. **Power circuit**: If the PSU is operational but voltage is fluctuating, check the PDU output and UPS status. Relocate to a different power circuit if needed.
4. **Preventive**: Maintain spare PSU inventory per device model. Set up SNMP traps for PSU state changes.

### Escalation
If replacement PSU also fails, suspect a backplane power distribution issue and escalate to Hardware Engineering with full environmental data.

---
