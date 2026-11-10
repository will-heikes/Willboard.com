#!/usr/bin/env python3
"""Build swizzle.json: Will's Swizzle rankings of his favorite Taylor Swift songs, edition by edition.

Run from the Willboard.com repo folder:
    python3 tools/build_swizzle.py --itunes "iTunes Music Library.xml" \
        --sheet 10="Swizzle 10.csv" --sheet 12="Swizzle 12.csv" --sheet 13="Swizzle 13.csv" \
        [--spotify ../willboard-spotify]

Sources, in order of preference for each edition:
  * a Google Sheet export (CSV) when Will has one: "Copy of Taylor Swift Song Rankings (Shared)" (Aug 8,
    2020) is Swizzle 10, "Taylor Swift Song Rankings (July 14, 2023)" is Swizzle 12, "Swizzle 13" (Dec 2025)
    is Swizzle 13. The sheets rank every song; the iTunes playlists of those editions stop early.
  * otherwise the "Swizzle N" playlist in Will's iTunes library (the playlist order is the ranking).
    The iTunes playlist named "Swizzle 13" is really Swizzle 12 (its top 12 matches the July 2023 sheet), so
    it is never used. There is no Swizzle 1.
--spotify points at a checkout of will-heikes/willboard-spotify; it gives each song a Deezer track id for the
30-second preview and a cover for albums the repo has no image of.
"""
import argparse
import csv
import glob
import json
import os
import plistlib
import re
import unicodedata
from collections import Counter

# When each edition was made: (date, estimated?, note). 10, 12 and 13 carry their sheets' dates.
# The rest follow Will's rule (2026-11-10): Swizzle 2 in early 2018; the first Lover and evermore lists
# 3-4 months after the album came out; the others spread evenly between those.
EDITIONS = {
    2: ('2018-02-10', True, 'Shortly after reputation.'),
    3: ('2018-06-23', True, 'After reputation, before Lover.'),
    4: ('2018-11-03', True, 'After reputation, before Lover.'),
    5: ('2019-03-16', True, 'After reputation, before Lover.'),
    6: ('2019-07-27', True, "ME! is out, the rest of Lover isn't."),
    7: ('2019-12-08', True, 'The first list with all of Lover.'),
    8: ('2020-02-27', True, 'After Lover, before folklore.'),
    9: ('2020-05-18', True, 'After Lover, before folklore.'),
    10: ('2020-08-08', False, 'Two weeks after folklore.'),
    11: ('2021-03-21', True, 'The first list with evermore.'),
    12: ('2023-07-14', False, 'After Midnights (The Til Dawn Edition). All Too Well and its 10 minute version were combined into one entry on this list, which is why the original drops off.'),
    13: ('2025-12-21', False, 'After The Life of a Showgirl. All Too Well and its 10 minute version are split back into two entries.'),
}
ERA = ['Taylor Swift', 'Fearless', 'Speak Now', 'Red', '1989', 'Reputation', 'Lover', 'folklore', 'evermore',
       'Midnights', 'The Tortured Poets Department', 'The Life of a Showgirl']

# Vault songs name their Taylor's Version album (the site's rule for Taylor's Version releases)
VAULT = {
    "Fearless (Taylor's Version)": ['You All Over Me', 'Mr. Perfectly Fine', "That's When", 'We Were Happy',
                                    "Don't You", 'Bye Bye Baby'],
    "Speak Now (Taylor's Version)": ['When Emma Falls in Love', 'I Can See You', 'Castles Crumbling',
                                     'Foolish One', 'Timeless', 'Electric Touch'],
    "Red (Taylor's Version)": ['Better Man', 'Nothing New', 'Babe', 'Message in a Bottle', 'I Bet You Think About Me',
                               'Forever Winter', 'Run', 'The Very First Night', 'All Too Well (10 Minute Version)'],
    "1989 (Taylor's Version)": ['Slut!', "Say Don't Go", 'Now That We Don\'t Talk', 'Suburban Legends',
                                'Is It Over Now?'],
}
# Sheet album labels -> the names the site uses
ALBUM_NAME = {'debut': 'Taylor Swift', 'folklore': 'folklore', 'evermore': 'evermore', 'reputation': 'Reputation',
              'midnights': 'Midnights', 'thetorturedpoetsdepartment': 'The Tortured Poets Department',
              'thelifeofashowgirl': 'The Life of a Showgirl'}
# Non-album singles: songs released on their own, never counted with an album (even a Taylor's Version that later added them)
OTHER = {'safeandsound': 'The Hunger Games', 'eyesopen': 'The Hunger Games', 'crazier': 'Hannah Montana: The Movie',
         'sweeterthanfiction': 'Sweeter Than Fiction', 'beautifuleyes': 'Beautiful Eyes', 'iheart': 'Beautiful Eyes',
         'ronan': 'Ronan', 'todaywasafairytale': 'Today Was a Fairytale'}
