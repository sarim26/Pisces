# Server issues (in-house)

Keywords: server, hung, hanged, hang, not working, down, reboot, crash, offline

These servers are on-premise (in-house). Do not tell the user to use a public cloud console.

## Symptom: Server hung / not responding / not working
1. Ask for the server hostname or IP and when it last worked.
2. Check if other users are affected (one PC vs whole office).
3. Technician checks:
   - Ping the server
   - Console/iLO/iDRAC access if ping fails
   - CPU, RAM, disk, event logs if the OS is still up
4. If the OS is hung: attempt a graceful restart from console; if that fails, controlled power cycle.
5. After restart, confirm services (file share, application, database) are running.

## Safety
- Do not power-cycle a production database server without a technician.
- Do not delete files or run disk repairs from the bot.

Escalate immediately if multiple services are down, the server will not boot, disk/RAID errors are reported, or the issue is after hours and business-critical.
