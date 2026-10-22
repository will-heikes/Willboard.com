#!/usr/bin/env python3
"""Take all-time Hot 20 play counts from Will's iTunes library export.

    python3 tools/import_itunes.py "Music.xml"

Run from the repo folder. Matches each Hot 20 song in data.json to the library by
title and artist, writes itunes_plays.tsv (song, artist, plays) for build_data.py to
merge, and raises itunesPlays in data.json right away. A count only ever goes up, so
a song keeps its larger figure if the library's is lower (a deleted and re-added track).

Also writes albums.json: every album holding a charted song (Hot 20 or Pop 10), with
the plays of all its tracks added together for album certifications. Deluxe and
Taylor's Version editions count with the original, which names the album and gives
it its cover; a song first released on a Taylor's Version (a vault track) keeps
that edition's name. Singles and compilations are left out. Each album also lists its
album cuts: tracks that never charted but have CUT_MIN plays or more (all editions together).
"""
import csv
import json
import plistlib
import re
import sys
from collections import defaultdict

from add_week import norm

OUT, ALBUMS = 'itunes_plays.tsv', 'albums.json'
CUT_MIN = 0  # plays for a non-charting track to show on its album (Will: show them all)
# "(feat. X)", "[with X]", "- Single Version" and the like aren't part of the title
EXTRA = re.compile(r'\s*[\(\[](feat|ft|with|from|radio|single|album|edit|remaster|explicit|clean)[^\)\]]*[\)\]]'
                   r'|\s+-\s+(single|radio|album)\b.*$', re.I)


