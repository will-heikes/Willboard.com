#!/usr/bin/env python3
"""Build year_tops.json: each year's top artists and albums, Country and Pop.

    python3 tools/build_year_tops.py <folder of Will's "Top Songs of YYYY" workbooks>

Run from the repo folder. The folder holds Will's workbooks saved as 2014.xlsx, 2015.xlsx, ...
Will's method: every song charted that year gets a weight, and an act's or album's total is the
sum of its songs' weights.
  - Song weight = its share of the year's top chart points + its share of the year's top plays.
    Where Will's workbook for the year has the song's total, his number is used as written.
  - Pop before 2017 counted chart points only.
  - Before 2015 a featured act got half of a song's points share (plays share in full);
    from 2015 every credited act gets the whole weight.
  - Years without a workbook use the chart points and, for plays, Will's year-end list
    (yearend_lists.tsv) or else the song's all-time plays split across years by its points.
Where a workbook ranks the artists (or albums) itself, Will's order is used as written, as with his
song lists; the weights then only fill in the counts and any places his list leaves open.
Weights only order the lists; they aren't written out, since the site never shows them.
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

import openpyxl

from add_week import norm, points

TOP = 10
# (year, chart): (tab, song column, total column) or, for 2014 Country, (tab, song, points share, plays share)
SHEETS = {
    (2014, 'willboard'): ('Country Songs', 0, 57, 59),
    (2015, 'willboard'): ('Country Songs Combined', 7, 11),
    (2016, 'willboard'): ('Country Song Agg', 1, 8),
    (2017, 'willboard'): ('Country Combinded', 1, 7),
    (2017, 'pop'): ('Pop Combined', 1, 7),
    (2018, 'willboard'): ('Top Country Songs', 1, 8),
    (2018, 'pop'): ('Top Pop Songs', 1, 8),
    (2020, 'willboard'): ('Country Test', 1, 8),
    (2020, 'pop'): ('Pop Test', 1, 8),
    (2021, 'willboard'): ('Country Songs', 56, 66),
    (2021, 'pop'): ('Pop Songs', 57, 67),
    (2022, 'willboard'): ('Country', 1, 6),
    (2022, 'pop'): ('Pop', 0, 5),
    (2024, 'willboard'): ('Country', 0, 6),
    (2024, 'pop'): ('Pop', 0, 5),
    (2025, 'willboard'): ('Country', 0, 6),
    (2025, 'pop'): ('Pop', 0, 6),
}
# Will's own artist totals: (year, chart): (tab, artist column, total column, first data row)
ARTIST_SHEETS = {
    (2014, 'willboard'): ('Country Artists', 1, 59, 2),
    (2016, 'willboard'): ('Country Song Agg', 2, 9, 1),
    (2017, 'willboard'): ('Country Combinded', 2, 8, 1),
    (2017, 'pop'): ('Pop Combined', 2, 8, 1),
}
# Will's own album totals (pivot tables of album name and total)
ALBUM_SHEETS = {
    (2020, 'willboard'): ('Sheet10', 0, 1, 3),
}


def ranked(path, spec):
    """Names from one of Will's totals tabs, biggest total first."""
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[spec[0]]
    rows = list(ws.iter_rows(values_only=True))[spec[3]:]
    got = [(r[spec[2]], str(r[spec[1]]).strip()) for r in rows
           if len(r) > spec[2] and is_num(r[spec[2]]) and r[spec[1]] and str(r[spec[1]]).strip() not in ('(blank)', 'Grand Total')]
    return [n for _, n in sorted(got, key=lambda x: -x[0])]


