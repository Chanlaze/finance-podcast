# Finance Podcast

Personal podcast feed generated from an authorised YouTube playlist.

## What it does

- Checks the configured playlist twice daily and can also be run manually.
- Converts newly discovered videos to MP3 with `yt-dlp` and FFmpeg.
- Stores audio as assets in the `podcast-media` GitHub Release.
- Rebuilds `docs/feed.xml` and a small subscription page.
- Deploys the `docs` folder with GitHub Pages.

## One-time GitHub setup

1. Create or rename the public repository to `finance-podcast`.
2. Add all files in this project to its default branch.
3. Open **Settings → Actions → General → Workflow permissions** and select
   **Read and write permissions**.
4. Open **Settings → Pages → Build and deployment → Source** and select
   **GitHub Actions**.
5. Open **Actions → Sync podcast → Run workflow** for the first import.

The podcast feed will be:

`https://chanlaze.github.io/finance-podcast/feed.xml`

The first and later runs import up to 20 new episodes each. Re-run the workflow
until the initial backlog is complete. Afterwards, the scheduled runs keep the
feed updated automatically.

## Important

The Pages site and Release assets are publicly reachable by anyone who has the
URL. Use this project only for content that you own or are authorised to
download and re-host.

