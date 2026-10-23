# Git's mental model: snapshots, pointers and the reflog

> **In one sentence:** A Git repository is a graph of immutable commit snapshots, a branch is a file holding the hash of one commit, `HEAD` says which branch you are on, and nearly every frightening Git operation only moves those pointers, so the reflog, which records every move, can put them back.

**Why it matters:** People lose work to a bad rebase or a `reset --hard` not because Git deleted anything but because they do not know the commits are still there. Once you see the graph, merge versus rebase stops being a matter of opinion, conflicts become mechanical, and "I think I just destroyed the branch" becomes a two-command fix.

## The idea

**Objects (item 6.1).** Git stores everything as objects named by the SHA-1 of their content; three kinds matter here. A *blob* is file content. A *tree* is a directory: names pointing at blobs and other trees. A *commit* points at one tree (the complete snapshot of the project at that moment) and at its parent commit or commits, and carries author, committer, timestamp and message. Because the hash covers everything including the parent hashes, no commit can be changed; you can only make a new one. A commit is a snapshot, not a diff: `git diff` computes differences on demand by comparing trees, and unchanged files share the same blob between commits.

```text
$ git cat-file -p main
tree 57ccce2e966dd4e22ab6f5c0e545e4507b0c6e5c
parent 1799d0be2dd1f0ecdff2453e15c273e825612274
author Demo <demo@example.com> 1792780451 +0600
committer Demo <demo@example.com> 1792780451 +0600

E: hotfix on main
```

**References.** A branch is a file under `.git/refs/heads/` containing one hash, 41 bytes including the newline:

```text
$ cat .git/refs/heads/main
ff19efe13c5ef47e55dabe3729b51add76e80920
```

Committing writes a new commit object and overwrites that file. `origin/main` is `refs/remotes/origin/main`, a local note of where the remote's `main` was at the last fetch. `HEAD` is normally a symbolic reference, `ref: refs/heads/feature`, meaning "the branch I am on"; when it holds a raw hash instead you are in *detached HEAD*, and new commits belong to no branch.

**The index.** Between your working directory and `HEAD` sits the index (the staging area), a binary file listing the paths and blob hashes that the *next* commit's tree will contain. `git add` writes a blob and updates the index; `git commit` turns the index into a tree, writes a commit pointing at it, and moves the current branch. `git status` is a three-way comparison of `HEAD`, the index and the working tree. The undo commands (item 6.4) are named by which of the three they touch: `restore <file>` copies index to working tree (`--staged` copies `HEAD` to index); `reset` moves the branch pointer and then, depending on `--soft`, `--mixed` (the default) or `--hard`, also resets the index and the working tree; `revert` creates a new commit that undoes an old one, which is the only safe undo on a shared branch.

**Merge and rebase (item 6.3).** `git merge feature` on `main` creates one new commit with two parents and moves `main` to it; both histories are preserved. If `main` has not moved since `feature` branched off, Git fast-forwards: no commit is created, `main` simply moves to `feature`'s commit. `git rebase main` on `feature` takes each commit on `feature` that is not on `main`, applies its changes on top of `main` in order, creating new commits with new hashes, and finally moves `feature` to the last one. The old commits are untouched; they are simply unreachable from any branch now. A conflict in either stops the operation with markers in the file; edit, `git add`, then `--continue`, or `--abort` to return exactly to the start.

**The reflog (item 6.4).** Every time `HEAD` or a branch moves, Git appends a line to `.git/logs/HEAD` or `.git/logs/refs/heads/<branch>`: the old hash, the new hash and why. `feature@{1}` means "where `feature` pointed one move ago", `HEAD@{2}` two moves ago. Merge, rebase and reset also save the previous position in `ORIG_HEAD`. The reflog is local to your clone, is not pushed, and expires: entries for unreachable commits after 30 days, the rest after 90. Until then, nothing you committed is lost.

## Example: a rebase, and the way back

Two commits on `feature`, one hotfix on `main` meanwhile:

```text
A ── B ── E          ← main
      \
       C ── D        ← feature, HEAD
```

