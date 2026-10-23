#!/usr/bin/env python3
"""Match every charted song to a Deezer track, so the site can play a 30-second preview.

Run from the Willboard.com repo folder (the "Fetch artist photos" Action runs it with "previews" ticked):
    python3 tools/fetch_previews.py [--redo "Song title,Other song"] [--minutes 100]

--redo missing tries again every song that had no match.

Deezer's preview links expire after a while, so this only stores each song's Deezer track id in
previews.json ({songId: trackId}, 0 when nothing matched). The site asks Deezer for a fresh preview
link when someone presses play. Songs already in the file are skipped, so a run that stops early
carries on where it left off. To fix a wrong match, put the right Deezer track id in FIX.
"""
import argparse
import json
import os
import re
import time
import urllib.parse

from fetch_artist_photos import get, primary_artist
from fetch_covers import clean, display_title, same_artist

OUT = 'previews.json'
SEARCH = 'https://api.deezer.com/search/track?limit=25&q={q}'
# songId: Deezer track id, for matches the search gets wrong
FIX = {}
# Live takes, remixes and the like lose to the studio recording
ALT = re.compile(r'\b(live|remix|acoustic|instrumental|karaoke|demo|sped up|slowed|version)\b', re.I)


def find(artist, title):
    want = clean(title)
    for q in (f'artist:"{artist}" track:"{title}"', f'{artist} {title}'):
        hits = json.loads(get(SEARCH.format(q=urllib.parse.quote(q)))).get('data', [])
        ok = [h for h in hits if h.get('preview') and same_artist(h.get('artist', {}).get('name', ''), artist)
              and clean(h.get('title_short') or h.get('title', '')) == want]
        if ok:
            # Keep Deezer's order (most popular first), but a studio take beats a live one or a remix
            ok.sort(key=lambda h: bool(ALT.search(h.get('title', ''))) and not ALT.search(title))
            return ok[0]['id']
        time.sleep(0.12)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redo', default='')
    ap.add_argument('--minutes', type=float, default=0)
    args = ap.parse_args()
    redo = {t.strip().lower() for t in args.redo.split(',') if t.strip()}
    data = json.load(open('data.json', encoding='utf-8'))
    acts = frozenset(a['name'] for a in data['artists'])
    found = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    start, done = time.time(), 0
    for i, s in enumerate(data['songs'], 1):
        artist, title = primary_artist(s['artistName'], acts), display_title(s['name'], s['artistName'])
        if s['id'] in FIX:
            found[s['id']] = FIX[s['id']]
            continue
        if s['id'] in found and title.lower() not in redo and not ('missing' in redo and not found[s['id']]):
            continue
        if args.minutes and time.time() - start > args.minutes * 60:
            print(f'Out of time at {i}/{len(data["songs"])}; run again for the rest')
            break
        try:
            found[s['id']] = find(artist, title)
        except Exception as e:
            print(f'[{i}] {artist} - {title}: lookup failed: {e}')
            continue
        done += 1
        print(f'[{i}/{len(data["songs"])}] {artist} - {title}: {found[s["id"]] or "not found"}')
        if done % 50 == 0:
            json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=0, sort_keys=True)
        time.sleep(0.12)
    json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=0, sort_keys=True)
    print(f'\nDone. {sum(1 for v in found.values() if v)} of {len(found)} songs have a preview.')


if __name__ == '__main__':
    main()
