#!/usr/bin/env python3
"""Match every charted song to a Deezer track, so the site can play a 30-second preview.

Run from the Willboard.com repo folder (the "Fetch artist photos" Action runs it with "previews" ticked):
    python3 tools/fetch_previews.py [--redo "Song title,Other song"] [--minutes 100]

--redo missing tries again every song that had no match; --redo all checks every song again.

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
from fetch_artist_photos import norm
from fetch_covers import clean, display_title, same_artist

OUT = 'previews.json'
# What each match actually is ({songId: "title | artist | album"}), to spot commentary and covers
PICKS = 'preview_picks.json'
picked = {}
SEARCH = 'https://api.deezer.com/search/track?limit=25&q={q}'
# songId: Deezer track id, for matches the search gets wrong
FIX = {}
# Live takes, remixes, commentary tracks, karaoke and covers lose to the studio recording
ALT = re.compile(r'\b(live|remix|acoustic|instrumental|karaoke|demo|sped up|slowed|version|commentary|voice memo|'
                 r'tribute|cover|made famous|originally performed|in the style of|piano|lullaby|8-bit|'
                 r'radio release|radio special|track by track|interview|story behind|behind the song|spoken)\b', re.I)
# Edition names that are still the studio recording
EDITIONS = re.compile(r"taylor'?s version|deluxe( edition| version)?|expanded edition|platinum edition|remaster(ed)?", re.I)


# Acts Deezer files under another name
ALIAS = {'Lady A': 'Lady Antebellum', 'Dixie Chicks': 'The Chicks', 'The Chicks': 'Dixie Chicks'}
# "We Can't Be Friends (wait for your love)" is the song Will charted as "We Can't Be Friends"
PARENS = re.compile(r'\s*[(\[][^)\]]*[)\]]')


def find(artist, title, album=''):
    for name in (artist, ALIAS.get(artist)):
        if name and (hit := search(name, title, album)):
            return hit
    return 0


def search(artist, title, album=''):
    want, who = clean(PARENS.sub('', title)) or clean(title), norm(artist)
    named = lambda t: clean(t) == want or clean(PARENS.sub('', t)) == want
    for q in (f'artist:"{artist}" track:"{title}"', f'{artist} {title}'):
        hits = json.loads(get(SEARCH.format(q=urllib.parse.quote(q)))).get('data', [])
        hits = [h for h in hits if h.get('preview') and named(h.get('title_short') or h.get('title', ''))]
        # The act itself, not a tribute band or a karaoke label that has its name in theirs. A loose
        # match is only for Will's spellings ("Ariana Grade"), and never an act named like a cover act
        ok = [h for h in hits if norm(h.get('artist', {}).get('name', '')) == who] or \
             [h for h in hits if same_artist(h.get('artist', {}).get('name', ''), artist) and not ALT.search(h.get('artist', {}).get('name', ''))]
        # Deezer keeps "(Commentary)" or "(Live)" in title_version, so check the whole title and the album
        full = lambda h: f"{h.get('title', '')} {h.get('title_version', '')} {h.get('album', {}).get('title', '')}"
        studio = [h for h in ok if not ALT.search(full(h)) or ALT.search(title)]
        # A recording on the song's own album (or its Taylor's Version, deluxe...) beats a lookalike
        # upload credited to the act, which is how a cover of "Mine" slipped through (Will)
        # (its album title may say "Taylor's Version", so only the track's own title is checked there)
        # Taylor Swift's "Big Machine Radio Release Special" albums share the album's name but are
        # commentary, so the album title is checked too, once edition names are taken out (Will)
        own = [h for h in ok if album and clean(h.get('album', {}).get('title', '')).startswith(clean(album))
               and (not ALT.search(EDITIONS.sub('', full(h))) or ALT.search(title))]
        if own or studio or ok:
            best = max(own or studio or ok, key=lambda h: h.get('rank', 0))
            picked[best['id']] = f"{best.get('title')} {best.get('title_version', '')}".strip() + f" | {best.get('artist', {}).get('name')} | {best.get('album', {}).get('title')}"
            print(f"    -> {picked[best['id']]}")
            return best['id']
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
    # Each song's album, from Will's library (country) and the pop album lookups
    album = {}
    for f in ('albums.json', 'pop_albums.json'):
        if os.path.exists(f):
            for a in json.load(open(f, encoding='utf-8')):
                for sid in a['songs']:
                    album.setdefault(sid, a['name'])
    start, done = time.time(), 0
    for i, s in enumerate(data['songs'], 1):
        artist, title = primary_artist(s['artistName'], acts), display_title(s['name'], s['artistName'])
        if s['id'] in FIX:
            found[s['id']] = FIX[s['id']]
            continue
        if s['id'] in found and 'all' not in redo and title.lower() not in redo and not ('missing' in redo and not found[s['id']]):
            continue
        if args.minutes and time.time() - start > args.minutes * 60:
            print(f'Out of time at {i}/{len(data["songs"])}; run again for the rest')
            break
        try:
            found[s['id']] = find(artist, title, album.get(s['id'], ''))
        except Exception as e:
            print(f'[{i}] {artist} - {title}: lookup failed: {e}')
            continue
        done += 1
        print(f'[{i}/{len(data["songs"])}] {artist} - {title}: {found[s["id"]] or "not found"}')
        if done % 50 == 0:
            json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=0, sort_keys=True)
        time.sleep(0.12)
    json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=0, sort_keys=True)
    picks = json.load(open(PICKS, encoding='utf-8')) if os.path.exists(PICKS) else {}
    for sid, tid in found.items():
        if tid in picked:
            picks[sid] = picked[tid]
        elif not tid:
            picks.pop(sid, None)
    json.dump(picks, open(PICKS, 'w', encoding='utf-8'), indent=0, sort_keys=True, ensure_ascii=False)
    print(f'\nDone. {sum(1 for v in found.values() if v)} of {len(found)} songs have a preview.')


if __name__ == '__main__':
    main()
