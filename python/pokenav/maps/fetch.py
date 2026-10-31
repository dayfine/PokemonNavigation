"""Downloads a Bulbapedia map image.

The wiki's pages sit behind a bot check, but its file archive serves an
upload by the MediaWiki hash path: /media/upload/<h0>/<h0h1>/<name>, where h
is the MD5 of the file name with spaces as underscores.
"""
import hashlib
import urllib.request
from pathlib import Path

ARCHIVE = 'https://archives.bulbagarden.net/media/upload'


def archive_url(name):
    name = name.replace(' ', '_')
    digest = hashlib.md5(name.encode('utf-8')).hexdigest()
    return f'{ARCHIVE}/{digest[0]}/{digest[:2]}/{name}'


def fetch(name, out_dir, opener=urllib.request.urlopen):
    out = Path(out_dir) / name.replace(' ', '_')
    if out.exists():
        return out
    request = urllib.request.Request(archive_url(name), headers={'User-Agent': 'Mozilla/5.0 (pokenav.maps)'})
    with opener(request) as response:
        data = response.read()
    if not data.startswith(b'\x89PNG'):
        raise ValueError(f'{name}: not a PNG (got {data[:15]!r})')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out
