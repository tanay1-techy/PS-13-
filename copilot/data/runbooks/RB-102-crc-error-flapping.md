# RB-102: Interface CRC Error Flapping

## Classification: UNCLASSIFIED
## Applicable Devices: Router, Switch
## Fault Category: Link Integrity

### Symptoms
- Rising CRC error counters on one or more interfaces
- Interface cycling between UP and DOWN states (link flapping)
- Intermittent packet loss on affected circuits
- Syslog messages: `INTERFACE: GigabitEthernet0/X CRC errors: N in last 60s`

### Diagnosis Steps
1. **Check error counters**: Run `show interface GigabitEthernetX/Y` and note CRC, input errors, runts, and giants counters. Record values and re-check after 5 minutes to confirm active growth.
2. **Inspect physical layer**: CRC errors typically indicate Layer 1 problems:
   - Damaged or kinked fiber/copper cable
   - Dirty or misaligned SFP/GBIC transceivers
   - Excessive cable length beyond specification
   - Electromagnetic interference (EMI) from adjacent power cables
3. **Check SFP diagnostics**: Run `show interface transceiver` to review optical power levels (Tx/Rx dBm). Acceptable range is typically -1 to -10 dBm for short-range SFPs.
4. **Review recent changes**: Check change log for recent cable moves, SFP replacements, or adjacent construction work.
5. **Test with known-good cable/SFP**: Swap the cable and/or transceiver module with verified working spares to isolate the component.

### Remediation
1. **Immediate**: If link is flapping, apply `dampening 5 1000 2000 20` on the interface to suppress rapid state changes and protect routing stability.
2. **Cable replacement**: If CRC errors correlate with cable degradation, replace the patch cable and cross-connect. Use certified Cat6A or single-mode fiber as appropriate.
3. **SFP replacement**: If transceiver power levels are outside specification, replace the SFP module. Use vendor-approved optics only.
4. **Clean connectors**: For fiber connections, clean both ends with IPA wipes and inspect with a fiber scope before reconnecting.
5. **EMI mitigation**: If interference is suspected, reroute cables away from power runs and use shielded cabling.

### Escalation
If errors persist after cable and SFP replacement, escalate to Physical Infrastructure team for end-to-end fiber/copper testing with OTDR/cable analyzer.

---
