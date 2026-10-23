# Linux essentials for developers: permissions, processes, pipes

> **In one sentence:** Linux is files, processes and text streams: every file has an owner, a group and nine permission bits; every process has a PID, a parent, three standard streams and an exit code, and is told things with signals; and the shell exists to wire the streams of small programs together.

**Why it matters:** Deploys fail at 2 a.m. with `Permission denied`; a runbook's `kill -9` drops in-flight requests that `kill -TERM` would have finished; a CI step passes because the exit code of a pipeline was `tee`'s and not the build's; and the engineer who can answer "which client is hammering us" from a log in thirty seconds goes back to bed first.

## The idea

**Permissions (item 5.1).** `ls -l` prints the whole model in one line:

```text
-rw-r--r--  1 armaan  staff  231 Oct 24 00:34 access.log
│├─┤├─┤├─┤    ├────┤  ├───┤  ├─┤ ├──────────┤ ├────────┤
│ │  │  │     owner   group  size  modified   name
│ │  │  └── others: read
│ │  └───── group:  read
│ └──────── owner:  read, write
└────────── type: - file, d directory, l symlink
```

Read, write and execute for owner, group and others; in octal r=4, w=2, x=1, so `644` is the line above, `755` an executable or a directory, `600` a private key. On a directory, `x` means "may enter and resolve names", `r` "may list", and `w` "may create, rename and delete entries", which is why deleting a file depends on the directory's permissions, not the file's. `chmod u+x deploy.sh`, `chmod 600 ~/.ssh/id_ed25519`, `chown -R app:app /var/lib/app`. `sudo` runs one command as root and logs who did it; services should run as an unprivileged user, and binding a port below 1024 needs root or `CAP_NET_BIND_SERVICE`. Directories that matter: `/etc` configuration, `/var/log` logs, `/var/lib` service state, `/proc` the kernel's view of processes as files.

**Processes, signals, exit codes (item 5.2).** Every process has a PID, a parent, a user, a working directory and a set of open file descriptors; `ps aux`, `ps -ef --forest`, `pgrep -af java` and `top` or `htop` show them. You talk to a process with signals. `SIGTERM` (15) is the polite request to stop and the default for `kill`: a JVM runs its shutdown hooks, Spring stops accepting requests and finishes the ones in flight. `SIGKILL` (9) cannot be caught: the kernel removes the process with no cleanup; it is what the OOM killer sends and what `docker stop` and Kubernetes fall back to after their grace period. `SIGINT` (2) is Ctrl-C. `SIGHUP` (1) is "your terminal went away" and the reason background jobs die when an SSH session closes (`nohup`, `tmux` or a systemd unit fix that).

Every process ends with an exit code, readable as `$?`. `0` is success; anything else is failure. Conventions: `1` general error, `2` wrong usage, `126` not executable, `127` command not found, and `128 + N` when killed by signal N, so `130` is Ctrl-C, `137` is `SIGKILL` (in a container, almost always the OOM killer) and `143` is `SIGTERM`.

**Pipes and redirection (item 5.3).** A process starts with three open streams: `0` stdin, `1` stdout, `2` stderr. `>` sends stdout to a file (truncating), `>>` appends, `2>` redirects stderr, `2>&1` sends stderr wherever stdout currently goes, `< file` feeds stdin, and `|` connects one process's stdout to the next one's stdin. stderr is not part of the pipe, so error messages still reach your terminal from the middle of a pipeline. Order matters: `cmd > out.log 2>&1` captures both streams, `cmd 2>&1 > out.log` sends stderr to the terminal. A pipeline's exit code is the last command's unless `set -o pipefail` is on. Everything is lines of text, and a dozen small tools turn lines into answers:

| Command | A real use |
|---|---|
| `ls -la` | see who owns the deploy directory and why the app cannot write to it |
| `grep -rn "OutOfMemoryError" /var/log/app/` | every occurrence, with file and line number |
| `tail -F app.log` | follow a log while reproducing a bug; `-F` survives log rotation |
| `less +F app.log` | page a huge log; `/` to search, `G` for the end, `q` to quit |
| `pgrep -af java` | the PID and the full command line, JVM flags included |
| `top`, `htop` | what is eating CPU or memory right now |
| `kill -TERM 4242` | stop a service gracefully; `kill -9` only when it ignores `TERM` |
| `df -h`, `du -sh /var/* \| sort -h` | is the disk full, and which directory grew |
| `lsof -i :8080`, `ss -tlnp` | which process is holding the port (`ss` is Linux only) |
| `find /var/log -name '*.log' -mtime +7` | files to rotate or delete; add `-delete` once you trust the list |
| `sort \| uniq -c \| sort -rn \| head` | the top N of anything: IPs, status codes, exceptions |
| `jq '.level' app.json` | read JSON logs and API responses; `jq -r` for raw strings |

`xargs` turns lines into arguments (`pgrep -f worker | xargs kill -TERM`); `cut`, `awk` and `sed` pick and rewrite fields; `man` or `tldr` (item 5.8) explain the flags.

## Example: triage a log, read the exit codes

A seven-line access log in `address method path status duration` format:

```text
$ awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -3
   3 10.0.0.7
   3 10.0.0.5
   1 10.0.0.9
$ grep ' 500 ' access.log | cut -d' ' -f1,3 | sort | uniq -c
   3 10.0.0.7 /api/orders
```

`awk` keeps the first field, `sort` groups equal lines, `uniq -c` counts each group, `sort -rn` orders by count, `head` keeps the top. The second pipeline answers "who is getting errors, and where".

Exit codes and signals, observed in a shell:

```text
$ sh -c 'exit 3'; echo $?
3
$ sleep 30 & kill -TERM $!; wait $!; echo $?
143
$ no_such_command; echo $?
127
$ false | true; echo $?
0
$ set -o pipefail; false | true; echo $?
1
```

`143 = 128 + 15` says the process was terminated by a signal, not that it failed on its own. Without `pipefail`, the failing `false` was invisible.

## Pitfalls

- `kill -9` as the first move. Nothing gets to clean up: no shutdown hooks, no connection draining, no flushed buffers. Send `TERM`, wait, then escalate.
- `cmd 2>&1 > file`. stderr goes to the terminal, because redirections are applied left to right.
- `build.sh | tee build.log` in CI returns `tee`'s exit code. Use `set -o pipefail`, and `set -euo pipefail` at the top of scripts (item 5.4).
- `chmod 777` to make an error go away. SSH refuses private keys that others can read, and a world-writable configuration directory is a privilege escalation waiting to happen.
- Deleting a huge log file that a running process still has open. The space is not freed until the process closes it, so `df` stays full while `du` says otherwise. Find the file with `lsof +L1`; next time truncate it with `: > file` instead of `rm`.

## Check yourself

1. A file shows `-rw-r-----  1 app app` and your user is in group `app`. Can you read it, execute it, delete it? Which answer depends on something other than these nine bits?
2. `docker stop` waits ten seconds and then the container dies. Which two signals were sent, in which order, and what should a JVM do between them?
3. `./run-tests.sh 2>&1 | tee tests.log` exits 0 although tests failed. Why, and what one line fixes the script?
4. `df -h` says `/var` is 98% full, `du -sh /var` reports 2 GB on a 100 GB volume. What is the most likely explanation and which command confirms it?

## Go deeper

- [The Missing Semester: Command-line Environment](https://missing.csail.mit.edu/2020/command-line/) · job control, signals, aliases and dotfiles in one lecture with exercises.
- [Linux Journey](https://linuxjourney.com/) · short, well-ordered lessons on permissions, processes and the filesystem.
- [The Art of Command Line](https://github.com/jlevy/the-art-of-command-line) · the one-page list of everything worth knowing; skim it twice a year.
- [explainshell](https://explainshell.com/) · paste any pipeline and get every flag explained from the man pages.

---

Part of [Foundations](../README.md) · items 5.1, 5.2, 5.3
