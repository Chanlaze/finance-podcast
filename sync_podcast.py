#!/usr/bin/env python3
"""Download new authorised playlist items and build a podcast RSS feed."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import pathlib
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "data" / "episodes.json"
DOCS = ROOT / "docs"
WORK = ROOT / "work"
MANIFEST_PATH = ROOT / "upload_manifest.json"

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("atom", ATOM_NS)
ET.register_namespace("content", CONTENT_NS)


def load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(args: list[str]) -> dict:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f"yt-dlp exited {proc.returncode}")
    return json.loads(proc.stdout)


def iso_from_metadata(info: dict) -> dt.datetime:
    timestamp = info.get("timestamp") or info.get("release_timestamp")
    if timestamp:
        return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    raw = info.get("upload_date") or info.get("release_date")
    if raw and len(raw) == 8:
        return dt.datetime.strptime(raw, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def duration_text(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def public_urls() -> tuple[str, str, str]:
    repository = os.environ.get("GITHUB_REPOSITORY", "Chanlaze/finance-podcast")
    owner, repo = repository.split("/", 1)
    site = f"https://{owner.lower()}.github.io/{repo}"
    return repository, site, f"{site}/feed.xml"


def discover(playlist_url: str) -> list[dict]:
    info = run_json([
        "yt-dlp", "--js-runtimes", "node", "--flat-playlist", "--dump-single-json",
        "--no-warnings", playlist_url,
    ])
    return [entry for entry in info.get("entries", []) if entry and entry.get("id")]


def download_episode(video_id: str, config: dict, repository: str) -> tuple[dict, pathlib.Path]:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    WORK.mkdir(parents=True, exist_ok=True)
    output_template = str(WORK / f"{video_id}.%(ext)s")
    info = run_json(["yt-dlp", "--js-runtimes", "node", "--dump-single-json", "--no-warnings", video_url])
    subprocess.run([
        "yt-dlp", "--js-runtimes", "node", "--no-playlist", "--no-warnings",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
        "--embed-metadata", "--embed-thumbnail", "--convert-thumbnails", "jpg",
        "--output", output_template, video_url,
    ], check=True)
    audio_path = WORK / f"{video_id}.mp3"
    if not audio_path.exists():
        raise RuntimeError(f"Audio file not created for {video_id}")

    release_tag = config["release_tag"]
    asset_name = urllib.parse.quote(audio_path.name)
    media_url = f"https://github.com/{repository}/releases/download/{release_tag}/{asset_name}"
    published = iso_from_metadata(info)
    episode = {
        "id": video_id,
        "title": info.get("title") or video_id,
        "description": info.get("description") or "",
        "source_url": info.get("webpage_url") or video_url,
        "media_url": media_url,
        "length": audio_path.stat().st_size,
        "duration": int(info.get("duration") or 0),
        "published": published.isoformat(),
        "thumbnail": info.get("thumbnail") or "",
    }
    return episode, audio_path


def add_text(parent: ET.Element, name: str, value) -> ET.Element:
    node = ET.SubElement(parent, name)
    node.text = str(value or "")
    return node


def build_feed(config: dict, episodes: list[dict], site_url: str, feed_url: str) -> None:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    add_text(channel, "title", config["podcast_title"])
    add_text(channel, "link", site_url)
    add_text(channel, "description", config["podcast_description"])
    add_text(channel, "language", config.get("language", "zh-HK"))
    add_text(channel, f"{{{ITUNES_NS}}}author", config.get("author", ""))
    add_text(channel, f"{{{ITUNES_NS}}}explicit", "false")
    add_text(channel, "lastBuildDate", email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)))
    ET.SubElement(channel, f"{{{ATOM_NS}}}link", {
        "href": feed_url, "rel": "self", "type": "application/rss+xml"
    })

    ordered = sorted(episodes, key=lambda item: item["published"], reverse=True)
    for episode in ordered:
        item = ET.SubElement(channel, "item")
        add_text(item, "title", episode["title"])
        add_text(item, "link", episode["source_url"])
        guid = add_text(item, "guid", episode["id"])
        guid.set("isPermaLink", "false")
        published = dt.datetime.fromisoformat(episode["published"])
        add_text(item, "pubDate", email.utils.format_datetime(published))
        add_text(item, "description", episode["description"])
        add_text(item, f"{{{CONTENT_NS}}}encoded", episode["description"])
        add_text(item, f"{{{ITUNES_NS}}}duration", duration_text(episode.get("duration")))
        if episode.get("thumbnail"):
            ET.SubElement(item, f"{{{ITUNES_NS}}}image", {"href": episode["thumbnail"]})
        ET.SubElement(item, "enclosure", {
            "url": episode["media_url"],
            "length": str(episode["length"]),
            "type": "audio/mpeg",
        })

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    DOCS.mkdir(parents=True, exist_ok=True)
    tree.write(DOCS / "feed.xml", encoding="utf-8", xml_declaration=True)


def build_index(config: dict, episodes: list[dict], feed_url: str) -> None:
    rows = []
    for episode in sorted(episodes, key=lambda item: item["published"], reverse=True):
        title = html.escape(episode["title"])
        source = html.escape(episode["source_url"], quote=True)
        media = html.escape(episode["media_url"], quote=True)
        date = html.escape(episode["published"][:10])
        rows.append(
            f'<article><h2><a href="{source}">{title}</a></h2>'
            f'<p>{date}</p><audio controls preload="none" src="{media}"></audio></article>'
        )
    page = f"""<!doctype html>
