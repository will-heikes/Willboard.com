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

OUT, ALBUMS, LENGTHS = 'itunes_plays.tsv', 'albums.json', 'song_lengths.json'
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
              ('lukecombs', 'thisonesforyoutoo'): ('lukecombs', 'thisonesforyou'),
              ('coleswindell', 'stereotypebroken'): ('coleswindell', 'stereotype'),
              # Deluxe reissues with their own title, and EPs whose songs went onto the album that
              # followed (Will, 2026-10-23). These give the album's name and release year, so the
              # EP's name and earlier date don't take over.
              ('carlypearce', '29'): ('carlypearce', '29writteninstone', '29: Written In Stone', 2021),
              ('lukecombs', 'whatyouseeaintalwayswhatyouget'): ('lukecombs', 'whatyouseeiswhatyouget', 'What You See Is What You Get', 2019),
              ('ellalangley', 'stillhungover'): ('ellalangley', 'hungover', 'hungover', 2024),
              ('kelseaballerini', 'thefirsttime10yearanniversaryedition'): ('kelseaballerini', 'thefirsttime', 'The First Time', 2015),
              ('maddie', 'onehearttoanother'): ('maddie', 'thewayitfeels', 'The Way It Feels', 2020),
              ('maddie', 'whatawomancando'): ('maddie', 'lovelight', 'Love & Light', 2025),
              ('parkermccollum', 'hollywoodgold'): ('parkermccollum', 'goldchaincowboy', 'Gold Chain Cowboy', 2021),
              ('runawayjune', 'runawayjune'): ('runawayjune', 'blueroses', 'Blue Roses', 2019),
              ('randallking', 'leanna'): ('randallking', 'shotglass', 'Shot Glass', 2022),
              ('ashtonshepherd', 'lookitup'): ('ashtonshepherd', 'wherecountrygrows', 'Where Country Grows', 2011)}

# Albums whose tracks carry their singles' earlier year. Year-End lists an album only from the year
# it came out (Will), so this matters there as well as for ordering
RELEASED = {('maddie', 'thewayitfeels'): 2020, ('carlypearce', 'carlypearce'): 2020,
            ('mackenziecarpenter', 'heycountryqueen'): 2025, ('gabbybarrett', 'goldmine'): 2020,
            ('timmcgraw', 'setthiscircusdown'): 2001}

# EPs folded into the album that followed (the rest of the merges above are deluxe reissues)
FROM_EP = re.compile(r'\s-\s*EP$|\bEP$', re.I)
EP_KEYS = {('carlypearce', '29')}  # (act, album) for EPs whose tracks carry no "- EP" tag

# Tracks filed under the wrong album: Eric Church's Heart and Soul are two albums, not "Heart & Soul" (Will)
TRACK_ALBUM = {('ericchurch', 'hellofaview'): 'Heart', ('ericchurch', 'stickthatinyourcountrysong'): 'Soul',
               # Will only has it on Greatest Hits, Vol. 2; it came from this 2001 album
               ('timmcgraw', 'grownmendontcry'): 'Set This Circus Down'}


def act_key(artist):
    act = lead(artist)
    return SAME_ACT.get(act, act)


def album_key(t):
    """One album across its editions: "Red (Taylor's Version)", "Red (Deluxe Edition)" and "Red - EP" are Red."""
    name = re.sub(r'\s*[\(\[][^\)\]]*(deluxe|edition|version|expanded|bonus|collection|encore)[^\)\]]*[\)\]]', '',
                  t['Album'].strip(), flags=re.I).strip()
    act = act_key(t.get('Album Artist') or t.get('Artist'))
    name = TRACK_ALBUM.get((act, bare(t['Name'])), name)
    key = act, norm(re.sub(r'\s+-\s+EP$', '', name, flags=re.I))
    to = SAME_ALBUM.get(key, key)
    return to if len(to) == 4 else (*to, name, None)


TV = re.compile(r"taylor['’]s version", re.I)


def lead(artist):
    return norm(re.split(r',| & | and | ft\.? | feat\.? | featuring | x | with |;', artist or '', flags=re.I)[0])


