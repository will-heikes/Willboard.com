#!/usr/bin/env python3
"""Download a photo for every Willboard artist from Deezer.

Run from the Willboard.com repo folder (next to data.json):
    python3 fetch_artist_photos.py

Saves images/artists/<slug>.jpg, the path index.html looks for, and writes
images/artists/_matches.csv so odd matches can be checked by eye.
Already-downloaded photos are skipped, so it is safe to re-run.
"""
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

OUT = os.path.join('images', 'artists')
API = 'https://api.deezer.com/search/artist?limit=5&q='


# Must match primaryArtist() and slugify() in index.html
def primary_artist(name):
    return re.split(r',| & | ft\.? | feat\.? | x | with ', name or '', flags=re.I)[0].strip()


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


def main():
    data = json.load(open('data.json', encoding='utf-8'))
    names = sorted({primary_artist(s['artistName']) for s in data['songs']} - {''})
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for i, name in enumerate(names, 1):
        slug = slugify(name)
        path = os.path.join(OUT, slug + '.jpg')
        if not slug:
            continue
        if os.path.exists(path):
            rows.append([name, slug, '', '', 'already had'])
            continue
        try:
            hits = json.loads(get(API + urllib.parse.quote(name))).get('data', [])
        except Exception as e:
            rows.append([name, slug, '', '', f'lookup failed: {e}'])
            continue
        # Prefer an exact name match, otherwise Deezer's top result
        exact = [h for h in hits if norm(h['name']) == norm(name)]
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
    bad = [r for r in rows if r[4] not in ('ok', 'already had')]
    print(f'\nDone. {len(rows) - len(bad)} photos ready, {len(bad)} to check in {OUT}/_matches.csv')


if __name__ == '__main__':
    sys.exit(main())