<html lang="zh-HK"><head><meta name="robots" content="noindex,nofollow"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(config['podcast_title'])}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#17202a}}
a{{color:#0758a5}}article{{border-top:1px solid #ddd;padding:18px 0}}audio{{width:100%}}
.feed{{word-break:break-all;background:#f3f5f7;padding:12px;border-radius:8px}}
</style></head><body><main><h1>{html.escape(config['podcast_title'])}</h1>
<p>{html.escape(config['podcast_description'])}</p><p class="feed"><strong>RSS:</strong> <a href="{html.escape(feed_url)}">{html.escape(feed_url)}</a></p>
{''.join(rows) or '<p>No episodes yet. Run the GitHub workflow first.</p>'}</main></body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    config = load_json(CONFIG_PATH, {})
    episodes = load_json(STATE_PATH, [])
    known = {episode["id"] for episode in episodes}
    repository, site_url, feed_url = public_urls()
    entries = discover(config["playlist_url"])
    unseen = [entry for entry in reversed(entries) if entry["id"] not in known]
    limit = int(os.environ.get("MAX_NEW_EPISODES", config.get("max_new_episodes_per_run", 20)))
    unseen = unseen[:max(1, min(limit, 100))]

    uploads: list[str] = []
    for entry in unseen:
        video_id = entry["id"]
        print(f"Processing {video_id}", flush=True)
        try:
            episode, audio_path = download_episode(video_id, config, repository)
        except Exception as exc:
            print(f"Warning: skipped {video_id}: {exc}", file=sys.stderr)
            if any(word in str(exc).lower() for word in ["not a bot", "sign in", "429", "403"]):
                raise RuntimeError("YouTube access blocked; manual review required.") from exc
            continue
        episodes.append(episode)
        known.add(video_id)
        uploads.append(str(audio_path.relative_to(ROOT)))

    if unseen and not uploads:
        raise RuntimeError("No new episode could be downloaded; inspect download errors.")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(uploads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    build_feed(config, episodes, site_url, feed_url)
    build_index(config, episodes, feed_url)
    print(f"Prepared {len(uploads)} new episode(s); {len(episodes)} total.")
    return 0


if __name__ == "__main__":
    from local_sync import main as local_main
    raise SystemExit(local_main())

