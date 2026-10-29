# systemd and journald essentials

> **In one sentence:** On a Linux host without Kubernetes, systemd is what starts your service, restarts it, stops it cleanly and runs it on a schedule, and journald is where its stdout and stderr go, indexed by unit, time, priority and boot, so a unit file and `journalctl -u` replace the init script, the `nohup`, the `tail -f` and most of the cron jobs.

**Why it matters:** Not everything runs in a cluster: the bastion host, the batch box, the on-premise installation at a customer, the VM that runs the one service that was never containerised. On those machines, "the service died at 03:00 and nobody knows why" is answered by a `Restart=` line and `journalctl -u orders --since "02:50"`, and "the cron job ran twice and filled the disk" is prevented by a timer unit. Interviewers use systemd questions to see whether you can operate a service, not only write one.

## The idea

**Units.** systemd manages *units*: services (`.service`), timers (`.timer`), mount points, sockets, targets (groups such as `multi-user.target`). Unit files are INI-style text in `/usr/lib/systemd/system/` (installed by packages) or `/etc/systemd/system/` (yours, and overrides). A service unit has three sections: `[Unit]` for description and ordering (`After=`, `Wants=`, `Requires=`), `[Service]` for how to run it, `[Install]` for which target pulls it in at boot. After editing any unit file run `systemctl daemon-reload`, or systemd keeps using the old one.

**The `[Service]` lines that matter for a JVM.** `Type=simple` (the default) considers the service started as soon as the process is forked; `Type=notify` lets the application tell systemd when it is actually ready through the sd_notify protocol, which a plain JVM does not speak, so for a Spring Boot service `simple` is the honest choice and readiness is checked by the health endpoint, not by `systemctl start` returning. `User=` and `Group=` drop root. `EnvironmentFile=` loads `KEY=value` lines, which is where `JAVA_TOOL_OPTIONS` and secrets-by-file belong. `Restart=on-failure` restarts on a non-zero exit or a signal, `RestartSec=` is the delay, and `StartLimitIntervalSec=` and `StartLimitBurst=` in `[Unit]` stop a crash loop from spinning forever. `TimeoutStopSec=` is how long systemd waits after `SIGTERM` before `SIGKILL`; set it above Spring Boot's graceful shutdown period (item 4.6). `LimitNOFILE=` sets the file-descriptor limit (item 7.2).

**journald.** Anything the service writes to stdout or stderr is captured by journald with metadata: unit, PID, UID, priority, boot ID, timestamp. The journal is binary and indexed; `journalctl` is the reader. By default it is kept in `/run/log/journal/` and lost at reboot unless `/var/log/journal/` exists or `Storage=persistent` is set in `/etc/systemd/journald.conf`. Size is capped by `SystemMaxUse=` and age by `MaxRetentionSec=` in the same file; `journalctl --disk-usage` shows the current size and `journalctl --vacuum-size=` or `--vacuum-time=` trims it. Services that insist on writing their own files still need `logrotate`, configured by a file in `/etc/logrotate.d/`.

**Timers instead of cron.** A timer unit activates a service unit on a schedule (`OnCalendar=`) or relative to boot or last run (`OnBootSec=`, `OnUnitActiveSec=`). Compared with a crontab line: the job's output goes to the journal instead of mail; `Persistent=true` runs a missed job after the machine was off; `RandomizedDelaySec=` spreads load; the service unit gives it a user, resource limits and a timeout; `systemctl list-timers` shows the next and last runs. Cron still exists on every machine and a one-liner in `/etc/cron.d/` is fine for trivial jobs; anything that can fail, overlap or run long is better as a timer.

## Example: a Spring Boot service as a unit, with a nightly timer

`/etc/systemd/system/orders.service`:

```ini
[Unit]
Description=Orders service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=orders
Group=orders
WorkingDirectory=/opt/orders
EnvironmentFile=/etc/orders/orders.env
ExecStart=/usr/bin/java -jar /opt/orders/application.jar
Restart=on-failure
RestartSec=5s
TimeoutStopSec=45s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

1. `After=network-online.target` plus `Wants=network-online.target` delays the start until the network is configured; `After=` alone only orders, it does not pull the target in.
2. `StartLimitBurst=5` within `StartLimitIntervalSec=300`: more than five restarts in five minutes and systemd gives up, so a broken configuration does not hammer the database every five seconds all night.
3. `ExecStart` must be an absolute path and runs with no shell, so no `~`, no globbing, no pipes and no `&&`; only basic `${VARIABLE}` substitution from the unit's environment is done.
4. `TimeoutStopSec=45s` with `spring.lifecycle.timeout-per-shutdown-phase=30s` in the application gives the JVM time to finish in-flight requests before systemd sends `SIGKILL`.
5. `WantedBy=multi-user.target` is what `systemctl enable` reads to create the symlink that starts the unit at boot.

`/etc/orders/orders.env`, readable only by root and the `orders` user:

```text
JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=75 -Xlog:gc:file=/var/log/orders/gc.log
SPRING_PROFILES_ACTIVE=production
SPRING_DATASOURCE_PASSWORD=change-me
```

Installing, starting and reading the logs:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now orders
systemctl status orders
journalctl -u orders -f
journalctl -u orders --since "2026-10-29 02:50" --until "2026-10-29 03:10"
journalctl -u orders -p err -b
journalctl -u orders -o json-pretty -n 1
```

