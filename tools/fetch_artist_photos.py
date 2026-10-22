#!/usr/bin/env python3
"""Download a photo for every Willboard artist from Deezer.

Run from the Willboard.com repo folder (next to data.json):
    python3 fetch_artist_photos.py

Saves images/artists/<slug>.jpg, the path index.html looks for, and writes
images/artists/_matches.csv so odd matches can be checked by eye.
Already-downloaded photos are skipped, so it is safe to re-run.

    --redo "Ronnie Dunn,Maddie & Tae"   download these again, replacing the old photo
    --wiki "Ronnie Dunn"                take these from Wikipedia instead of Deezer
    --index-only                        just tidy uploaded era photos and rebuild _years.json

Era photos: upload "<Artist> <year>.jpg" (e.g. "Carrie Underwood 2016.jpg") into
images/artists/. The index step renames it to carrie-underwood-2016.jpg and lists
it in _years.json, and the site uses the photo nearest each chart or awards year.
"""
import csv
import json
import os
import re
import subprocess
import sys
import time
import argparse
import unicodedata
import urllib.parse
import urllib.request

OUT = os.path.join('images', 'artists')
API = 'https://api.deezer.com/search/artist?limit=5&q='
WIKI = 'https://en.wikipedia.org/api/rest_v1/page/summary/'
# What to search Deezer for when the act goes by a stylized name there (Will spells it Pink)
SEARCH_AS = {'Pink': 'P!nk'}


# Must match primaryArtist() and slugify() in index.html.
# Acts with "&" in their own name (Maddie & Tae) stay whole.
def primary_artist(name, acts=frozenset()):
    first = re.split(r',| ft\.? | feat\.? | with ', name or '', flags=re.I)[0].strip()
    return first if first in acts else re.split(r' & | x ', first, flags=re.I)[0].strip()


def slugify(name):
    s = name.lower().replace("'", '').replace('’', '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def norm(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'willboard-photos/1.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def wiki_photo(name):
    page = json.loads(get(WIKI + urllib.parse.quote(name.replace(' ', '_'))))
    return (page.get('originalimage') or page.get('thumbnail') or {}).get('source')


ERA = re.compile(r'^(.*?)[\s_-]+((?:19|20)\d\d)\.(jpe?g|png|webp)$', re.I)


def committed(path):
    """When git last committed this file (0 if never), to tell which upload is newest."""
    out = subprocess.run(['git', 'log', '-1', '--format=%ct', '--', path], capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def index_eras():
    """Rename uploaded era photos to <slug>-<year>.jpg and list them in _years.json."""
    # Acts with a year in their name (The 1975) are main photos, not era photos
    data = json.load(open('data.json', encoding='utf-8'))
    acts = frozenset(a['name'] for a in data['artists'])
    known = {slugify(primary_artist(s['artistName'], acts)) for s in data['songs']}
    found = {}
    for f in os.listdir(OUT):
        m = ERA.match(f)
        if m and slugify(os.path.splitext(f)[0]) not in known:
            found.setdefault((slugify(m.group(1)), int(m.group(2))), []).append(f)
    years = {}
    for (slug, year), files in sorted(found.items()):
        target = f'{slug}-{year}.jpg'
        # The same artist and year uploaded more than once (a .jpg and a .webp, say):
        # the most recently committed file wins, and an upload beats the tidied copy
        keep = max(files, key=lambda f: (committed(os.path.join(OUT, f)), f != target))
        for f in files:
            if f != keep and f != target:
                os.remove(os.path.join(OUT, f))
                print(f'dropped {f}, older than {keep}')
        if keep != target:
            os.replace(os.path.join(OUT, keep), os.path.join(OUT, target))
            print(f'renamed {keep} -> {target}')
        years.setdefault(slug, []).append(year)
    with open(os.path.join(OUT, '_years.json'), 'w', encoding='utf-8') as fh:
        json.dump({k: sorted(set(v)) for k, v in sorted(years.items())}, fh, indent=0)
    print(f'{sum(len(v) for v in years.values())} era photos for {len(years)} artists')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redo', default='')
    ap.add_argument('--wiki', default='')
    ap.add_argument('--index-only', action='store_true')
    args = ap.parse_args()
    split = lambda s: {n.strip() for n in s.split(',') if n.strip()}
    redo, wiki = split(args.redo), split(args.wiki)
    os.makedirs(OUT, exist_ok=True)
    if args.index_only:
        return index_eras()

    data = json.load(open('data.json', encoding='utf-8'))
    acts = frozenset(a['name'] for a in data['artists'])
    names = sorted({primary_artist(s['artistName'], acts) for s in data['songs']} - {''})
    rows = []
    for i, name in enumerate(names, 1):
        slug = slugify(name)
        path = os.path.join(OUT, slug + '.jpg')
        if not slug:
            continue
        if os.path.exists(path) and name not in redo | wiki:
            rows.append([name, slug, '', '', 'already had'])
            continue
        if name in wiki:
            try:
                url = wiki_photo(name)
                if not url:
                    raise ValueError('no lead image on Wikipedia')
                open(path, 'wb').write(get(url))
                rows.append([name, slug, 'Wikipedia', '', 'ok'])
                print(f'[{i}/{len(names)}] {name} -> Wikipedia')
            except Exception as e:
                rows.append([name, slug, '', '', f'wikipedia failed: {e}'])
            continue
        try:
            query = SEARCH_AS.get(name, name)
            hits = json.loads(get(API + urllib.parse.quote(query))).get('data', [])
        except Exception as e:
            rows.append([name, slug, '', '', f'lookup failed: {e}'])
            continue
        # Prefer an exact name match (the most-followed one), otherwise Deezer's top result
        exact = sorted([h for h in hits if h['name'] == query or norm(h['name']) == norm(name) and name not in SEARCH_AS],
                       key=lambda h: -(h.get('nb_fan') or 0))
        hit = (exact or hits or [None])[0]
        if not hit or 'artist/' not in (hit.get('picture_xl') or '') or hit['picture_xl'].endswith('//1000x1000-000000-80-0-0.jpg'):
            rows.append([name, slug, hit['name'] if hit else '', '', 'no photo'])
            continue
        status = 'ok' if exact else 'CHECK: name differs'
        try:
            img = get(hit['picture_xl'].replace('1000x1000', '500x500'))
            open(path, 'wb').write(img)
        except Exception as e:
            status = f'download failed: {e}'
        rows.append([name, slug, hit['name'], hit.get('nb_fan', ''), status])
        print(f'[{i}/{len(names)}] {name} -> {hit["name"]} ({status})')
        time.sleep(0.15)  # stay well under Deezer's rate limit

    with open(os.path.join(OUT, '_matches.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['willboard_name', 'file', 'deezer_name', 'deezer_fans', 'status'])
        w.writerows(rows)
    index_eras()
    bad = [r for r in rows if r[4] not in ('ok', 'already had')]
    print(f'\nDone. {len(rows) - len(bad)} photos ready, {len(bad)} to check in {OUT}/_matches.csv')


if __name__ == '__main__':
    sys.exit(main())
