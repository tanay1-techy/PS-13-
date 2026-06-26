# RB-110: Hardware Degradation and Predictive Failure

## Classification: RESTRICTED
## Applicable Devices: Router, Switch, Server, Firewall
## Fault Category: Hardware Failure (Predictive)

### Symptoms
- Correctable ECC memory errors increasing over time
- SMART disk warnings (for server devices)
- Intermittent module resets or line card reloads
- Syslog: `HARDWARE: DIMM slot X correctable ECC error count: N`
- Environmental sensors showing gradual drift from baseline

### Diagnosis Steps
1. **Check hardware diagnostics**: Run `show diagnostic result module all` (Cisco) or `ipmitool sel list` (server) for hardware event log entries.
2. **Review ECC error trend**: A slowly rising correctable ECC error count indicates DIMM degradation. Track the rate — more than 100 errors/day warrants preemptive replacement.
3. **Check disk health**: For servers, run `smartctl -a /dev/sdX` and review Reallocated Sector Count, Current Pending Sector, and Offline Uncorrectable counters.
4. **Module stability**: Review `show module` uptime for unexpected reloads or resets.
5. **Cross-reference with environmental data**: Hardware degradation can be accelerated by thermal stress (see RB-104).

### Remediation
1. **DIMM replacement**: If ECC error rate exceeds threshold, schedule DIMM replacement during the next maintenance window. Identify the exact DIMM slot from diagnostics.
2. **Disk replacement**: If SMART attributes indicate pending failure, initiate RAID rebuild with replacement disk before the drive fails completely.
3. **Module replacement**: If a line card is experiencing repeated resets, RMA (Return Merchandise Authorization) the module with the vendor.
4. **Proactive migration**: Before hardware replacement, migrate workloads/traffic to redundant paths to minimize service impact.
5. **Preventive**: Implement predictive failure monitoring that tracks degradation trends and alerts before critical threshold is reached (this co-pilot system).

### Escalation
For confirmed hardware degradation, open an RMA case with the hardware vendor. Include serial number, diagnostic output, and error rate timeline.

---
