# RB-106: Packet Loss and Network Congestion

## Classification: UNCLASSIFIED
## Applicable Devices: Router, Switch, Firewall
## Fault Category: Performance Degradation

### Symptoms
- Packet loss exceeding 1% on monitored interfaces
- QoS queue tail-drops or WRED drops increasing
- Application latency complaints from end users
- SNMP: rising `ifOutDiscards` or `ifOutErrors` counters

### Diagnosis Steps
1. **Identify congested interfaces**: Run `show interface` and check for output drops, queue drops, and utilization percentage. An interface consistently above 80% utilization is congested.
2. **Check QoS policy**: Run `show policy-map interface` to see per-class traffic statistics. Identify which traffic class is experiencing drops.
3. **Review traffic patterns**: Use NetFlow or sFlow data to identify top talkers and unexpected traffic spikes.
4. **Check for broadcast storms**: Look for excessive broadcast/multicast traffic: `show interface counters broadcast`.
5. **Verify MTU settings**: MTU mismatches cause fragmentation and increased drop rates. Confirm end-to-end MTU consistency.

### Remediation
1. **Immediate**: Identify and rate-limit offending traffic flows using ACLs or QoS policers.
2. **QoS tuning**: Adjust bandwidth allocations in the QoS policy to prioritize mission-critical traffic (voice, telemetry, control-plane).
3. **Capacity augmentation**: If sustained congestion, engage capacity planning for link upgrade or LAG expansion.
4. **Broadcast storm control**: Enable storm-control on access ports: `storm-control broadcast level 5.00 1.00`
5. **ECMP/load balancing**: Distribute traffic across multiple equal-cost paths if available.

### Escalation
If packet loss persists after QoS remediation, escalate to Network Architecture team for capacity planning review.

---
