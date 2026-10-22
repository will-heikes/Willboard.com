#!/usr/bin/env python3
"""Take all-time Hot 20 play counts from Will's iTunes library export.

    python3 tools/import_itunes.py "Music.xml"

Run from the repo folder. Matches each Hot 20 song in data.json to the library by
title and artist, writes itunes_plays.tsv (song, artist, plays) for build_data.py to
merge, and raises itunesPlays in data.json right away. A count only ever goes up, so
a song keeps its larger figure if the library's is lower (a deleted and re-added track).
"""
import csv
import json
import plistlib
import re
import sys
from collections import defaultdict

from add_week import norm

OUT = 'itunes_plays.tsv'
# "(feat. X)", "[with X]", "- Single Version" and the like aren't part of the title
EXTRA = re.compile(r'\s*[\(\[](feat|ft|with|from|radio|single|album|edit|remaster|explicit|clean)[^\)\]]*[\)\]]'
                   r'|\s+-\s+(single|radio|album)\b.*$', re.I)


def bare(title):
    """Looser key: no brackets at all ("Taylor's Version", "Acoustic Version") and no leading article."""
    return re.sub(r'^(a|the)', '', norm(re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', title)))


def lead(artist):
    return norm(re.split(r',| & | and | ft\.? | feat\.? | featuring | x | with |;', artist or '', flags=re.I)[0])


def main():
    lib = plistlib.load(open(sys.argv[1], 'rb'))
    tracks, loose = defaultdict(list), defaultdict(list)  # title -> [(artist text, plays)]
    for t in lib['Tracks'].values():
        if t.get('Name'):
            v = (norm(f"{t.get('Artist', '')} {t.get('Album Artist', '')}"), t.get('Play Count', 0))
            tracks[norm(EXTRA.sub('', t['Name']))].append(v)
            loose[bare(t['Name'])].append(v)

    data = json.load(open('data.json', encoding='utf-8'))
    rows, missing, raised = [], [], 0
    for s in data['songs']:
        if s['chart'] != 'willboard':
            continue
        # Will's tell-apart suffix ("Heaven - Niall") names the artist, not the title
        m = re.fullmatch(r'(.+?) - (.+)', s['name'])
        title = m.group(1) if m and norm(m.group(2)) in norm(s['artistName']) else s['name']
        who = lead(s['artistName'])
        hits = [p for a, p in tracks.get(norm(EXTRA.sub('', title)), []) if who and who[:8] in a]
        if not hits:
            hits = [p for a, p in loose.get(bare(title), []) if who and who[:8] in a]
        if not hits:
            missing.append(f"{s['name']} - {s['artistName']}")
            continue
        plays = max(hits)  # several copies (single + album): the one Will plays carries the count
        rows.append((s['name'], s['artistName'], plays))
        if plays > (s['itunesPlays'] or 0):
            s['itunesPlays'], raised = plays, raised + 1

    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['song', 'artist', 'plays'])
        w.writerows(sorted(rows))
    json.dump(data, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'{len(rows)} matched, {raised} raised, {len(missing)} not in the library')
    print('\n'.join(sorted(missing)))


if __name__ == '__main__':
    main()