def keys(title):
    """Looser and looser forms of a title: as is, without brackets, without a "- Artist" tag."""
    t = str(title or '').strip()
    out = [norm(t), norm(re.sub(r'\s*[\(\[].*?[\)\]]', '', t)), norm(re.sub(r'\s+-\s+.*$', '', t))]
    return [k for k in dict.fromkeys(out) if k]


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def main():
    folder = sys.argv[1]
    data = json.load(open('data.json', encoding='utf-8'))
    runs = json.load(open('runs.json', encoding='utf-8'))
    albums = json.load(open('albums.json', encoding='utf-8'))
    songs = {s['id']: s for s in data['songs']}
    acts = {a['name'] for a in data['artists']}
    act_id = {a['name']: a['id'] for a in data['artists']}
    # Pop albums (tools/build_pop_albums.py) rank the Pop 10's songs; one that's also a library album
    # (a song that charted on both) counts with that album, as on the site
    pop_albums = json.load(open('pop_albums.json', encoding='utf-8')) if os.path.exists('pop_albums.json') else []
    album_of = {sid: a for a in pop_albums for sid in a['songs']}
    album_of.update({sid: a for a in albums for sid in a['songs']})

    def credits(name):
        """The acts on a credit, lead first. "&" and " x " split only when every part is a known act."""
        parts = [p.strip() for p in re.split(r',\s*|\s+(?:feat\.?|ft\.?|featuring|with)\s+', name, flags=re.I) if p.strip()]
        out = []
        for p in parts:
            sub = [x.strip() for x in re.split(r'\s+&\s+|\s+x\s+', p) if x.strip()]
            out += sub if len(sub) > 1 and all(x in acts for x in sub) else [p]
        return list(dict.fromkeys(out))

    # Will's year-end list plays, for years without a workbook
    list_plays = {}
    for r in csv.DictReader(open('yearend_lists.tsv', encoding='utf-8'), delimiter='\t'):
        if re.fullmatch(r'\d+', (r['plays'] or '').strip()):
            list_plays[('willboard' if r['chart'] == 'country' else 'pop', int(r['year']), norm(r['song']))] = int(r['plays'])

    out, report = {}, []
    for key in ('willboard', 'pop'):
        weeks, song_runs = runs[key]['weeks'], runs[key]['runs']
        # Per song: points, weeks at #1 in each year, and points in all
        per = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        total_pts = defaultdict(int)
        for sid, r in song_runs.items():
            for i, pos in enumerate(r[1:]):
                if pos:
                    y = int(weeks[r[0] + i][:4])
                    per[y][sid][0] += points(pos)
                    per[y][sid][1] += pos == 1
                    total_pts[sid] += points(pos)
        for y in sorted(per):
            year = per[y]
            top_pts = max(p for p, _ in year.values()) or 1
            pts_share = {sid: p / top_pts for sid, (p, _) in year.items()}

            # Plays share: from Will's workbook total, else his list's plays, else an estimate
            given, comps = {}, {}
            spec = SHEETS.get((y, key))
            path = os.path.join(folder, f'{y}.xlsx')
            if spec and os.path.exists(path):
                ws = openpyxl.load_workbook(path, data_only=True)[spec[0]]
                by_key = {}
                for sid in year:
                    for k in keys(songs[sid]['name']):
                        by_key.setdefault(k, sid)
                for row in ws.iter_rows(values_only=True):
                    if len(row) <= max(spec[1:]) or not row[spec[1]]:
                        continue
                    sid = next((by_key[k] for k in keys(row[spec[1]]) if k in by_key), None)
                    if not sid:
                        continue
                    if len(spec) == 4 and is_num(row[spec[2]]) and is_num(row[spec[3]]):
                        comps[sid] = (row[spec[2]], row[spec[3]])
                    elif len(spec) == 3 and is_num(row[spec[2]]):
                        given[sid] = row[spec[2]]
            est = {}
            for sid in year:
                lp = list_plays.get((key, y, norm(songs[sid]['name'])))
                est[sid] = lp if lp is not None else (songs[sid].get('itunesPlays') or 0) * year[sid][0] / (total_pts[sid] or 1)
            top_pl = max(est.values()) or 1

            def parts(sid):
                """(points share, plays share) of a song's weight."""
                if key == 'pop' and y < 2017:
                    return pts_share[sid], 0
                if sid in comps:
                    return comps[sid]
                if sid in given:
                    # Will's total as written; split by the same ratio as the points share for the
                    # half-points rule (only reached from 2015, where it isn't needed)
                    return given[sid], 0
                if spec and (given or comps):
                    # In a workbook year, a song his sheet doesn't list: points share, plays assumed alike
                    return pts_share[sid], pts_share[sid]
                return pts_share[sid], est[sid] / top_pl

            tally, al_tally = defaultdict(lambda: [0.0, set(), 0]), defaultdict(lambda: [0.0, set()])
            for sid in year:
                pp, pl = parts(sid)
                for i, act in enumerate(credits(songs[sid]['artistName'])):
                    t = tally[act]
                    t[0] += (pp if i == 0 or y >= 2015 else pp / 2) + pl
                    t[1].add(sid)
                    t[2] += year[sid][1]
                al = album_of.get(sid)
                if al:
                    a = al_tally[(al['name'], al['artist'])]
                    a[0] += pp + pl
                    a[1].add(sid)
            act_order = [n for n, _ in sorted(tally.items(), key=lambda x: -x[1][0])]
            al_order = [k for k, _ in sorted(al_tally.items(), key=lambda x: -x[1][0])]
            mine = []
            if (y, key) in ARTIST_SHEETS and os.path.exists(path):
                # His credits can be a whole line ("Jonas Blue, JP Cooper"); that counts for the lead act
                mine = [n if n in tally else credits(n.replace(';', ','))[0] for n in ranked(path, ARTIST_SHEETS[(y, key)])]
                act_order = list(dict.fromkeys([n for n in mine if n in tally] + act_order))
            if (y, key) in ALBUM_SHEETS and os.path.exists(path):
                by_name = {norm(k[0]): k for k in al_tally}
                mine_al = [by_name[norm(n)] for n in ranked(path, ALBUM_SHEETS[(y, key)]) if norm(n) in by_name]
                al_order = list(dict.fromkeys(mine_al + al_order))
            out.setdefault(str(y), {})[key] = {
                'artists': [{'name': n, 'artistId': act_id.get(n), 'songs': len(tally[n][1]), 'no1': tally[n][2]}
                            for n in act_order[:TOP]],
                'albums': [{'name': k[0], 'artist': k[1], 'songs': len(al_tally[k][1])} for k in al_order[:TOP]],
            }
            report.append(f"{y} {key}: {'workbook ' + str(len(given) + len(comps)) + '/' + str(len(year)) if given or comps else 'estimated'}"
                          f" · #1 artist {out[str(y)][key]['artists'][0]['name']}")

    json.dump(out, open('year_tops.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('\n'.join(report))


if __name__ == '__main__':
    main()
