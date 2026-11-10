#!/usr/bin/env python3
"""Find the right 30-second clip for every song in swizzle.json (Taylor Swift Rankings).

Run from the Willboard.com repo folder (the "Fetch artist photos" Action runs it with "swizzle" ticked):
    python3 tools/fetch_swizzle_previews.py [--redo all|"Song title,Other song"] [--minutes 100]

Will's rules (2026-11-10): the ORIGINAL recording plays, except for songs he ranked as Taylor's Version
(their album is a Taylor's Version album, which covers the vault songs); never an acoustic, live, remix
or other alternate take unless the song's own title says so. The matching is fetch_previews.find(), the
same one the charts use: Deezer's studio track, else Apple's 30-second preview (Deezer only has Taylor's
Big Machine originals as commentary editions, so most originals come from Apple).

Writes swizzle_previews.json ({song key: Deezer id or Apple preview URL, 0 when nothing matched}) and
swizzle_preview_picks.json (what each match is). tools/build_swizzle.py takes clips from it first.
To fix a wrong match, put the right Deezer id or "apple:<track id>" in FIX.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import fetch_previews as fp  # noqa: E402
from fetch_artist_photos import get  # noqa: E402

OUT, PICKS = 'swizzle_previews.json', 'swizzle_preview_picks.json'
# Apple sells the debut album as "Taylor Swift (Bonus Track Version)": still the studio recording
fp.EDITIONS = re.compile(fp.EDITIONS.pattern + r"|bonus track( version)?", re.I)
FIX = {}
TV = re.compile(r"taylor['’]?s version", re.I)
TEN = re.compile(r'10 minute', re.I)


def wanted(s):
    """(artist, title, album) to search for: Taylor's Version only when Will ranked that version."""
    artist = re.split(r'\s+(?:feat\.?|ft\.?|featuring|&|with)\s+|,\s*', s['a'], flags=re.I)[0].strip()
    title, album = s['t'], s.get('al') or ''
    if TV.search(album) and not TV.search(title):
        title += " (Taylor's Version)"
    return artist, title, album


FEAT = re.compile(r'\((?:feat\.?|ft\.?|featuring)\s+([^)]*)\)', re.I)


def right_cut(title, pick):
    """Is the pick the take Will ranked? find() falls back to a live take or remix when nothing else turns
    up (Long Live came back as Speak Now World Tour Live), the 10 Minute Version and the 5-minute song
    share a name once brackets go, and so do Karma and Karma (feat. Ice Spice)."""
    pick = pick or ''
    if bool(TEN.search(title)) != bool(TEN.search(pick)):
        return False
    # Only the words around the song's name count: "Long Live" is not a live take
    bare = fp.PARENS.sub('', title).strip()
    rest = re.sub(re.escape(bare), '', pick, count=1, flags=re.I).replace('10 Minute Version', '')
    tags = ' '.join(re.findall(r'[(\[]([^)\]]*)', title)).replace('10 Minute Version', '')
    if fp.ALT.search(fp.EDITIONS.sub('', rest)) and not fp.ALT.search(tags):
        return False
    feat = FEAT.search(title)
    return not feat or feat.group(1).split()[0].lower() in pick.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redo', default='')
    ap.add_argument('--minutes', type=float, default=0)
    args = ap.parse_args()
    redo = {t.strip().lower() for t in args.redo.split(',') if t.strip()}
    songs = json.load(open('swizzle.json', encoding='utf-8'))['songs']
    found = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    picks = json.load(open(PICKS, encoding='utf-8')) if os.path.exists(PICKS) else {}
    start = time.time()
    for i, (k, s) in enumerate(sorted(songs.items()), 1):
        if k in found and 'all' not in redo and s['t'].lower() not in redo and not ('missing' in redo and not found[k]):
            continue
        if args.minutes and time.time() - start > args.minutes * 60:
            print(f'Out of time at {i}/{len(songs)}; run again for the rest')
            break
        artist, title, album = wanted(s)
        if k in FIX:
            fix = FIX[k]
            if str(fix).startswith('apple:'):
                hit = (json.loads(get(fp.LOOKUP.format(cc='us', id=fix[6:]))).get('results') or [{}])[0]
                fix = hit.get('previewUrl') or 0
                if fix:
                    fp.picked[fix] = f"{hit.get('trackName')} | {hit.get('artistName')} | {hit.get('collectionName')} (Apple)"
            found[k] = fix
        else:
            try:
                fp.picked.clear()
                tid = fp.find(artist, title, album)
                # The wrong length of All Too Well: ask again with the cut spelled out in full
                if tid and not right_cut(title, fp.picked.get(tid)):
                    print('    not the take Will ranked, trying Apple')
                    tid = fp.itunes(artist, title, album, original=not TV.search(title)) or 0
                    if tid and not right_cut(title, fp.picked.get(tid)):
                        tid = 0
                found[k] = tid
            except Exception as e:
                print(f'[{i}] {title}: lookup failed: {e}')
                continue
        if found[k] in fp.picked:
            picks[k] = fp.picked[found[k]]
        elif not found[k]:
            picks.pop(k, None)
        print(f'[{i}/{len(songs)}] {artist} - {title} ({album}): {picks.get(k, "not found")}')
        json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=0, sort_keys=True)
        json.dump(picks, open(PICKS, 'w', encoding='utf-8'), indent=0, sort_keys=True, ensure_ascii=False)
        time.sleep(0.12)
    print(f'\nDone. {sum(1 for v in found.values() if v)} of {len(songs)} songs have a clip.')


if __name__ == '__main__':
    main()
