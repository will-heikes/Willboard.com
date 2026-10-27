#!/usr/bin/env python3
"""Download album and single covers for the Willboard Awards and albums page (and, optionally, every chart song).

Run from the Willboard.com repo folder (next to data.json and awards.json):
    python3 tools/fetch_covers.py                 # every album and song in awards.json, every album in albums.json
    python3 tools/fetch_covers.py --all-songs     # also every song that has charted
    python3 tools/fetch_covers.py --redo "Carly Pearce - Hummingbird"
    python3 tools/fetch_covers.py --tidy-only     # just rename covers you uploaded

Covers are saved as images/covers/<artist>--<title>.jpg, the path index.html looks for.
Deezer is tried first, then the iTunes store. Every lookup is written to
images/covers/_matches.csv so odd matches can be checked by eye.

To add or replace a cover yourself, upload "<Artist> - <Title>.jpg" (e.g.
"Carly Pearce - Hummingbird.jpg") into images/covers/. The tidy step renames it.
Covers that already exist are never overwritten unless named in --redo.
"""
import argparse
import csv
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from fetch_artist_photos import get, norm, primary_artist, slugify

OUT = os.path.join('images', 'covers')
DEEZER = 'https://api.deezer.com/search/{kind}?limit=10&q={q}'
ITUNES = 'https://itunes.apple.com/search?country=US&limit=10&entity={kind}&term={q}'


def display_title(name, artist):
    """Drop Will's tell-apart suffix ("Heaven - Niall"), as displayTitle() in index.html does."""
    m = re.fullmatch(r'(.+?) - ([^-]+)', name or '')
    return m.group(1) if m and norm(m.group(2)) and norm(m.group(2)) in norm(artist) else name


def cover_name(artist, title):
    # Must match coverUrl() in index.html
    return f'{slugify(artist)}--{slugify(title)}.jpg'


def clean(title):
    """Title without edition tags, for matching: 'Hummingbird (Deluxe)' -> 'hummingbird'."""
    # "(Taylor's Version)" is a different album from the original, so it stays in
    t = re.sub(r"\s*[\(\[](?![^)\]]*taylor)[^)\]]*(deluxe|edition|version|remaster|expanded|feat\.?|ft\.?|with)[^)\]]*[\)\]]", '', title, flags=re.I)
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    return norm(t)


def same_artist(found, wanted):
    f, w = norm(found), norm(wanted)
    return bool(f) and (w in f or f in w)


def from_deezer(kind, artist, title):
    q = urllib.parse.quote(f'artist:"{artist}" {"album" if kind == "album" else "track"}:"{title}"')
    hits = json.loads(get(DEEZER.format(kind='album' if kind == 'album' else 'track', q=q))).get('data', [])
    for h in hits:
        name = h.get('title', '')
        if clean(name) == clean(title) and same_artist(h.get('artist', {}).get('name', ''), artist):
            pic = (h if kind == 'album' else h.get('album', {})).get('cover_xl') or ''
            if pic and '/cover//' not in pic:
                return pic.replace('1000x1000', '600x600'), f'Deezer: {name}'
    return None


def from_itunes(kind, artist, title):
    q = urllib.parse.quote(f'{artist} {title}')
    hits = json.loads(get(ITUNES.format(kind='album' if kind == 'album' else 'song', q=q))).get('results', [])
    for h in hits:
        name = h.get('collectionName' if kind == 'album' else 'trackName', '')
        if clean(name) == clean(title) and same_artist(h.get('artistName', ''), artist):
            art = h.get('artworkUrl100', '')
            if art:
                return art.replace('100x100bb', '600x600bb'), f'iTunes: {name}'
    return None


UPLOAD = re.compile(r'^(.+?)\s+-\s+(.+)\.(jpe?g|png|webp)$', re.I)


def tidy():
    """Rename uploaded '<Artist> - <Title>.jpg' files to the site's naming."""
    for f in sorted(os.listdir(OUT)):
        m = UPLOAD.match(f)
        if m:
            target = cover_name(m.group(1), m.group(2))
            os.replace(os.path.join(OUT, f), os.path.join(OUT, target))
            print(f'renamed {f} -> {target}')


def wanted(all_songs):
    """(kind, artist, title) for every award album and song, plus chart songs if asked."""
    data = json.load(open('data.json', encoding='utf-8'))
    acts = frozenset(a['name'] for a in data['artists'])
    awards = json.load(open('awards.json', encoding='utf-8'))
    items = {}
    for show in awards.values():
        for n in show:
            artist = primary_artist(n.get('artist') or '', acts)
            if not artist:
                continue
            if n.get('album'):
                items[cover_name(artist, n['album'])] = ('album', artist, n['album'])
            if n.get('song'):
                items.setdefault(cover_name(artist, n['song']), ('song', artist, n['song']))
    # Every album with a charted song (albums.json, from tools/import_itunes.py)
    # and pop_albums.json (tools/build_pop_albums.py)
    for f in ('albums.json', 'pop_albums.json'):
        if not os.path.exists(f):
            continue
        for al in json.load(open(f, encoding='utf-8')):
            artist = primary_artist(al['artist'], acts)
            if artist:
                items.setdefault(cover_name(artist, al['name'].strip()), ('album', artist, al['name'].strip()))
                # Songs off a deluxe edition show that edition's cover
                for ed in al.get('deluxe', {}).values():
                    items.setdefault(cover_name(artist, ed.strip()), ('album', artist, ed.strip()))
    if all_songs:
        for s in data['songs']:
            artist, title = primary_artist(s['artistName'], acts), display_title(s['name'], s['artistName'])
            items.setdefault(cover_name(artist, title), ('song', artist, title))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all-songs', action='store_true')
    ap.add_argument('--redo', default='', help='"Artist - Title" entries to fetch again, comma separated')
    ap.add_argument('--tidy-only', action='store_true')
    ap.add_argument('--minutes', type=float, default=0, help='stop after this long, so a long run still saves what it got')
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    tidy()
    if args.tidy_only:
        return
    redo = {cover_name(*e.split(' - ', 1)) for e in args.redo.split(',') if ' - ' in e}

    items = wanted(args.all_songs)
    rows, got, start = [], 0, time.time()
    # Albums first: they're the ones the albums page needs
    for i, (fname, (kind, artist, title)) in enumerate(sorted(items.items(), key=lambda x: (x[1][0] != 'album', x[0])), 1):
        path = os.path.join(OUT, fname)
        if os.path.exists(path) and fname not in redo:
            continue
        if args.minutes and time.time() - start > args.minutes * 60:
            print(f'\nOut of time at {i}/{len(items)}; run again to fetch the rest')
            break
        hit, status = None, 'not found'
        for source in (from_deezer, from_itunes):
            try:
                hit = source(kind, artist, title)
            except Exception as e:
                status = f'lookup failed: {e}'
            if source is from_itunes:
                time.sleep(3)  # iTunes allows about 20 lookups a minute
            if hit:
                break
        if hit:
            try:
                open(path, 'wb').write(get(hit[0]))
                status, got = hit[1], got + 1
            except Exception as e:
                status = f'download failed: {e}'
        rows.append([kind, artist, title, fname, status])
        print(f'[{i}/{len(items)}] {artist} - {title}: {status}')
        time.sleep(0.15)

    with open(os.path.join(OUT, '_matches.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['kind', 'artist', 'title', 'file', 'result'])
        w.writerows(rows)
    print(f'\nDone. {got} new covers, {len(rows) - got} not found (see {OUT}/_matches.csv)')


if __name__ == '__main__':
    main()
