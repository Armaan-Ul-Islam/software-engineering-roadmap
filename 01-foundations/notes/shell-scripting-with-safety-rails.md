# Shell scripting with safety rails

> **In one sentence:** A shell script is a sequence of commands where every unquoted variable is split on whitespace and every failure is ignored by default, so a usable script starts with `set -euo pipefail`, quotes every expansion, checks its arguments, cleans up with `trap`, and stays short enough that you would not rather have written it in a real language.

**Why it matters:** Deploy scripts, CI steps, cron jobs and Dockerfile `RUN` lines are shell, and shell fails silently: a step that errors in the middle keeps going, a path with a space becomes two paths, and an unset variable turns `rm -rf "$directory/build"` into `rm -rf /build`. Each of these has taken down a production system somewhere. Twenty lines of discipline prevent nearly all of it.

## The idea

**Words and quoting.** The shell reads a line, expands variables and globs, splits the result into words on whitespace (the characters in `IFS`), and runs the first word with the rest as arguments. Expansion happens *before* splitting, so `$file` containing `release notes.txt` becomes two arguments. Double quotes stop word splitting and globbing but still expand variables; single quotes stop everything. The rule is mechanical: **every** `$variable` and `$(command)` goes in double quotes unless you specifically want splitting. The same applies to `"$@"`, which passes all arguments through unchanged, where a bare `$@` or `$*` re-splits them.

**Exit codes and `set -e`.** Every command returns 0 for success or 1 to 255 for failure (item 5.2 lists the conventions). By default the shell ignores failures and runs the next line. `set -e` makes the script exit on the first failing command, with important exceptions: a command inside an `if` or `while` condition, on the left of `&&` or `||`, in a pipeline other than the last command, or whose output is captured as part of a `local` or `export` assignment does not trigger it. `set -u` makes an unset variable an error instead of an empty string. `set -o pipefail` makes a pipeline's exit code the last non-zero one instead of the last command's, so `grep pattern file | sort` fails when `grep` finds nothing. Together: `set -euo pipefail` as the first line after the shebang. It is a safety net, not a guarantee; the exceptions above are why a script still needs explicit `|| exit 1` or `if ! command; then` where a failure must be handled.

**Tests and conditions.** `[[ ... ]]` is bash's test construct: `[[ -f "$path" ]]` (file exists), `[[ -z "$value" ]]` (empty), `[[ "$answer" == y* ]]` (pattern match), `[[ $# -eq 2 ]]` (argument count). It does not word-split, so it is safer than the older `[ ... ]`, which is an ordinary command with the usual quoting rules. A command's own exit code is a condition too: `if grep -q "$version" changelog.txt; then`.

**Cleanup.** `trap 'rm -rf "$work_directory"' EXIT` runs the command when the script exits for any reason, including `set -e` failures and Ctrl-C. Temporary files come from `mktemp -d`, never from a hand-built `/tmp/name`.

**When to stop.** Shell has no data structures beyond strings and arrays, no exceptions, no types, and its error handling is the exceptions list above. The limit is roughly: a script that parses structured data (use `jq` for JSON, otherwise a program), needs a loop with state across iterations, handles more than one error path, or passes about 100 lines. At that point write it in Python, Java or whatever the team runs, and keep the shell wrapper to a single line that calls it. Shell is for gluing commands together, not for logic.

## Example: the three failure modes, then a script with rails

Quoting, observed:

```bash
#!/usr/bin/env bash
file="demo/release notes.txt"
echo "--- unquoted"
ls -l $file
echo "--- quoted"
ls -l "$file"
echo "--- unset variable, unquoted, with rm printed instead of run"
directory=""
echo rm -rf $directory/build
```

```text
$ bash quoting.sh
--- unquoted
ls: demo/release: No such file or directory
ls: notes.txt: No such file or directory
--- quoted
-rw-r--r--@ 1 armaan  wheel  0 Oct 29 11:41 demo/release notes.txt
--- unset variable, unquoted, with rm printed instead of run
rm -rf /build
```

