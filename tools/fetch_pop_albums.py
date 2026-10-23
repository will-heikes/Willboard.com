#!/usr/bin/env python3
"""Find the album each Pop 10 song comes from (Will's iTunes library only covers country).

Run from the Willboard.com repo folder (the "Fetch artist photos" Action runs it with "pop_albums" ticked):
    python3 tools/fetch_pop_albums.py [--redo "Song title,Other song"] [--minutes 100]

Each song is looked up on Deezer, then the iTunes store. Of the releases that carry the song,
a studio album beats an EP, and either beats a single or a compilation. A song only out as a
single gets album null. Results go to pop_album_matches.json ({songId: {...}}), and songs already
in it are skipped, so a run that stops early carries on where it left off. Album covers are
saved to images/covers/ like the other covers. tools/build_pop_albums.py turns the matches
into pop_albums.json for the site.
"""
import argparse
import json
import os
import time
import urllib.parse

from fetch_artist_photos import get, primary_artist
from fetch_covers import OUT as COVERS, clean, cover_name, display_title, same_artist

OUT = 'pop_album_matches.json'
DEEZER_TRACK = 'https://api.deezer.com/search/track?limit=25&q={q}'
DEEZER_ALBUM = 'https://api.deezer.com/album/{id}'
ITUNES = 'https://itunes.apple.com/search?country=US&limit=25&entity=song&term={q}'
RANK = {'album': 0, 'ep': 1, 'single': 2, 'compile': 3}
_albums = {}


def deezer_album(aid):
    if aid not in _albums:
        _albums[aid] = json.loads(get(DEEZER_ALBUM.format(id=aid)))
        time.sleep(0.12)
    return _albums[aid]


def from_deezer(artist, title):
    q = urllib.parse.quote(f'artist:"{artist}" track:"{title}"')
    hits = json.loads(get(DEEZER_TRACK.format(q=q))).get('data', [])
    best = None
    for h in hits:
        if clean(h.get('title', '')) != clean(title) or not same_artist(h.get('artist', {}).get('name', ''), artist):
            continue
        al = deezer_album(h['album']['id'])
        if al.get('error'):
            continue
        kind = al.get('record_type', 'album')
        if (al.get('artist') or {}).get('name', '').lower() == 'various artists':
            kind = 'compile'
        key = (RANK.get(kind, 3), al.get('release_date') or '9999')
        if not best or key < best[0]:
            best = (key, {'album': al.get('title'), 'albumArtist': (al.get('artist') or {}).get('name') or artist,
                          'type': kind, 'released': al.get('release_date'), 'cover': al.get('cover_xl'),
                          'tracks': al.get('nb_tracks'), 'source': 'Deezer'})
    return best[1] if best else None


def from_itunes(artist, title):
    hits = json.loads(get(ITUNES.format(q=urllib.parse.quote(f'{artist} {title}')))).get('results', [])
    best = None
    for h in hits:
        if clean(h.get('trackName', '')) != clean(title) or not same_artist(h.get('artistName', ''), artist):
            continue
        name = h.get('collectionName', '')
        kind = 'single' if name.endswith(' - Single') else 'ep' if name.endswith(' - EP') else 'album'
        if (h.get('collectionArtistName') or '').lower() == 'various artists':
            kind = 'compile'
        key = (RANK[kind], h.get('releaseDate') or '9999')
        if not best or key < best[0]:
            best = (key, {'album': name.removesuffix(' - EP'), 'albumArtist': h.get('collectionArtistName') or h.get('artistName'),
                          'type': kind, 'released': (h.get('releaseDate') or '')[:10],
                          'cover': (h.get('artworkUrl100') or '').replace('100x100bb', '600x600bb'),
                          'tracks': h.get('trackCount'), 'source': 'iTunes'})
    return best[1] if best else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redo', default='')
    ap.add_argument('--minutes', type=float, default=0)
    args = ap.parse_args()
    redo = {t.strip().lower() for t in args.redo.split(',') if t.strip()}
    data = json.load(open('data.json', encoding='utf-8'))
    acts = frozenset(a['name'] for a in data['artists'])
    found = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    songs = [s for s in data['songs'] if s['chart'] == 'pop']
    start, done = time.time(), 0
    for i, s in enumerate(songs, 1):
        artist, title = primary_artist(s['artistName'], acts), display_title(s['name'], s['artistName'])
        if s['id'] in found and title.lower() not in redo:
            continue
        if args.minutes and time.time() - start > args.minutes * 60:
            print(f'Out of time at {i}/{len(songs)}; run again for the rest')
            break
        hit, note = None, 'not found'
        for source in (from_deezer, from_itunes):
            try:
                got = source(artist, title)
            except Exception as e:
                got, note = None, f'lookup failed: {e}'
            if source is from_itunes:
                time.sleep(3)  # iTunes allows about 20 lookups a minute
            if got and (not hit or RANK[got['type']] < RANK[hit['type']]):
                hit = got
            # A single on Deezer may still be on an album iTunes knows about
            if hit and hit['type'] in ('album', 'ep'):
                break
        rec = {'artist': artist, 'title': title, **(hit or {'note': note})}
        if hit and hit['type'] in ('album', 'ep') and hit.get('cover'):
            path = os.path.join(COVERS, cover_name(artist, hit['album']))
            if not os.path.exists(path):
                try:
                    open(path, 'wb').write(get(hit['cover']))
                except Exception:
                    pass
        found[s['id']] = rec
        done += 1
        print(f'[{i}/{len(songs)}] {artist} - {title}: {hit["album"] + " (" + hit["type"] + ")" if hit else note}')
        if done % 25 == 0:
            json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        time.sleep(0.15)
    json.dump(found, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    kinds = {}
    for r in found.values():
        kinds[r.get('type', 'not found')] = kinds.get(r.get('type', 'not found'), 0) + 1
    print('\nDone.', kinds)


if __name__ == '__main__':
    main()
