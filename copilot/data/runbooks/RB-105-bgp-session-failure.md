# RB-105: BGP Session Failure and Recovery

## Classification: RESTRICTED
## Applicable Devices: Router
## Fault Category: Routing Protocol

### Symptoms
- BGP neighbor state changed from Established to Idle/Active
- Route withdrawal causing traffic blackholing
- Syslog: `BGP: Neighbor X.X.X.X session RESET by peer`
- Increased latency or unreachability to downstream networks

### Diagnosis Steps
1. **Check BGP neighbor status**: Run `show bgp summary` to identify which peers are down and their uptime/state.
2. **Review hold-timer expiry**: If the session dropped due to hold-timer expiry, check for CPU overload or interface issues preventing keepalive exchange.
3. **Verify TCP connectivity**: Ping the peer's BGP source address. Traceroute to confirm the path is intact.
4. **Check for prefix limit exceeded**: `show bgp neighbor X.X.X.X` — if max-prefix limit was hit, the session was administratively shut down.
5. **Review route policy changes**: Recent route-map or prefix-list modifications may have caused the peer to reset.
6. **Check authentication**: If MD5 authentication is configured, verify keys match on both sides.

### Remediation
1. **Immediate**: If prefix-limit was exceeded, increase the limit or apply more specific filters: `neighbor X.X.X.X maximum-prefix <new-limit> warning-only`
2. **Session reset**: Clear the BGP session: `clear bgp neighbor X.X.X.X soft` (soft reset preferred to avoid route churn).
3. **Authentication mismatch**: Coordinate with the peer operator to verify and re-sync MD5 keys.
4. **TCP path failure**: If the underlying path is broken, engage the transport/MPLS team to restore connectivity.
5. **Preventive**: Enable BFD (Bidirectional Forwarding Detection) for sub-second failure detection: `neighbor X.X.X.X fall-over bfd`

### Escalation
If BGP session cannot be re-established after basic troubleshooting, engage the peering team and the remote AS operator.

---
