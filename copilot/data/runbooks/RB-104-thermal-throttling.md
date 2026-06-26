# RB-104: Thermal Throttling and Overheating

## Classification: UNCLASSIFIED
## Applicable Devices: Router, Switch, Server
## Fault Category: Environmental / Hardware

### Symptoms
- CPU frequency reduced below base clock (thermal throttling)
- Fan speed alarms or fan failure events
- Temperature sensor warnings exceeding 70°C threshold
- Syslog: `ENVMON: Temperature sensor X: Y°C (warning threshold: 70°C)`
- Degraded throughput despite low logical utilization

### Diagnosis Steps
1. **Check temperature sensors**: Run `show environment temperature` (network device) or `ipmitool sdr type temperature` (server) to get current readings from all sensors.
2. **Check fan status**: Run `show environment fan` or `ipmitool sdr type fan` to verify all fans are operational and at expected RPM.
3. **Review ambient conditions**: Check data center environmental monitoring (DCIM) for room temperature, hot/cold aisle containment breaches, or CRAC unit failures.
4. **Inspect airflow**: Verify that blanking panels are installed, no cable obstructions block airflow, and hot/cold aisles are properly contained.
5. **Check recent changes**: New high-density equipment installed nearby can create localized hot spots.

### Remediation
1. **Immediate (critical temp > 85°C)**: Reduce load on the device. Shift traffic to redundant paths if available. Consider controlled shutdown to prevent hardware damage.
2. **Fan failure**: Replace failed fan module. Most modern devices support hot-swap fan replacement. Keep spare fan modules in the data center inventory.
3. **Airflow correction**:
   - Install blanking panels in empty rack units
   - Verify hot/cold aisle containment is intact
   - Clear any cable obstructions from device intake/exhaust
4. **Ambient temperature**: Coordinate with Facilities to check CRAC/CRAH units. Temporary portable cooling may be needed for acute situations.
5. **Preventive**:
   - Set temperature warning threshold at 65°C and critical at 80°C
   - Implement automated load shedding when temperature exceeds warning threshold
   - Schedule quarterly thermal audits of the data center

### Escalation
If temperature cannot be reduced below warning threshold after airflow and fan remediation, escalate to Facilities Management and consider emergency workload migration.

---