The last line is the famous one: a typo in the variable name, a missing environment variable in CI, or a failed `cd` and the script deletes from the root. `set -u` would have stopped it at the expansion; `rm -rf "${directory:?directory is not set}/build"` stops it with a message.

A deploy script skeleton with the rails in place:

```bash
#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 <environment> <version>" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage
environment="$1"
version="$2"

work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT

echo "deploying $version to $environment using $work_directory"
grep -c "$version" demo/changelog.txt | tee "$work_directory/count.txt"
echo "this line is not reached when grep finds nothing"
```

```text
$ bash safe.sh; echo "exit $?"
usage: safe.sh <environment> <version>
exit 2
$ bash safe.sh staging 2.3.0; echo "exit $?"
deploying 2.3.0 to staging using /var/folders/x1/6_zq6s895wd50l7r1_69xtc00000gn/T/tmp.BSuZnhCIhh
0
exit 1
$ bash -c 'set -u; echo "$undefined_name"'; echo "exit $?"
bash: undefined_name: unbound variable
exit 127
```

Three things to notice. Missing arguments exit with 2 and a usage line on stderr, so a caller can tell "wrong usage" from "deploy failed". `grep -c` printed `0` and exited 1 (no match); without `pipefail` the pipeline's exit code would have been `tee`'s 0 and the script would have continued to the next line. The temporary directory was removed by the `trap` even though the script died in the middle. Put `shellcheck` (linked below) in CI and it will flag every unquoted expansion and `set -e` exception before a reviewer has to.

## Pitfalls

- `cd "$directory" && rm -rf build` is safe; `cd $directory; rm -rf build` runs `rm` in the current directory when `cd` fails. Under `set -e` the failing `cd` stops the script, which is another reason to turn it on.
- `local result=$(command)` under `set -e`. The exit code of the assignment is `local`'s, which is 0, so the failure is lost. Declare first, then assign on its own line: `local result; result=$(command)`.
- `for file in $(ls)`. Splits on spaces and expands globs in file names. Use `for file in *.log` or `find ... -print0 | xargs -0`.
- `[ $value = "yes" ]` with an empty `$value` becomes `[ = "yes" ]`, a syntax error. `[[ ... ]]` handles this; so does quoting.
- Parsing structured output with `cut` and `awk`. JSON changes field order, file names contain newlines. `jq` for JSON; a program for anything else.
- Testing a script by running it. Test it with `bash -n script.sh` (syntax), `shellcheck script.sh`, and a dry-run flag that prints commands instead of running them, before it runs with `rm` and `sudo` in it.
- macOS ships bash 3.2 (from 2007) and BSD versions of `sed`, `date` and `grep`. A script that works on a developer laptop may fail in a Linux container and the other way around; pin to `#!/usr/bin/env bash`, avoid bash 4 features if macOS must run it, and test in the image that will run it.

## Check yourself

1. Under `set -euo pipefail`, which of these failures stops the script and which does not: `grep -q x file` as an `if` condition; `curl $url | jq .` where `curl` fails; `local body=$(curl "$url")` where `curl` fails; a bare `false` on its own line?
2. A CI step is `./gradlew test | tee build.log` and the job stays green after test failures. Explain why and give the one-line fix.
3. Rewrite `for file in $(ls *.csv); do process $file; done` so that it handles a file called `q3 report.csv`, and explain each change.
4. You are asked to add retry logic with backoff and JSON parsing of a response to a 40-line deploy script. What do you do, and why?

## Go deeper

- [BashGuide](https://mywiki.wooledge.org/BashGuide) · the one guide that explains word splitting and quoting correctly; read "Parameters" and "Tests and Conditionals".
- [ShellCheck](https://www.shellcheck.net/) · a linter that catches nearly every mistake in this note; install it locally and in CI.
- [The Missing Semester: Shell Tools and Scripting](https://missing.csail.mit.edu/2020/shell-tools/) · scripting basics with exercises, including `find`, `xargs` and exit codes.
- [explainshell](https://explainshell.com/) · paste a line you inherited and see what every flag does before you change it.

---

Part of [Foundations](../README.md) · item 5.4