`status` shows whether the unit is active, its main PID, memory and CPU use, and the last few log lines. `-f` follows. `--since` and `--until` take timestamps or phrases like `"1 hour ago"`. `-p err` filters by priority (`emerg` through `debug`); `-b` restricts to the current boot, `-b -1` to the previous one, which is where the answer to "why did it die before the reboot" lives. `-o json-pretty` shows the metadata fields journald attached, which log shippers forward.

A nightly report as two units. `/etc/systemd/system/orders-report.service`:

```ini
[Unit]
Description=Nightly orders report

[Service]
Type=oneshot
User=orders
WorkingDirectory=/opt/orders
ExecStart=/opt/orders/bin/report.sh
```

`/etc/systemd/system/orders-report.timer`:

```ini
[Unit]
Description=Run the nightly orders report

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now orders-report.timer
systemctl list-timers orders-report.timer
systemd-analyze calendar "*-*-* 02:30:00"
sudo systemctl start orders-report.service
journalctl -u orders-report.service -n 50
```

`systemd-analyze calendar` prints when the expression fires next, which is the check to run before trusting a schedule. Starting the service unit by hand runs the job immediately with the same user and environment the timer would use. The equivalent crontab line, `30 2 * * * /opt/orders/bin/report.sh`, loses the journal, the missed-run catch-up and the user and limit settings, and if the script takes longer than a day two copies run at once; a oneshot service cannot start while a previous instance is still running.

Overrides without editing the installed file: `sudo systemctl edit orders` opens a drop-in at `/etc/systemd/system/orders.service.d/override.conf`, where a `[Service]` section with `Environment=JAVA_TOOL_OPTIONS=...` or a changed `TimeoutStopSec=` is merged over the original; `systemctl cat orders` shows the result.

## Pitfalls

- Editing a unit and wondering why nothing changed. `systemctl daemon-reload` is required after every edit; `systemctl status` warns about it, but only if you read the output.
- `Restart=always` on a service that exits deliberately. A batch job that finishes is restarted forever; use `on-failure`, and `oneshot` for jobs.
- A short `TimeoutStopSec` or the default `DefaultTimeoutStopSec` of 90 seconds combined with a slow shutdown. The JVM is killed mid-request, and the journal shows `Killing process ... with signal SIGKILL`.
- Logs to a file *and* `tail`-based habits. Logback writing to `/var/log/orders/app.log` without rotation fills the disk; writing to stdout gives rotation, indexing and shipping for free.
- A volatile journal. Without `/var/log/journal/` or `Storage=persistent`, every reboot deletes the evidence of why you rebooted.
- Running as root because the unit has no `User=`. Any file the application writes is root-owned and any vulnerability is a root shell.
- `ExecStart=/bin/sh -c "..."` to get shell features. It works, but the main PID is now the shell, signals go to the shell first, and `Type=simple` tracks the wrong process. Put the logic in a script and call it directly.
- Timer and cron for the same job. Both fire, both write, and the duplicated report is blamed on the application.

## Check yourself

1. A service crashes at boot because the database is not reachable yet, then works when started by hand a minute later. Which `[Unit]` and `[Service]` lines address this, and why is `After=` alone insufficient?
2. The on-call engineer needs every error logged by `orders` between 02:50 and 03:10 last night, and then everything the service logged during the boot before the last reboot. Write the two commands.
3. Explain what `Persistent=true` on a timer does, and give one job where you would want it and one where you would not.
4. A unit has `Restart=always`, `RestartSec=1s` and no start limit, and the configuration file is broken. Describe what the host looks like after ten minutes and what three lines you would change.

## Go deeper

- [Arch Wiki: systemd](https://wiki.archlinux.org/title/Systemd) · the best practical overview; unit basics, targets, drop-ins and the common commands.
- [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html) and [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html) · the authoritative reference for every `[Service]` directive used above.
- [journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html) and [journald.conf](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html) · filtering options and the storage and retention settings.
- [systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html) and [systemd.time](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html) · timer directives and the `OnCalendar` expression syntax.

---

Part of [DevOps & Delivery](../README.md) · item 7.3
