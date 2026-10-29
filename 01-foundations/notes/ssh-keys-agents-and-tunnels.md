# SSH: keys, agents, config and tunnels

> **In one sentence:** SSH authenticates you with a key pair (the private half never leaves your machine, the public half is copied to every server), an agent holds the unlocked private key so you type the passphrase once, `~/.ssh/config` turns long commands into short host names, and port forwarding turns the same encrypted connection into a tunnel for any TCP service behind it.

**Why it matters:** Every production server, bastion, CI runner and Git remote you will touch speaks SSH. The difference between an engineer who fumbles with `Permission denied (publickey)` and one who reaches a database on a private subnet in ten seconds is a working mental model of where the keys are, what the agent does, and which direction a tunnel points.

## The idea

**Keys.** `ssh-keygen -t ed25519` produces two files: `id_ed25519` (private, mode `600`, stays on your machine, ideally with a passphrase) and `id_ed25519.pub` (public, one line, safe to post anywhere). A server lets you in when your public key is listed in `~/.ssh/authorized_keys` of the account you log in as, and your client can prove it holds the matching private key. Ed25519 is the current default: short keys, fast, no parameter choices to get wrong. RSA keys still work and are needed for a few old systems; if you must, use 4096 bits. The server has a key pair too; its public key is stored in your `~/.ssh/known_hosts` on first connection, and a later mismatch produces the loud `REMOTE HOST IDENTIFICATION HAS CHANGED` warning, which means either the server was rebuilt or someone is in the middle.

**The agent.** A passphrase-protected key would need the passphrase on every connection. `ssh-agent` is a process that holds decrypted private keys in memory; `ssh-add` loads a key into it, `ssh-add -l` lists what is loaded, and `ssh` asks the agent to sign the authentication challenge instead of reading the key file. macOS and most desktop Linux start an agent for you. *Agent forwarding* (`ssh -A` or `ForwardAgent yes`) lets a remote shell use your local agent, so `git pull` on a server can authenticate with your key without the key being on the server. Only forward to hosts you trust: root on that host can use your agent while you are connected.

**Config.** `~/.ssh/config` maps a short name to a host, user, port, key and any other option, with `Host` patterns and `ProxyJump` for hopping through a bastion. After that, `ssh app-1` replaces `ssh -i ~/.ssh/id_ed25519 -J deploy@bastion.example.com deploy@10.0.3.11`, and `scp`, `rsync`, `git` and your IDE all honour the same file. `ssh -G app-1` prints the fully resolved configuration, which is the first thing to check when a connection does something unexpected.

**Port forwarding.** An SSH connection can carry extra TCP streams. Three shapes:

| Flag | Meaning | Typical use |
|---|---|---|
| `-L 15432:db.internal:5432` | *Local* forward: connections to `localhost:15432` on your machine go through the SSH server to `db.internal:5432` | reach a database on a private subnet from your laptop |
| `-R 8080:localhost:3000` | *Remote* forward: connections to port 8080 on the SSH server go back through the tunnel to port 3000 on your machine | let a partner's webhook reach your dev server behind NAT (item 3.2) |
| `-D 1080` | *Dynamic* forward: a SOCKS proxy on your machine that routes through the SSH server | browse an internal web console without a VPN |

Add `-N` to forward without opening a shell. The forward uses the SSH server's network position, so anything the server can reach, your laptop can now reach on a local port.

**Copying files.** `scp source user@host:destination` copies once. `rsync -avz --delete ./build/ user@host:/var/www/app/` copies only what changed, preserves permissions and timestamps, and is restartable; prefer it for anything bigger than one file or done more than once. Both run over SSH and use the same keys and config.

## Example: a key, a config, a resolved host

```text
$ ssh-keygen -t ed25519 -C "armaan@laptop" -f ./id_ed25519_demo
Generating public/private ed25519 key pair.
Your identification has been saved in ./id_ed25519_demo
Your public key has been saved in ./id_ed25519_demo.pub
The key fingerprint is:
SHA256:tyjwEQTkwuV96SdwqhJRHeNrTFRik1MSiH0+5ky6h5A armaan@laptop
$ ls -l
-rw-------  1 armaan  wheel  399 Oct 29 11:43 id_ed25519_demo
-rw-r--r--  1 armaan  wheel   95 Oct 29 11:43 id_ed25519_demo.pub
$ cat id_ed25519_demo.pub
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINobbu1lXIM33xlkYll4vPCT+uHG+rAg6PwK3tchrK9y armaan@laptop
```

