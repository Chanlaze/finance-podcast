# Finance Podcast

Local Windows downloader for an authorised YouTube playlist. Audio is public in
`podcast-media` GitHub Releases. GitHub Pages publishes `main:/docs`.
The legacy `sync.yml` workflow is disabled: keep it disabled.

RSS: https://chanlaze.github.io/finance-podcast/feed.xml

## Local operation

Python 3.13, `.venv` with `requirements.txt`, FFmpeg and ffprobe in `.tools`,
Node.js, Git and an authenticated GitHub CLI are required. Machine-specific
paths are in ignored `local-settings.json`. Sign in locally with `gh auth login`
if needed. Never commit credentials or cookies.

Single import: `.venv\Scripts\python.exe local_sync.py --limit 1 --publish`

`run-local.ps1` processes at most three unseen episodes per run in playlist order,
prevents overlapping scheduled runs, and writes ignored `logs/` files. Existing
published IDs are skipped. Local audio and metadata are reused after failure;
partial downloads resume. Release assets are never overwritten. Public SHA-256
and byte length must match before an episode is recorded. MP3 files are fully
decoded and compared against source duration before upload.

Retain `data/episodes.json` and `work/`. A failed push leaves the local commit for
the next run. Review remote changes if push is rejected; no force-push is used.
Do not run concurrent manual imports or sync from another machine.

The Windows task needs this user logged in and an internet connection. Sleep or
shutdown may delay execution. Inspect task result and logs for failures. If
YouTube requests verification, complete it locally; no password is stored here.

The page uses noindex,nofollow and robots.txt. Audio and RSS remain public.