```text
$ git log --oneline --graph --all
* dddd172 D: feature part 2
* 53ad70b C: feature part 1
| * ff19efe E: hotfix on main
|/
* 1799d0b B: add b
* 1c3d5fd A: initial
```

Rebase `feature` onto `main`:

```text
$ git switch feature
$ git rebase main
Successfully rebased and updated refs/heads/feature.
$ git log --oneline --graph --all
* a917d84 D: feature part 2
* dc0cabc C: feature part 1
* ff19efe E: hotfix on main
* 1799d0b B: add b
* 1c3d5fd A: initial
```

```text
A ── B ── E ── C' ── D'   ← feature, HEAD
      \   ↑
       \  main
        C ── D            (unreachable)
```

`C'` and `D'` carry the same changes and messages as `C` and `D` but have new hashes, because their parents differ. `C` and `D` still exist in `.git/objects`; `git log` just has no path to them. The branch's reflog does:

```text
$ git reflog show feature
a917d84 feature@{0}: rebase (finish): refs/heads/feature onto ff19efe13c5ef47e55dabe3729b51add76e80920
dddd172 feature@{1}: commit: D: feature part 2
53ad70b feature@{2}: commit: C: feature part 1
1799d0b feature@{3}: branch: Created from HEAD
```

To put the branch back exactly as it was:

```text
$ git reset --hard feature@{1}
HEAD is now at dddd172 D: feature part 2
```

Right after a rebase, `git reset --hard ORIG_HEAD` does the same. To keep both versions while you compare them, make a branch instead of resetting: `git branch feature-before-rebase feature@{1}`. The same recipe repairs a bad `git reset --hard` or a commit made in detached HEAD: run `git reflog`, find the line before the mistake, and `git reset --hard HEAD@{n}` or `git switch -c rescue <hash>`.

The reflog cannot restore work that was never committed: `reset --hard` overwrites uncommitted changes in the working tree, and no reflog entry refers to them. Staged files can sometimes be recovered as dangling blobs with `git fsck --lost-found`; unstaged edits are gone.

## Pitfalls

- Believing rebase deletes or rewrites commits in place. It creates new ones and moves a pointer; the old ones stay reachable through the reflog for weeks.
- `reset --hard` with uncommitted changes in the working tree. This is the one genuinely destructive everyday command; `git stash` or a WIP commit first.
- Rebasing commits that others have already based work on, then force-pushing over them. Rebase only your own unpublished commits, and push with `--force-with-lease` so you cannot overwrite someone else's push (item 6.5).
- Committing in detached HEAD after checking out a tag or a commit, then switching branches. The commits exist only in the reflog; `git switch -c rescue <hash>` saves them.
- Resolving a conflict by taking "ours" or "theirs" wholesale. During a rebase the meanings flip: "ours" is the branch you are rebasing onto, "theirs" is your own commit being replayed.

## Check yourself

1. After `git rebase main`, your commits have new hashes. Where are the old ones, which command lists them, and how long do they stay?
2. Describe `git reset --soft HEAD~1`, `--mixed` and `--hard` in terms of the branch pointer, the index and the working tree. Which one can lose something no reflog entry can bring back?
3. Draw the graph after merging a three-commit `feature` into `main` with a merge commit, and after rebasing `feature` onto `main` and fast-forwarding. Which history would you want when bisecting a bug six months later, and why?
4. You ran `git reset --hard origin/main` while on `feature` and lost two commits. Give the two commands that recover them without touching `main`.

## Go deeper

- [Pro Git: Git Internals, Plumbing and Porcelain](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) · build a repository by hand with the plumbing commands; after this chapter nothing in Git is magic.
- [Learn Git Branching](https://learngitbranching.js.org/) · an interactive sandbox that draws the graph after every command; do the rebase levels.
- [Pro Git: Branches in a Nutshell](https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell) and [Rebasing](https://git-scm.com/book/en/v2/Git-Branching-Rebasing) · what the pointers do, with diagrams, and the rule about rebasing shared history.
- [Oh Shit, Git!?!](https://ohshitgit.com/) · the recovery recipes for the moment you need them.

---

Part of [Foundations](../README.md) · items 6.1, 6.3, 6.4
