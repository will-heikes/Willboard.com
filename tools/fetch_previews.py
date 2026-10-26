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
                 r'radio release|radio special|track by track|interview|story behind|behind the song|spoken|'
                 # "Remix" alone missed "(Almighty Club Mix)", "(Dyro Radio Edit)", "(A Cappella)" and "... (Remixes)"
                 r'remixes|club mix|radio mix|dub mix|mix edit|radio edit|club edit|a cappella|acapella|extended mix)\b', re.I)
# Edition names that are still the studio recording
EDITIONS = re.compile(r"taylor'?s version|deluxe( edition| version)?|expanded edition|platinum edition|remaster(ed)?", re.I)


# Acts Deezer files under another name
ALIAS = {'Lady A': 'Lady Antebellum', 'Dixie Chicks': 'The Chicks', 'The Chicks': 'Dixie Chicks'}
# "We Can't Be Friends (wait for your love)" is the song Will charted as "We Can't Be Friends"
# Talk rather than the song: never played, even when it's all Deezer has
SPOKEN = re.compile(r'\b(commentary|voice memo|interview|track by track|story behind|behind the song|spoken|radio release special|radio special)\b', re.I)
ITUNES = 'https://itunes.apple.com/search?entity=song&country=us&limit=50&term={q}'
# A re-recording (Taylor's Version) is only played when that's what Will charted, or when it's the only
# recording there is (the From The Vault songs); otherwise the original plays, the one that charted (Will)
TV = re.compile(r"taylor['’]?s version", re.I)
PARENS = re.compile(r'\s*[(\[][^)\]]*[)\]]')


def find(artist, title, album=''):
    """The song's Deezer track id, else an Apple preview link, else a Deezer remix or edit. Never talk."""
    spare = redo = 0
    for name in (artist, ALIAS.get(artist)):
        if not name:
            continue
        best, other, again = search(name, title, album)
        if best:
            return best
        spare, redo = spare or other, redo or again
    # Deezer has Taylor's originals only as commentary editions, so Apple's original comes before
    # Deezer's re-recording
    if redo:
        for name in (artist, ALIAS.get(artist)):
            if name and (url := itunes(name, title, album, original=True)):
                return url
        return redo
    # Deezer has no preview of the studio recording for some catalogues (Big Machine's offers only its
    # commentary editions, Lady A and Keith Urban none at all), so Apple's 30-second clip stands in
    for name in (artist, ALIAS.get(artist)):
        if name and (url := itunes(name, title, album)):
            return url
    return spare


def named(want):
    return lambda t: clean(t) == want or clean(PARENS.sub('', t)) == want


def search(artist, title, album=''):
    """(studio recording's Deezer id, a remix or edit's id as a last resort, a re-recording's id)"""
    want, who = clean(PARENS.sub('', title)) or clean(title), norm(artist)
    match = named(want)
    spare = redo = 0
    for q in (f'artist:"{artist}" track:"{title}"', f'{artist} {title}'):
        hits = json.loads(get(SEARCH.format(q=urllib.parse.quote(q)))).get('data', [])
        hits = [h for h in hits if h.get('preview') and match(h.get('title_short') or h.get('title', ''))]
        # The act itself, not a tribute band or a karaoke label that has its name in theirs. A loose
        # match is only for Will's spellings ("Ariana Grade"), and never an act named like a cover act
        ok = [h for h in hits if norm(h.get('artist', {}).get('name', '')) == who] or \
             [h for h in hits if same_artist(h.get('artist', {}).get('name', ''), artist) and not ALT.search(h.get('artist', {}).get('name', ''))]
        # Deezer keeps "(Commentary)" or "(Live)" in title_version, so check the whole title and the album
        full = lambda h: f"{h.get('title', '')} {h.get('title_version', '')} {h.get('album', {}).get('title', '')}"
        studio = [h for h in ok if not ALT.search(full(h)) or ALT.search(title)]
        # A recording on the song's own album (or its Taylor's Version, deluxe...) beats a lookalike
        # upload credited to the act, which is how a cover of "Mine" slipped through (Will). Taylor
        # Swift's "Big Machine Radio Release Special" albums share the album's name but are
        # commentary, so the album title is checked too, once edition names are taken out (Will)
        own = [h for h in ok if album and clean(h.get('album', {}).get('title', '')).startswith(clean(album))
               and (not ALT.search(EDITIONS.sub('', full(h))) or ALT.search(title))]
        pool = own or studio
        first = [h for h in pool if TV.search(title) or not TV.search(full(h))]
        if first:
            return note(max(first, key=lambda h: h.get('rank', 0))), 0, 0
        if pool and not redo:
            redo = note(max(pool, key=lambda h: h.get('rank', 0)))
        # A remix or radio edit will do if nothing better turns up; someone talking never will
        rest = [h for h in ok if not SPOKEN.search(full(h))]
        if rest and not spare:
            spare = note(max(rest, key=lambda h: h.get('rank', 0)))
        time.sleep(0.12)
    return 0, spare, redo


def note(h):
    picked[h['id']] = f"{h.get('title')} {h.get('title_version', '')}".strip() + f" | {h.get('artist', {}).get('name')} | {h.get('album', {}).get('title')}"
    print(f"    -> {picked[h['id']]}")
    return h['id']


def itunes(artist, title, album='', original=False):
    want, who = clean(PARENS.sub('', title)) or clean(title), norm(artist)
    match = named(want)
    hits = []
    # Apple sometimes answers a busy minute with an empty list rather than an error, so an empty
    # answer is asked again after a pause, then once more by title alone
    for q, wait in ((f'{artist} {title}', 3), (f'{artist} {title}', 20), (title, 3)):
        time.sleep(wait)  # Apple allows about 20 searches a minute
        try:
            hits = json.loads(get(ITUNES.format(q=urllib.parse.quote(q)))).get('results', [])
        except Exception as e:
            print(f'    itunes lookup failed: {e}')
        if any(match(h.get('trackName', '')) and (norm(h.get('artistName', '')) == who
               or same_artist(h.get('artistName', ''), artist)) for h in hits):
            break
    full = lambda h: f"{h.get('trackName', '')} {h.get('collectionName', '')}"
    seen = hits
    hits = [h for h in hits if h.get('previewUrl') and match(h.get('trackName', ''))
            and (norm(h.get('artistName', '')) == who or same_artist(h.get('artistName', ''), artist))
            and (not ALT.search(EDITIONS.sub('', full(h))) or ALT.search(title))]
    if not TV.search(title):
        hits = sorted(hits, key=lambda h: bool(TV.search(full(h))))
        if original:
            hits = [h for h in hits if not TV.search(full(h))]
    if not hits:
        # What Apple did answer, to see why nothing matched
        print(f'    apple: no match in {len(seen)}: ' + '; '.join(f"{h.get('trackName')} | {h.get('artistName')} | {h.get('collectionName')}" for h in seen[:4]))
        return None
    own = [h for h in hits if album and clean(h.get('collectionName', '')).startswith(clean(album))]
    h = (own or hits)[0]
    picked[h['previewUrl']] = f"{h.get('trackName')} | {h.get('artistName')} | {h.get('collectionName')} (Apple)"
    print(f"    -> {picked[h['previewUrl']]}")
    return h['previewUrl']


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
