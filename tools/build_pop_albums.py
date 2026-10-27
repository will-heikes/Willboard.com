#!/usr/bin/env python3
"""Turn pop_album_matches.json (tools/fetch_pop_albums.py) into pop_albums.json for the site.

    python3 tools/build_pop_albums.py

Songs only out as singles (or not found) get no album. Editions of one album ("(Deluxe)",
"(Expanded Edition)", " - EP") are merged, and the shortest name is kept. Album plays and
certifications come from Will's iTunes library, which doesn't cover pop, so pop albums carry
their charted songs and release year only. The site folds an album that's also in albums.json
into that entry.
"""
import json
import os
import re
import shutil
from collections import Counter, defaultdict

from fetch_artist_photos import norm
from fetch_covers import OUT as COVERS, clean, cover_name, same_artist

# Lookups that landed on the wrong release: "Artist|Title" (as in pop_album_matches.json) ->
# the album to use instead, or None for a song that was only a single
FIX = {
    'Alessia Cara|Best Days': 'Love & Hyperbole',
    'Alis|Nân': None,
    'Ariana Grande|The Boy is Mine': 'eternal sunshine',
    'Bebe Rexha|Meant to Be': 'Expectations',
    'DNCE|Cake By the Ocean': 'DNCE',
    'Hailee Steinfeld|Let Me Go': None,
    'Kelly Clarkson|It\'s Quiet Uptown': 'The Hamilton Mixtape',
    'Major Lazer|Cold Water': None,
    'Marshmello|Be Kind (Feat. Halsey)': None,
    'Neon Trees|Everybody Talks': 'Picture Show',
    'Nickelback|When We Stand Together': 'Here and Now',
    'Noah Cyrus|Team': None,
    'P!nk|Runaway': 'TRUSTFALL',
    'Post Malone|Better Now': 'beerbongs & bentleys',
    'Post Malone|White Iverson': 'Stoney',
    'Starley|Call On Me': None,
    'T-Pain|5 O\'Clock': 'Revolver',
    'Avril Lavigne|Bois Lie': 'Love Sux',
    'The Weeknd|Earned It': 'Beauty Behind the Madness',
    'The Weeknd|The Hills': 'Beauty Behind the Madness',
    'The Weeknd|I Feel It Coming': 'Starboy',
    'The Weeknd|Die For You': 'Starboy',
    'The Weeknd|Call Out My Name': 'My Dear Melancholy,',
    'The Weeknd|Pray For Me': None,
    'The Weeknd|One of the Girls': None,
    'Ed Sheeran|Afterglow': None,
    'Dua Lipa|Dance the Night': None,
    'Katy Perry|Never Really Over': 'Smile',
    'Katy Perry|Bandaids': None,
}
# "(Deluxe)", "(Wembley Edition)", "[Expanded Edition]", "Deluxe: LANA", ": The Encore" and the like
EDITION = re.compile(r'\s*([(\[][^)\]]*(deluxe|edition|version|expanded|remaster|anniversary)[^)\]]*[)\]]'
                     r'|:\s*the encore|\s+deluxe(:.*)?|:\s*[^:]*edition)\s*$', re.I)


# Reissues and EPs that count with an album (Will, 2026-10-23): "Artist|Album" as found -> that album.
# An EP goes into the album that followed it, since its songs were carried onto it.
SAME_ALBUM = {
    'Katy Perry|Teenage Dream: The Complete Confection': 'Teenage Dream',
    'Katy Perry|1432': '143',
    'Olivia Rodrigo|GUTS (spilled)': 'GUTS',
    'Pitbull|Global Warming: Meltdown': 'Global Warming',
    'Nick Jonas|Nick Jonas X2': 'Nick Jonas',
    "Demi Lovato|It's Not That Deep (Unless You Want It To Be)": 'It’s Not That Deep',
    'Tyla|TYLA +': 'TYLA',
    'Lorde|The Love Club EP': 'Pure Heroine',
    'Sabrina Carpenter|Espresso EP': "Short n' Sweet",
    'Kelsea Ballerini|Rolling Up the Welcome Mat (For Good)': 'Rolling Up the Welcome Mat',
}

# Preview picks that are no studio album: soundtracks, compilations, DJ mix episodes, double singles
PARENS = re.compile(r'\s*[(\[][^)\]]*[)\]]')
NOT_ALBUM = re.compile(r'soundtrack|motion picture|\bfrom\b|episode|collection|greatest|hits|/', re.I)

# Release years the track dates get wrong: a deluxe track dated later, or singles out long before the album
RELEASED = {
    'Dua Lipa|Future Nostalgia': 2020,
    'Sam Smith|Gloria': 2023,
    'Zara Larsson|So Good': 2017,
    'Katy Perry|The Ones That Got The Plays': 2019,
    'Camila Cabello|Camila': 2018,
    'Halsey|Manic': 2020,
    "Meghan Trainor|Takin' It Back": 2022,
    'T-Pain|Revolver': 2011,
    # Found through song previews, which carry no dates
    'Ke$ha|Warrior': 2012,
    'Ke$ha|Rainbow': 2017,
    'Fall Out Boy|Save Rock And Roll': 2013,
    'Machine Gun Kelly|bloom': 2017,
    'Machine Gun Kelly|Tickets To My Downfall': 2020,
    'BlackBear|digital druglord': 2017,
    '6ix9ine|DUMMY BOY (Revised)': 2018,
    'Rina Sawayama|SAWAYAMA': 2020,
    'Maneskin|Chosen': 2017,
}


def base_name(name):
    return EDITION.sub('', name).strip() or name.strip()