# Spellings the sheets use that differ from the song's real title
ALIAS = {'lwymmd': 'lookwhatyoumademedo'}
TITLE = {'lookwhatyoumademedo': 'Look What You Made Me Do', 'saydontgo': "Say Don't Go", 'shakeitoff': 'Shake It Off',
         'thelifeofashowgirl': 'The Life of a Showgirl', 'karmaicespice': 'Karma (feat. Ice Spice)',
         'snowonthebeachmorelanadelrey': 'Snow on the Beach (feat. More Lana Del Rey)',
         'snowonthebeach': 'Snow on the Beach', 'alltoowell10minuteversion': 'All Too Well (10 Minute Version)',
         'foreverandalwayspianoversion': 'Forever & Always (Piano Version)', 'foreverandalways': 'Forever & Always',
         'safeandsound': 'Safe & Sound', 'iheart': 'I Heart?', 'tisthedamnseason': "'tis the damn season",
         'exile': 'exile', 'evermore': 'evermore', 'nobodynocrime': 'no body, no crime', 'coneyisland': 'coney island',
         'itstimetogo': "it's time to go", 'rightwhereyouleftme': 'right where you left me',
         'superstar': 'Superstar', 'isitovernow': 'Is It Over Now?', 'slut': 'Slut!', 'florida': 'Florida!!!',
         'thatswhen': "That's When", 'red2013cmaawardsperformance': 'Red (2013 CMA Awards Performance)'}


def squash(s):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', s or '').lower())


def clean_title(t):
    """The song's title without Taylor's Version / vault tags, features or bonus-track notes."""
    t = (t or '').replace('’', "'").strip()
    t = re.sub(r"\s*[\(\[](taylor's version|from the vault|bonus track)[\)\]]", '', t, flags=re.I)
    t = re.sub(r'\s*[\(\[]from [^\)\]]*[\)\]]', '', t, flags=re.I)
    return t.strip()


def key(t):
    t = clean_title(t)
    low = t.lower()
    if low.startswith('karma') and 'ice' in low:
        return 'karmaicespice'
    if low.startswith('snow on the beach'):
        return 'snowonthebeachmorelanadelrey' if 'more lana' in low else 'snowonthebeach'
    t = re.sub(r'\s*[\(\[]?\s*\b(feat\.?|ft\.?|featuring)\s[^\)\]]*[\)\]]?', '', t, flags=re.I)
    k = squash(t.replace('&', 'and'))
    return ALIAS.get(k, k)


def itunes_album(a, artist):
    a = (a or '').strip()
    if a.startswith('Sounds Of The Season'):
        return 'The Taylor Swift Holiday Collection'
    if a.startswith('Red (2013 CMA'):
        return 'Red'
    if 'Hunger Games' in a:
        return 'The Hunger Games'
    if a.startswith('Hannah Montana'):
        return 'Hannah Montana: The Movie'
    a = re.sub(r'\s*\((Deluxe|Platinum|3am|Til Dawn) Edition\)|\s*- Single$', '', a)
    a = re.sub(r'\s*\(From "[^"]*"\)', '', a)
    return {'reputation': 'Reputation'}.get(a.lower(), a)