# Hits collections (Will): a song is filed under one only when it's on no studio album, like Ain't
# Back Yet. Their pages list just those songs, and Year-End leaves them out
COMPILATION = re.compile(r"greatest hits|\bhits\b|singles collection|: the collection|number one hits|"
                         r"out of the box|the ones that got the plays", re.I)


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
    deluxe = {}  # songs Will has from a deluxe edition: song id -> that edition, for its cover
    lengths = {}  # song id -> seconds, for Ask's longest and shortest song
    for s in data['songs']:
        # Will's tell-apart suffix ("Heaven - Niall") names the artist, not the title
        m = re.fullmatch(r'(.+?) - (.+)', s['name'])
        title = m.group(1) if m and norm(m.group(2)) in norm(s['artistName']) else s['name']
        who = lead(s['artistName'])
        hits = [(p, t) for a, p, t in tracks.get(norm(EXTRA.sub('', title)), []) if who and who[:8] in a]
        if not hits:
            hits = [(p, t) for a, p, t in loose.get(bare(title), []) if who and who[:8] in a]
        on_album = [h for h in hits if is_album(h[1])]
        # A studio album beats a hits collection
        on_album = [h for h in on_album if not COMPILATION.search(h[1]['Album'])] or on_album
        # A song re-recorded for a Taylor's Version belongs to the original release
        on_album = [h for h in on_album if not TV.search(h[1]['Album'])] or on_album
        if on_album:
            t = max(on_album, key=lambda h: h[0])[1]
            album_songs[album_key(t)[:2]].append(s)
            if TV.search(t['Album']):
                edition[s['id']] = re.sub(r'\s*\[[^\]]*\]', '', t['Album']).strip()
            elif not (FROM_EP.search(t['Album'].strip()) or (act_key(t.get('Album Artist') or t.get('Artist')), norm(t['Album'])) in EP_KEYS
                      or (act_key(t.get('Album Artist') or t.get('Artist')), bare(t['Name'])) in TRACK_ALBUM):
                deluxe[s['id']] = t['Album'].strip()
        timed = [(p, t) for p, t in hits if t.get('Total Time')]
        if timed:
            lengths[s['id']] = round(max(timed, key=lambda h: h[0])[1]['Total Time'] / 1000)
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
    json.dump(dict(sorted(lengths.items())), open(LENGTHS, 'w', encoding='utf-8'), separators=(',', ':'))

    albums = defaultdict(lambda: {'plays': 0, 'tracks': 0, 'names': [], 'years': [], 'cuts': defaultdict(lambda: [0, []])})
    for t in lib['Tracks'].values():
        if is_album(t) and album_key(t)[:2] in album_songs:
            if COMPILATION.search(t['Album']) and album_key(t)[2] == t['Album'].strip() \
                    and bare(t['Name']) not in {bare(s['name']) for s in album_songs[album_key(t)[:2]]}:
                continue  # a hits collection's old hits aren't its own songs
            a = albums[album_key(t)[:2]]
            a['plays'] += t.get('Play Count', 0)
            a['tracks'] += 1
            cut = a['cuts'][bare(t['Name'])]
            cut[0] += t.get('Play Count', 0)
            cut[1].append(re.sub(r'\s*[\(\[][^\)\]]*(version|vault|remaster)[^\)\]]*[\)\]]', '', EXTRA.sub('', t['Name']), flags=re.I).strip())
            if not TV.search(t['Album']):
                k = album_key(t)
                a['names'].append(k[2])
                if k[3] or t.get('Year'):
                    a['years'].append(k[3] or t['Year'])
    out = []
    for k, a in albums.items():
        songs = sorted(album_songs[k], key=lambda s: s['debutDate'])
        # The album's own act, not a duet partner (Cole Swindell for Stereotype, The Chicks for Gaslighter)
        lead_id = next((s['artistId'] for s in songs if act_key(s['artistName']) == k[0]), songs[0]['artistId'])
        al = {'name': min(a['names'] or [k[1]], key=len), 'artist': acts[lead_id], 'artistId': lead_id,
              'plays': a['plays'], 'tracks': a['tracks'], 'songs': [s['id'] for s in songs]}
        if a['years']:
            al['year'] = min(a['years'])  # release year, for ordering an artist's albums
        al['year'] = RELEASED.get(k, al.get('year'))
        charted = {bare(s['name']) for s in songs}
        cuts = sorted(((min(n, key=len), p) for b, (p, n) in a['cuts'].items() if b not in charted and p >= CUT_MIN), key=lambda c: -c[1])
        if cuts:
            al['cuts'] = [{'name': n, 'plays': p} for n, p in cuts]
        # A song off a deluxe edition keeps that edition's cover (Will); one off an EP takes the album's
        dlx = {s['id']: deluxe[s['id']] for s in songs if s['id'] in deluxe and norm(deluxe[s['id']]) != norm(al['name'])}
        if dlx:
            al['deluxe'] = dlx
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