def group_key(name):
    # Ed Sheeran's +, x, ÷ and = have no letters for clean() to keep
    b = base_name(name)
    return clean(b) or b


def main():
    data = json.load(open('data.json', encoding='utf-8'))
    songs = {s['id']: s for s in data['songs']}
    ids = {a['name']: a['id'] for a in data['artists']}
    matches = json.load(open('pop_album_matches.json', encoding='utf-8'))
    by_norm = {norm(n): n for n in ids}

    def album_artist(m):
        # Will's spelling of the act; an album by someone else (a DJ's album with the singer
        # featured) goes under that act when Will's chart knows them
        a = m.get('albumArtist') or m['artist']
        return m['artist'] if same_artist(a, m['artist']) else by_norm.get(norm(a), a)

    # The song preview lookup (tools/fetch_previews.py) often found a song the album lookup missed
    # ("GTFO" on Caution, Will 2026-10-27): its album counts when it's one we already have for the
    # act, or, for a song the album lookup never found, when it isn't a single, a soundtrack or a mix
    picks = json.load(open('preview_picks.json', encoding='utf-8')) if os.path.exists('preview_picks.json') else {}
    known = set()
    for m in matches.values():
        if m.get('type') in ('album', 'ep') and f"{m['artist']}|{m['title']}" not in FIX:
            known.add((norm(m['artist']), group_key(m['album'])))

    def from_preview(sid, m):
        parts = [p.strip() for p in picks.get(sid, '').split(' | ')]
        if len(parts) < 3:
            return None
        album = re.sub(r'\s*\(Apple\)$', '', parts[2]).removesuffix(' - Single').removesuffix(' - EP').strip()
        if (norm(m['artist']), group_key(album)) in known:
            return album
        if 'album' in m or clean(PARENS.sub('', album)).startswith(clean(PARENS.sub('', m['title']))) or NOT_ALBUM.search(album):
            return None
        return album

    groups = defaultdict(list)
    for sid, m in matches.items():
        if sid not in songs:
            continue
        key = f"{m['artist']}|{m['title']}"
        if key in FIX:
            name = FIX[key]
            if name:  # the right album is by the song's own act
                m = {**m, 'album': None, 'albumArtist': m['artist'], 'released': None}
        else:
            name = m.get('album') if m.get('type') in ('album', 'ep') else None
        if not name and (alt := from_preview(sid, m)):
            name, m = alt, {**m, 'album': None, 'albumArtist': m['artist'], 'released': None}
        if not name:
            continue
        if f"{m['artist']}|{base_name(name)}" in SAME_ALBUM:
            # The reissue's date isn't the album's
            name, m = SAME_ALBUM[f"{m['artist']}|{base_name(name)}"], {**m, 'released': None, 'reissued': m.get('released')}
        groups[(norm(album_artist(m)), group_key(name))].append((sid, m, name))
    out = []
    for (_, _), rows in groups.items():
        rows.sort(key=lambda r: songs[r[0]]['debutDate'])
        artist = album_artist(rows[0][1])
        name = min((base_name(r[2]) for r in rows), key=len)
        # iTunes dates each track by its own release, so a lead single can predate its album;
        # take the year most of the charted songs share
        years = (Counter(int(r[1]['released'][:4]) for r in rows if r[1].get('released'))
                 or Counter(int(r[1]['reissued'][:4]) for r in rows if r[1].get('reissued')))
        # Albums found only through a song preview carry no dates: their charted songs' debuts stand in
        year = min(years, key=lambda y: (-years[y], y)) if years else int(songs[rows[0][0]]['debutDate'][:4])
        # The lookup saved the cover under the edition it found; the site looks for it under this name
        dest = os.path.join(COVERS, cover_name(artist, name))
        for r in rows:
            src = os.path.join(COVERS, cover_name(r[1]['artist'], r[1].get('album') or ''))
            if not os.path.exists(dest) and r[1].get('album') and os.path.exists(src):
                shutil.copyfile(src, dest)
        al = {'name': name, 'artist': artist, 'artistId': ids.get(artist), 'plays': None,
              'tracks': max((r[1].get('tracks') or 0) for r in rows) or None,
              'songs': [r[0] for r in rows], 'year': year, 'chart': 'pop'}
        # A song found on a deluxe edition keeps that edition's cover (Will); one off an EP takes the album's
        dlx = {r[0]: r[1]['album'] for r in rows if r[1].get('album') and clean(r[1]['album']) != clean(name)
               and not re.search(r'\bEP\b', r[1]['album']) and r[1].get('type') != 'ep'
               and os.path.exists(os.path.join(COVERS, cover_name(artist, r[1]['album'])))}
        if dlx:
            al['deluxe'] = dlx
        # The album's own release: its latest charted track, leaving out deluxe additions, since its
        # singles come out first. Year-End only lists an album from this year on (Will)
        out_years = [int(r[1]['released'][:4]) for r in rows if r[1].get('released') and r[0] not in dlx]
        if out_years:
            al['released'] = max(out_years)
        elif not years:
            al['released'] = max(int(songs[r[0]]['debutDate'][:4]) for r in rows)
        al['released'] = RELEASED.get(f'{artist}|{name}', al.get('released'))
        if not years:
            al['year'] = al['released']
        al['year'] = al['year'] or al['released']
        out.append(al)
    out.sort(key=lambda a: (-len(a['songs']), a['artist'].lower(), a['name'].lower()))
    json.dump(out, open('pop_albums.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    kinds = defaultdict(int)
    for m in matches.values():
        kinds[m.get('type', 'not found')] += 1
    print(f'{len(out)} pop albums from {sum(len(a["songs"]) for a in out)} songs; lookups: {dict(kinds)}')


if __name__ == '__main__':
    main()