def sheet_rows(path):
    """(rank, title, album label) from a sheet export. Rank and Song are the first two filled columns."""
    rows = []
    for r in csv.reader(open(path, encoding='utf-8-sig')):
        cells = r[1:] if r and not r[0] else r
        if len(cells) >= 3 and cells[0].strip().isdigit() and cells[1].strip():
            rows.append((int(cells[0]), cells[1].strip(), cells[2].strip()))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--itunes')
    ap.add_argument('--clips-only', action='store_true', help="only refresh clips from swizzle_previews.json")
    ap.add_argument('--sheet', action='append', default=[], help='N=path.csv')
    ap.add_argument('--spotify', help='willboard-spotify checkout, for previews and missing covers')
    args = ap.parse_args()
    if args.clips_only:
        out = json.load(open('swizzle.json', encoding='utf-8'))
        add_clips(out['songs'])
        with open('swizzle.json', 'w') as f:
            json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
        return

    lib = plistlib.load(open(args.itunes, 'rb'))
    tracks = lib['Tracks']
    folder = next(p['Playlist Persistent ID'] for p in lib['Playlists'] if p.get('Name') == 'Swizzle' and p.get('Folder'))
    lists = {}
    for p in lib['Playlists']:
        m = re.fullmatch(r'Swizzle (\d+)', p.get('Name', ''))
        if m and p.get('Parent Persistent ID') == folder and int(m.group(1)) != 13:
            items = [tracks[str(i['Track ID'])] for i in p.get('Playlist Items', [])]
            lists[int(m.group(1))] = [(i + 1, t.get('Name'), None, t) for i, t in enumerate(items)]
    for s in args.sheet:
        n, path = s.split('=', 1)
        lists[int(n)] = [(r, t, a, None) for r, t, a in sheet_rows(path)]

    songs, editions = {}, []
    for n in sorted(lists):
        seen, ranked = set(), []
        for rank, title, label, t in lists[n]:
            k = key(title)
            if k in seen:
                raise SystemExit(f'Swizzle {n}: {title!r} twice')
            seen.add(k)
            s = songs.setdefault(k, {'t': None, 'a': 'Taylor Swift', 'al': None})
            if t:  # iTunes: proper spelling and the real credit
                s['t'] = s['t'] or clean_title(t.get('Name'))
                artist = t.get('Artist') or ''
                if 'Taylor Swift' not in artist.split(' Feat')[0].split(' &')[0] or artist.startswith('Tim McGraw'):
                    s['a'] = artist
                s.setdefault('_it', itunes_album(t.get('Album'), artist))
            else:
                s.setdefault('_sheet', clean_title(title))
                if label and squash(label) not in ('na', 'other'):
                    s['_label'] = ALBUM_NAME.get(squash(label), label)  # the latest sheet wins
            ranked.append([rank, k])
        date, est, note = EDITIONS[n]
        editions.append({'n': n, 'date': date, 'est': est, 'note': note, 'songs': ranked})

    vault = {squash(clean_title(t)): al for al, ts in VAULT.items() for t in ts}
    for k, s in songs.items():
        s['t'] = TITLE.get(k) or s['t'] or s.pop('_sheet', None) or k
        s.pop('_sheet', None)
        # A song that came out on its own (a soundtrack or charity single) stays a non-album single even
        # where a sheet files it under the Taylor's Version album it was later added to (Will 2026-11-10:
        # Today Was a Fairytale is not a Fearless song)
        label = s.pop('_label', None)
        al = vault.get(k) or OTHER.get(k) or label or s.get('_it')
        s.pop('_label', None); s.pop('_it', None)
        s['al'] = al

    # Each edition's era: the newest studio album it ranks
    for e in editions:
        albums = {songs[k]['al'].replace(" (Taylor's Version)", '') for _, k in e['songs']}
        e['era'] = max((a for a in albums if a in ERA), key=ERA.index)

    # Songs that charted on the Hot 20 or Pop 10 link to their Willboard song page
    data = json.load(open('data.json'))
    for x in data['songs']:
        k = key(re.sub(r' - [^-]+$', '', x['name']))
        if k in songs and squash(x['artistName']).startswith(squash(songs[k]['a'])[:11]):
            songs[k].setdefault('wb', x['id'])

    if args.spotify:
        add_spotify(songs, args.spotify)
    add_clips(songs)

    out = {'editions': editions, 'songs': dict(sorted(songs.items()))}
    with open('swizzle.json', 'w') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'swizzle.json: {len(editions)} editions, {len(songs)} songs')
    for e in editions:
        print(f"  Swizzle {e['n']:>2}  {e['date']:<12} {len(e['songs']):>3} songs  #1 {songs[e['songs'][0][1]]['t']}  ({e['era']} era)")


def add_clips(songs):
    """The clip tools/fetch_swizzle_previews.py chose wins: the original recording unless Will ranked the
    Taylor's Version, never acoustic or live (Will 2026-11-10)."""
    if not os.path.exists('swizzle_previews.json'):
        return
    clips = json.load(open('swizzle_previews.json', encoding='utf-8'))
    for k, s in songs.items():
        if clips.get(k):
            s['dz'] = clips[k]


def add_spotify(songs, root):
    """Deezer ids (for previews) from Will's most-played Spotify version of each song, and Deezer covers for
    albums the repo has no image of (images/covers/taylor-swift--<album>.jpg)."""
    media = json.load(open(os.path.join(root, 'media', 'tracks.json')))
    plays, album_track = Counter(), {}
    for f in sorted(glob.glob(os.path.join(root, 'streams', '*.csv'))):
        for r in csv.DictReader(open(f, encoding='utf-8')):
            if not r.get('track_uri', '').startswith('spotify:track:'):
                continue
            tid = r['track_uri'].split(':')[-1]
            plays[(key(r['track']), squash(r['artist'].split(',')[0]), tid)] += 1
            if media.get(tid, {}).get('cover'):
                album_track.setdefault(squash(re.sub(r':.*', '', r['album'])), tid)
    best = {}
    for (k, art, tid), c in plays.most_common():
        if media.get(tid, {}).get('deezer'):
            best.setdefault((k, art), tid)
    previews = json.load(open('previews.json')) if os.path.exists('previews.json') else {}
    covers = set(os.listdir(os.path.join('images', 'covers')))
    slug = lambda s: re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', s.lower().replace("'", '').replace('’', '')))
    for k, s in songs.items():
        tid = best.get((k, squash(s['a'].split(' Feat')[0].split(',')[0].split(' &')[0]))) or best.get((k, 'taylorswift'))
        if tid:
            s['dz'] = media[tid]['deezer']
        elif s.get('wb') and previews.get(s['wb']):
            s['dz'] = previews[s['wb']]
        if s['al'] and f"taylor-swift--{slug(s['al'])}.jpg" not in covers:
            at = album_track.get(squash(s['al']))
            if at and media.get(at, {}).get('cover'):
                s['cv'] = media[at]['cover']
    missing = sorted({s['al'] for s in songs.values() if s['al'] and 'cv' not in s
                      and f"taylor-swift--{slug(s['al'])}.jpg" not in covers})
    print('previews:', sum('dz' in s for s in songs.values()), 'of', len(songs), '| albums with no cover:', missing)


if __name__ == '__main__':
    main()