The private key is `600`, the public key is one line that goes into `authorized_keys` on the server (or `ssh-copy-id user@host` does it for you). The comment is only a label; make it say which machine the key lives on so a stale key can be identified and removed. The fingerprint is how you compare keys without comparing the whole string.

A config for a private subnet behind a bastion:

```text
Host bastion
    HostName bastion.example.com
    User deploy
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

Host app-*
    User deploy
    ProxyJump bastion
    IdentityFile ~/.ssh/id_ed25519

Host app-1
    HostName 10.0.3.11
```

```text
$ ssh -F ./config -G app-1 | grep -E '^(hostname|user|port|identityfile|proxyjump|forwardagent) '
user deploy
hostname 10.0.3.11
port 22
identityfile ~/.ssh/id_ed25519
forwardagent no
proxyjump bastion
```

Options are resolved first match wins per option, top to bottom, which is why the specific `Host app-1` block can sit after the `app-*` pattern and still contribute `HostName`. With this file in place, these all work without flags:

```bash
ssh app-1
rsync -avz ./build/ app-1:/var/lib/app/releases/2.3.0/
ssh -N -L 15432:db.internal:5432 app-1
```

The last line is the daily one: while it runs, `psql -h localhost -p 15432` on the laptop talks to the private database, through the bastion, through `app-1`. `IdentitiesOnly yes` matters when the agent holds several keys: without it, `ssh` offers every loaded key in turn, and a server that counts failed attempts (or GitHub, which identifies you by the first key that matches) may reject you before the right key is tried.

## Pitfalls

- `Permission denied (publickey)`. In order: is the public key in the right account's `authorized_keys`; is `~/.ssh` `700` and the key `600` (the server refuses sloppy permissions and says nothing useful); is the right key offered (`ssh -v` shows "Offering public key"; `ssh-add -l` shows the agent's contents)? Nine times out of ten it is one of those three.
- Private key on a server. Copying `id_ed25519` to a bastion to hop onward is how keys leak. Use `ProxyJump` (the private key stays home) or agent forwarding to trusted hosts only.
- Agent forwarding to shared hosts. Anyone with root there can authenticate as you while you are connected. Prefer `ProxyJump`, which needs no forwarding.
- A tunnel that "does not work" because of the bind address. `-L` binds to `localhost` on your machine by default; another container or a colleague cannot use it unless you bind `0.0.0.0:15432:...`, and then you have exposed the database to your network. On the `-R` side, the server binds to its own loopback unless `GatewayPorts` is enabled in its `sshd_config`.
- Idle tunnels dropped by a NAT or firewall. Add `ServerAliveInterval 30` to the config so the client sends keepalives; or run tunnels under `autossh`.
- Blindly accepting a changed host key. Delete the line with `ssh-keygen -R hostname` only after confirming the server was really rebuilt.
- `scp -r` for a 2 GB deploy. One flaky packet and it starts over. `rsync` resumes, skips unchanged files and can `--delete` what no longer belongs.

## Check yourself

1. You need `psql` on your laptop to reach `db.internal:5432`, which only `app-1` can reach, which only the bastion can reach. Write the config and the single `ssh` command, and state what `-N` changes.
2. A partner needs to send webhooks to the API you are developing on `localhost:3000`, and your laptop is behind NAT. Which forward type, in which direction, and what must be enabled on the server for it to be reachable from outside?
3. `ssh prod` fails with `Permission denied (publickey)` although it worked yesterday. Name three things to check and the command that shows which key the client is offering.
4. Why is `ProxyJump` preferable to copying your key to the bastion, and preferable to agent forwarding?

## Go deeper

- [SSH Academy: SSH command](https://www.ssh.com/academy/ssh/command) · the command line options, with separate pages on keys, agents and config.
- [The Missing Semester: Command-line Environment](https://missing.csail.mit.edu/2020/command-line/) · the SSH section covers keys, config, tunnels and copying files, with exercises.
- [ssh_config(5)](https://man7.org/linux/man-pages/man5/ssh_config.5.html) · every option; search for `ProxyJump`, `IdentitiesOnly` and `ServerAliveInterval`.
- [ssh(1)](https://man7.org/linux/man-pages/man1/ssh.1.html) · the `-L`, `-R`, `-D` and `-G` flags explained precisely.

---

Part of [Foundations](../README.md) · item 5.5
