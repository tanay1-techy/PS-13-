# RB-103: Memory Leak Detection and Mitigation

## Classification: RESTRICTED
## Applicable Devices: Server, Router, Switch
## Fault Category: Resource Exhaustion

### Symptoms
- Steadily increasing memory usage without corresponding workload increase
- Process RSS (Resident Set Size) growing over time
- OOM (Out-of-Memory) killer events in kernel logs
- Degraded application response times
- Syslog: `KERNEL: Out-of-memory score adjusted for PID XXXX`

### Diagnosis Steps
1. **Identify leaking process**: Run `top -o %MEM` or `ps aux --sort=-%mem | head -20` to find processes with abnormally high memory usage.
2. **Track memory growth**: Use `pidstat -r -p <PID> 60 10` to sample memory usage every 60 seconds for 10 iterations. A consistently increasing RSS confirms a leak.
3. **Check system-wide memory**: Run `free -h` and `cat /proc/meminfo` to assess total/available/swap usage.
4. **Review application logs**: Check the suspect process's log files for memory allocation warnings or buffer growth messages.
5. **Inspect slab cache**: Run `slabtop` to check if kernel slab allocations are growing (indicates kernel-level leak).

### Remediation
1. **Immediate (if critical)**: Restart the affected service: `systemctl restart <service-name>`. This reclaims leaked memory but is a temporary fix.
2. **Short-term**: Set memory cgroup limits to prevent a single process from exhausting system memory: `systemctl set-property <service>.service MemoryMax=4G`
3. **Medium-term**: Report the leak to the application development team with evidence (PID, RSS growth timeline, heap dumps if available).
4. **Preventive**:
   - Configure OOM score adjustments to protect critical processes: `echo -1000 > /proc/<PID>/oom_score_adj`
   - Set up automated monitoring alerts when RSS exceeds 80% of limit
   - Schedule periodic service restarts during maintenance windows if no fix is available

### Escalation
If memory leak is in a vendor-provided application, open a support case with memory growth evidence. If in-house, escalate to Application Engineering with heap dump attached.

---
