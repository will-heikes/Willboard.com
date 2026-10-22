#!/usr/bin/env python3
"""Build decade.json: the 2010s Decade-End lists from Will's "CS Era points - 2010s Decade" workbook.

    python3 tools/build_decade.py "CS Era points - 2010s Decade.xlsx"

Run from the repo folder. Country songs, artists and albums keep the order of Will's
"Top Songs", "Top Artists" and "Top Albums" tabs. Pop songs follow Will's own Top 100 in
decade_lists.tsv; Pop artists (the tab isn't ranked) are ordered by decade chart points.
Points only set the order; they aren't written out, since the site never shows them.
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

import openpyxl

from add_week import norm
from build_yearend import match

DECADE, TOP_SONGS, TOP_OTHER = '2010s', 100, 25
LISTS = 'decade_lists.tsv'
RENAMED = {'Lady Antebellum': 'Lady A'}  # the name the rest of the site uses


def rows(wb, tab):
    it = wb[tab].iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else '' for h in next(it)]
    return [dict(zip(head, r)) for r in it]


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def main():
    wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
    data = json.load(open('data.json', encoding='utf-8'))
    runs = json.load(open('runs.json', encoding='utf-8'))
    albums = json.load(open('albums.json', encoding='utf-8'))
    artist_id = {norm(a['name']): a['id'] for a in data['artists']}
    out, unmatched = {}, []

    def song_rows(key, listed):
        songs = [s for s in data['songs'] if s['chart'] == key]
        by_name = defaultdict(list)
        for s in songs:
            by_name[norm(s['name'])].append(s)
        res = []
        for title, artist, year in listed:
            s = match(by_name, title, artist, year)
            run = [p for p in runs[key]['runs'].get(s['id'], [None])[1:] if p] if s else []
            if not s:
                unmatched.append(f'{key}: {title} - {artist}')
            res.append({'rank': len(res) + 1, 'songId': s['id'] if s else None,
                        'name': s['name'] if s else title, 'artistName': s['artistName'] if s else artist,
                        'peak': min(run) if run else None, 'wks1': run.count(1), 'wc': len(run)})
            if len(res) == TOP_SONGS:
                break
        return res

    def artist_rows(names):
        # The Pop tab lists some acts twice and has pairings ("Maroon 5; Wiz Khalifa") of its own
        names = list(dict.fromkeys(RENAMED.get(n, n) for n in names if ';' not in n))[:TOP_OTHER]
        return [{'rank': i + 1, 'name': n, 'artistId': artist_id.get(norm(n))} for i, n in enumerate(names)]

    # Country: Will's own order
    top = [r for r in rows(wb, 'Top Songs') if r.get('Song')]
    country = song_rows('willboard', [(clean(r['Song']), clean(r['Artist']), getattr(r['Debut Date'], 'year', 2015)) for r in top])
    # Albums: each album's songs' weighted decade totals ("Total" on Top Songs: points share + plays share)
    # added up. The Top Albums tab ranks by the album's own iTunes plays, which lifts albums with one
    # small hit (Shania Twain's Now), so Will's song totals decide the order instead.
    by_name = defaultdict(list)
    for s in data['songs']:
        if s['chart'] == 'willboard':
            by_name[norm(s['name'])].append(s)
    album_of = {sid: a for a in albums for sid in a['songs']}
    totals, counts, names = defaultdict(float), defaultdict(int), {}
    for r in top:
        if not isinstance(r.get('Total'), (int, float)):
            continue
        s = match(by_name, clean(r['Song']), clean(r['Artist']), getattr(r['Debut Date'], 'year', 2015))
        al = album_of.get(s['id']) if s else None
        if al:
            key, names[(al['name'], al['artist'])] = (al['name'], al['artist']), True
        elif clean(r.get('Album')) and not re.search(r'single', clean(r['Album']), re.I):
            key = (clean(r['Album']), RENAMED.get(clean(r['Artist']), clean(r['Artist'])))
        else:
            continue
        totals[key] += r['Total']
        counts[key] += 1
    al_rows = [{'rank': i + 1, 'name': k[0], 'artist': k[1], 'songs': counts[k]}
               for i, k in enumerate(sorted(totals, key=lambda k: -totals[k])[:TOP_OTHER])]
    out['willboard'] = {'songs': country,
                        'artists': artist_rows([clean(r['Artist']) for r in rows(wb, 'Top Artists') if r.get('Artist')]),
                        'albums': al_rows}

    # Pop: ordered by decade points, unless Will has ranked the songs himself
    it = wb['Pop'].iter_rows(values_only=True)
    next(it)
    head = [str(h).strip() if h is not None else '' for h in next(it)]
    pop = [dict(zip(head, r)) for r in it]
    pop = sorted((r for r in pop if r.get('Song') and isinstance(r.get('Total'), (int, float))), key=lambda r: -r['Total'])
    pop_songs = song_rows('pop', [(clean(r['Song']), clean(r['Artist']).replace(';', ','), getattr(r['Debut Date'], 'year', 2015)) for r in pop])
    # Will's own Pop Top 100 (decade_lists.tsv), when there is one, replaces the points order
    if os.path.exists(LISTS):
        mine = [r for r in csv.DictReader(open(LISTS, encoding='utf-8'), delimiter='\t') if r['decade'] == DECADE and r['chart'] == 'pop']
        if mine:
            pop_songs = song_rows('pop', [(r['song'], r['artist'], 2015) for r in sorted(mine, key=lambda r: int(r['rank']))])
    pop_artists = sorted((r for r in rows(wb, 'Pop Artist Records') if r.get('Artist') and isinstance(r.get('Points'), (int, float))),
                         key=lambda r: -r['Points'])
    out['pop'] = {'songs': pop_songs, 'artists': artist_rows([clean(r['Artist']) for r in pop_artists])}

    json.dump({DECADE: out}, open('decade.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    for k, v in out.items():
        print(k, {n: len(x) for n, x in v.items()}, 'top:', [s['name'] for s in v['songs'][:3]])
    print('Unmatched:', *unmatched, sep='\n  ')


if __name__ == '__main__':
    main()
