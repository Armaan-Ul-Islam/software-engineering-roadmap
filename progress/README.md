# Progress profiles

Each file here is one person's progress, saved from the tracker. The tracker (`index.html`) lists every file in this folder as a profile; pick yours, and the items it marks done are loaded as your starting point. Your browser keeps a working copy; use **Save file** in the tracker to download the current state, then put it here as `<profile>.json` and commit (or upload it through GitHub's "Add file" button). The hosted site rebuilds on every push, so the file becomes the new baseline on every device.

Format (the tracker writes it; you never edit it by hand):

```json
{
  "format": "software-engineering-roadmap-progress",
  "version": 1,
  "profile": "armaan",
  "exportedAt": "2026-10-24T09:12:00.000Z",
  "progress": {
    "databases:5.3": "2026-10-24",
    "spring:4.3": "2026-10-24"
  }
}
```

Keys are `<domain slug>:<item id>`; values are the date the item was ticked. `python3 tools/save_progress.py <downloaded file>` copies a download into this folder with the right name and rebuilds the data file.
