#!/usr/bin/env python3
"""Build year_plays.json: each song's plays in each year, for the Year-End drop-downs.

    python3 tools/build_year_plays.py <folder of YYYY.xlsx>

Run from the repo folder. The folder holds Will's "Top Songs of YYYY" workbooks saved as
YYYY.xlsx (the same folder build_year_tops.py reads). Plays on Will's own year-end lists
(yearend.json) win; his workbooks fill in every other song that charted that year.
Pop before 2017 was ranked on chart points only, so those years have no plays.
"""
import difflib
import json
import re
import os
import sys
from collections import defaultdict

import openpyxl

from build_year_tops import is_num, keys

# (year, chart): (tab, song column, plays column). A plays column given as text is
# the header naming it ('Total' after the weekly plays columns).
SHEETS = {
    (2012, 'willboard'): ('Country Song', 63, 65),  # his Top 25 by plays
    (2013, 'willboard'): ('Country Songs', 63, 64),
    (2014, 'willboard'): ('Country Songs', 0, 58),
    (2015, 'willboard'): ('Country Songs Plays', 1, 'Total'),
    (2016, 'willboard'): ('Country Plays', 1, 'Total'),
    (2017, 'willboard'): ('Country Plays', 1, 'Total'),
    (2017, 'pop'): ('Pop Plays', 1, 'Total'),
    (2018, 'willboard'): ('Top Country Songs', 4, 5),
    (2018, 'pop'): ('Top Pop Songs', 4, 5),
    (2020, 'willboard'): ('Country Test', 1, 6),
    (2020, 'pop'): ('Pop Test', 1, 6),
    (2021, 'willboard'): ('Country Songs', 1, 64),
    (2021, 'pop'): ('Pop Songs', 1, 65),
    (2022, 'willboard'): ('Country Plays', 0, 3),
    (2022, 'pop'): ('Pop', 0, 1),
    (2024, 'willboard'): ('Country', 0, 2),
    (2024, 'pop'): ('Pop', 0, 1),
    (2025, 'willboard'): ('Country', 0, 2),
    (2025, 'pop'): ('Pop', 0, 2),
}


def main():
    folder = sys.argv[1]
    data = json.load(open('data.json', encoding='utf-8'))
    runs = json.load(open('runs.json', encoding='utf-8'))
    yearend = json.load(open('yearend.json', encoding='utf-8'))
    songs = {s['id']: s for s in data['songs']}
    out = {'willboard': defaultdict(dict), 'pop': defaultdict(dict)}
    missed = []
    for key in out:
        weeks, song_runs = runs[key]['weeks'], runs[key]['runs']
        charted = defaultdict(set)  # year: songs on the chart that year
        for sid, r in song_runs.items():
            for i, pos in enumerate(r[1:]):
                if pos:
                    charted[int(weeks[r[0] + i][:4])].add(sid)
        for (y, k), (tab, song_col, plays_col) in SHEETS.items():
            path = os.path.join(folder, f'{y}.xlsx')
            if k != key or not os.path.exists(path):
                continue
            rows = list(openpyxl.load_workbook(path, data_only=True)[tab].iter_rows(values_only=True))
            if isinstance(plays_col, str):
                plays_col = next(r.index(plays_col) for r in rows if plays_col in r)
            by_key = {}
            for sid in sorted(charted[y]):
                for kk in keys(songs[sid]['name']):
                    by_key.setdefault(kk, sid)
            for r in rows:
                if len(r) <= max(song_col, plays_col) or not isinstance(r[song_col], str) or not is_num(r[plays_col]):
                    continue
                sid = next((by_key[kk] for kk in keys(r[song_col]) if kk in by_key), None)
                if not sid:
                    # Typos and cut-off titles in the workbooks: "Quaterback", "We Are Never Ever Getting Back"
                    base = keys(re.sub(r'\s+', ' ', r[song_col]))[-1]
                    near = [kk for kk in by_key if len(base) > 8 and kk.startswith(base)] or \
                        difflib.get_close_matches(base, by_key, n=1, cutoff=0.85)
                    sid = by_key[near[0]] if near else None
                if sid:
                    out[key][str(y)].setdefault(sid, int(r[plays_col]))
                elif r[plays_col]:
                    missed.append(f'{key} {y} {r[song_col]}')
        # Will's year-end lists win where they give plays
        for y, v in yearend[key].items():
            for row in v['songs']:
                if row.get('songId') and row.get('plays') is not None:
                    out[key][y][row['songId']] = row['plays']
    json.dump(out, open('year_plays.json', 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
    for key in out:
        print(key, ', '.join(f'{y}: {len(v)}' for y, v in sorted(out[key].items())))
    if missed:
        print(f'\n{len(missed)} workbook rows not matched to a song that charted that year:')
        print('\n'.join(missed))


if __name__ == '__main__':
    main()
