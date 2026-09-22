"""Local-only downloader: validate, upload, then record and publish."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import sync_podcast as podcast

ROOT = pathlib.Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PYTHONUTF8'] = '1'
os.environ['PATH'] = str(ROOT / '.tools') + os.pathsep + os.environ['PATH']
settings = podcast.load_json(ROOT / 'local-settings.json', {})
for key in ('git_dir', 'gh_dir'):
    if settings.get(key):
        os.environ['PATH'] = settings[key] + os.pathsep + os.environ['PATH']
if settings.get('git_exec_path'):
    os.environ['GIT_EXEC_PATH'] = settings['git_exec_path']

def run(args, capture=False):
    result = subprocess.run(args, check=True, text=True, encoding='utf-8',
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)

def validate(audio, expected):
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(audio)], True))
    assert any(s.get('codec_name') == 'mp3' for s in probe['streams']), 'Not MP3'
    duration = float(probe['format']['duration'])
    assert duration > 0 and audio.stat().st_size > 1000, 'Empty audio'
    if expected:
        assert abs(duration - float(expected)) < max(5, float(expected) * .01), 'Truncated audio'
    run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(audio), '-map', '0:a:0', '-f', 'null', '-'])
    return duration

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--video-id')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS'):
        raise RuntimeError('YouTube downloads must run locally')
    if args.limit < 1:
        parser.error('--limit must be positive')
    config = podcast.load_json(podcast.CONFIG_PATH, {})
    episodes = podcast.load_json(podcast.STATE_PATH, [])
    known = {e['id'] for e in episodes}
    repo, site, feed = podcast.public_urls()
    ytdlp = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--js-runtimes',
             'node:' + settings.get('node', shutil.which('node') or 'node')]
    if args.video_id:
        entries = [{'id': args.video_id}]
    else:
        entries = json.loads(run(ytdlp + ['--flat-playlist', '--dump-single-json', config['playlist_url']], True))['entries']
    selected = []
    for entry in entries:
        if entry and entry.get('id') and entry['id'] not in known and entry['id'] not in selected:
            selected.append(entry['id'])
    for video_id in selected[:args.limit]:
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError('Invalid YouTube video ID')
        audio = podcast.WORK / (video_id + '.mp3')
        info_path = podcast.WORK / (video_id + '.info.json')
        if not audio.exists() or not info_path.exists():
            run(ytdlp + ['--no-playlist', '--newline', '--write-info-json', '--ffmpeg-location', str(ROOT / '.tools'),
                         '-f', 'bestaudio/best', '-x', '--audio-format', 'mp3', '--audio-quality', '5',
                         '-o', str(podcast.WORK / '%(id)s.%(ext)s'), 'https://www.youtube.com/watch?v=' + video_id])
        info = podcast.load_json(info_path, {})
        duration = validate(audio, info.get('duration'))
        tag = config['release_tag']
        releases = json.loads(run(['gh', 'api', f'repos/{repo}/releases', '--paginate', '--slurp'], True))
        release = next((r for page in releases for r in page if r['tag_name'] == tag), None)
        if release is None:
            run(['gh', 'release', 'create', tag, '--repo', repo, '--title', 'Podcast media', '--notes', 'Audio files used by the personal RSS feed.', '--latest=false'])
        assets = json.loads(run(['gh', 'release', 'view', tag, '--repo', repo, '--json', 'assets'], True))['assets']
        existing = next((a for a in assets if a['name'] == audio.name), None)
        if existing:
            assert existing['size'] == audio.stat().st_size, 'Existing Release asset has different size; preserved'
        else:
            run(['gh', 'release', 'upload', tag, str(audio), '--repo', repo])
        url = f'https://github.com/{repo}/releases/download/{tag}/{audio.name}'
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(url, timeout=120) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        assert size == audio.stat().st_size and digest.hexdigest() == hashlib.sha256(audio.read_bytes()).hexdigest(), 'Public asset verification failed'
        episodes.append(dict(id=video_id, title=info.get('title') or video_id,
            description=info.get('description') or '', source_url='https://www.youtube.com/watch?v=' + video_id,
            media_url=url, length=size, duration=round(duration), published=podcast.iso_from_metadata(info).isoformat(),
            thumbnail=info.get('thumbnail') or ''))
        save(podcast.STATE_PATH, episodes)
        print(f'Uploaded and verified {video_id}: {duration:.1f} seconds, {size} bytes', flush=True)
    if not episodes:
        raise RuntimeError('No published episodes')
    if selected or not (podcast.DOCS / 'feed.xml').exists():
        podcast.build_feed(config, episodes, site, feed)
        podcast.build_index(config, episodes, feed)
    if args.publish:
        run(['git', 'add', 'data/episodes.json', 'docs/feed.xml', 'docs/index.html'])
        if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode:
            run(['git', 'commit', '-m', 'Update podcast feed from local sync'])
        run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', 'HEAD:main'])

if __name__ == '__main__':
    main()
