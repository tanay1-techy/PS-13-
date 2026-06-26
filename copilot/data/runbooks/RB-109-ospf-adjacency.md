# RB-109: OSPF Neighbor Adjacency Failure

## Classification: RESTRICTED
## Applicable Devices: Router, Switch (Layer 3)
## Fault Category: Routing Protocol

### Symptoms
- OSPF neighbor stuck in INIT or 2-WAY state
- Routes learned via OSPF disappearing from routing table
- Asymmetric routing causing traffic blackholes
- Syslog: `OSPF: Neighbor X.X.X.X on interface Y changed state to DOWN`

### Diagnosis Steps
1. **Check OSPF neighbor table**: `show ip ospf neighbor` to see current state of all adjacencies.
2. **Verify OSPF configuration**: Confirm area ID, hello/dead timers, network type, and authentication match on both sides.
3. **Check MTU**: OSPF will not form adjacency if MTU mismatches exist on the link. Verify with `show interface` and compare both ends.
4. **Review access lists**: Ensure OSPF multicast (224.0.0.5, 224.0.0.6) is not being blocked by interface ACLs or firewall rules.
5. **Check interface state**: The underlying interface must be UP/UP for OSPF to work. Check for physical layer issues (see RB-102).

### Remediation
1. **Timer mismatch**: Ensure hello and dead timers match: `ip ospf hello-interval 10` and `ip ospf dead-interval 40` (default).
2. **MTU fix**: Set matching MTU on both ends or use `ip ospf mtu-ignore` as a temporary workaround.
3. **Area mismatch**: Correct the area assignment on the misconfigured side.
4. **Authentication**: If authentication is enabled, verify the key and key-id match. Re-key if necessary.
5. **Restart OSPF process**: As a last resort, `clear ip ospf process` (causes momentary traffic disruption).

### Escalation
If adjacency cannot be established after configuration verification, collect OSPF debug output (`debug ip ospf adj`) and escalate to Routing Engineering team.

---