def bare(title):
    """Looser key: no brackets ("Taylor's Version", "Acoustic Version"), no leading article, "Comin'" = "Coming"."""
    title = re.sub(r"in['’](?=\s|$)", 'ing', re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', title))
    return re.sub(r'^(a|the)', '', norm(title))


# The same act under an old name, so its albums don't split in two (Lady A's Need You Now)
SAME_ACT = {'ladyantebellum': 'ladya'}
# Albums whose tracks are filed under two acts or two titles, keyed (act, album) -> (act, album).
# Gaslighter came out as the Dixie Chicks became The Chicks; the rest are reissues (Will, 2026-10-22)
SAME_ALBUM = {('dixiechicks', 'gaslighter'): ('thechicks', 'gaslighter'),
              ('carlypearce', 'hummingbirdnorainnoflowers'): ('carlypearce', 'hummingbird'),
              ('lukecombs', 'thisonesforyoutoo'): ('lukecombs', 'thisonesforyou')}


def act_key(artist):
    act = lead(artist)
    return SAME_ACT.get(act, act)


def album_key(t):
    """One album across its editions: "Red (Taylor's Version)", "Red (Deluxe Edition)" and "Red - EP" are Red."""
    name = re.sub(r'\s*[\(\[][^\)\]]*(deluxe|edition|version|expanded|bonus|collection|encore)[^\)\]]*[\)\]]', '',
                  t['Album'].strip(), flags=re.I).strip()
    key = act_key(t.get('Album Artist') or t.get('Artist')), norm(re.sub(r'\s+-\s+EP$', '', name, flags=re.I))
    return (*SAME_ALBUM.get(key, key), name)


TV = re.compile(r"taylor['’]s version", re.I)


def lead(artist):
    return norm(re.split(r',| & | and | ft\.? | feat\.? | featuring | x | with |;', artist or '', flags=re.I)[0])


def is_album(t):
    # iTunes' Compilation flag is set on plenty of ordinary albums, so only Various Artists counts as one
    return (t.get('Album') and not re.search(r'\s-\s*single$', t['Album'], re.I)
            and (t.get('Album Artist') or '').lower() != 'various artists')


def main():
    lib = plistlib.load(open(sys.argv[1], 'rb'))
    tracks, loose = defaultdict(list), defaultdict(list)  # title -> [(artist text, plays)]
    for t in lib['Tracks'].values():
        if t.get('Name'):
            v = (norm(f"{t.get('Artist', '')} {t.get('Album Artist', '')}"), t.get('Play Count', 0), t)
            tracks[norm(EXTRA.sub('', t['Name']))].append(v)
            loose[bare(t['Name'])].append(v)

    data = json.load(open('data.json', encoding='utf-8'))
    acts = {a['id']: a['name'] for a in data['artists']}
    rows, missing, raised = [], [], 0
    album_songs = defaultdict(list)  # album key -> songs from it that charted
    edition = {}  # vault songs: song id -> "Fearless (Taylor's Version)"
    for s in data['songs']:
        # Will's tell-apart suffix ("Heaven - Niall") names the artist, not the title
        m = re.fullmatch(r'(.+?) - (.+)', s['name'])
        title = m.group(1) if m and norm(m.group(2)) in norm(s['artistName']) else s['name']
        who = lead(s['artistName'])
        hits = [(p, t) for a, p, t in tracks.get(norm(EXTRA.sub('', title)), []) if who and who[:8] in a]
        if not hits:
            hits = [(p, t) for a, p, t in loose.get(bare(title), []) if who and who[:8] in a]
        on_album = [h for h in hits if is_album(h[1])]
        # A song re-recorded for a Taylor's Version belongs to the original release
        on_album = [h for h in on_album if not TV.search(h[1]['Album'])] or on_album
        if on_album:
            t = max(on_album, key=lambda h: h[0])[1]
            album_songs[album_key(t)[:2]].append(s)
            if TV.search(t['Album']):
                edition[s['id']] = re.sub(r'\s*\[[^\]]*\]', '', t['Album']).strip()
        if s['chart'] != 'willboard':
            continue
        if not hits:
            missing.append(f"{s['name']} - {s['artistName']}")
            continue
        plays = max(p for p, _ in hits)  # several copies (single + album): the one Will plays carries the count
        rows.append((s['name'], s['artistName'], plays))
        if plays > (s['itunesPlays'] or 0):
            s['itunesPlays'], raised = plays, raised + 1

    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['song', 'artist', 'plays'])
        w.writerows(sorted(rows))
    json.dump(data, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    albums = defaultdict(lambda: {'plays': 0, 'tracks': 0, 'names': [], 'years': [], 'cuts': defaultdict(lambda: [0, []])})
    for t in lib['Tracks'].values():
        if is_album(t) and album_key(t)[:2] in album_songs:
            a = albums[album_key(t)[:2]]
            a['plays'] += t.get('Play Count', 0)
            a['tracks'] += 1
            cut = a['cuts'][bare(t['Name'])]
            cut[0] += t.get('Play Count', 0)
            cut[1].append(re.sub(r'\s*[\(\[][^\)\]]*(version|vault|remaster)[^\)\]]*[\)\]]', '', EXTRA.sub('', t['Name']), flags=re.I).strip())
            if not TV.search(t['Album']):
                a['names'].append(album_key(t)[2])
                if t.get('Year'):
                    a['years'].append(t['Year'])
    out = []
    for k, a in albums.items():
        songs = sorted(album_songs[k], key=lambda s: s['debutDate'])
        # The album's own act, not a duet partner (Cole Swindell for Stereotype, The Chicks for Gaslighter)
        lead_id = next((s['artistId'] for s in songs if act_key(s['artistName']) == k[0]), songs[0]['artistId'])
        al = {'name': min(a['names'] or [k[1]], key=len), 'artist': acts[lead_id], 'artistId': lead_id,
              'plays': a['plays'], 'tracks': a['tracks'], 'songs': [s['id'] for s in songs]}
        if a['years']:
            al['year'] = min(a['years'])  # release year, for ordering an artist's albums
        charted = {bare(s['name']) for s in songs}
        cuts = sorted(((min(n, key=len), p) for b, (p, n) in a['cuts'].items() if b not in charted and p >= CUT_MIN), key=lambda c: -c[1])
        if cuts:
            al['cuts'] = [{'name': n, 'plays': p} for n, p in cuts]
        if any(s['id'] in edition for s in songs):
            al['editions'] = {s['id']: edition[s['id']] for s in songs if s['id'] in edition}
        out.append(al)
    out.sort(key=lambda a: -a['plays'])
    json.dump(out, open(ALBUMS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'{len(out)} albums with a charted song; top: ' + ', '.join(f"{a['name']} {a['plays']}" for a in out[:5]))
    print(f'{len(rows)} matched, {raised} raised, {len(missing)} not in the library')
    print('\n'.join(sorted(missing)))


if __name__ == '__main__':
    main()
