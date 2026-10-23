#!/usr/bin/env python3
"""Build year_plays.json: each song's plays in each year, for the Year-End drop-downs.

    python3 tools/build_year_plays.py <folder of YYYY.xlsx> [country_plays.csv pop_plays.csv]

Run from the repo folder. The folder holds Will's "Top Songs of YYYY" workbooks saved as
YYYY.xlsx (the same folder build_year_tops.py reads); 2019 has no Top Songs workbook, so
2019.xlsx there is his "Plays Page 2019". From 2020 the plays on Will's own year-end lists
(yearend.json) win and his workbooks fill in every other song that charted that year.
Before 2020 the workbooks win where the two differ (Will, 2026-10-23).
Years with no workbook (2023) come from the CS Era Points plays archive exports, worked
out the way Will's workbooks do it (checked against 2024): Hot 20, the song's highest
running total in the year minus its first; Pop 10, the sum of its weekly plays. These match
his workbooks for nearly every song in 2020-2025. Pop before 2017 was ranked on chart points
only, and Pop 2019 has neither, so those years have no plays.
"""
import difflib
import json
import re
import os
import sys
from collections import defaultdict

import openpyxl

import csv

from build_year_tops import is_num, keys
from build_data import WEEK_LABEL

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
    (2019, 'willboard'): ('Country Total', 0, 4),  # Plays Page 2019
    (2019, 'pop'): ('Pop Total', 0, 4),
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
# The country plays export has two columns per chart week (running total, position) and dates
# only from this week on; earlier weeks are counted back from it
COUNTRY_ANCHOR = ('2024-03-21', 443)


def country_running(path, weeks):
    """{song title: {chart week: running plays}} from the Hot 20 plays export."""
    rows = list(csv.reader(open(path, encoding='utf-8')))
    a = weeks.index(COUNTRY_ANCHOR[0])
    out = {}
    for r in rows[1:]:
        if not r[0].strip():
            continue
        got = {}
        for i, w in enumerate(weeks):
            c = COUNTRY_ANCHOR[1] + 2 * (i - a)
            if 4 < c < len(r) and r[c].strip().isdigit():
                got[w] = int(r[c])
        if got:
            out[r[0].strip()] = got
    return out


def pop_year_plays(path):
    """{song title: {year: plays}} from the Pop plays export (weekly plays, from 2020)."""
    rows = list(csv.reader(open(path, encoding='utf-8')))
    year, prev, years = 2020, None, {}
    for i, h in enumerate(rows[0][1:], 1):
        m = WEEK_LABEL.fullmatch(h.strip())
        if not m:
            continue
        mon = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split().index(m.group(2)) + 1
        if prev and mon < prev:
            year += 1
        prev, years[i] = mon, year
    out = defaultdict(lambda: defaultdict(int))
    for r in rows[1:]:
        for i, y in years.items():
            if i < len(r) and r[i].strip().isdigit():
                out[r[0].strip()][y] += int(r[i])
    return out


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
        # Years without a workbook: the plays archive
        have = {str(y) for (y, k) in SHEETS if k == key}
        if len(sys.argv) > 3:
            if key == 'willboard':
                per_year = defaultdict(dict)
                for title, got in country_running(sys.argv[2], weeks).items():
                    for y in {w[:4] for w in got}:
                        v = [got[w] for w in sorted(got) if w[:4] == y]
                        per_year[y][title] = max(v) - v[0]
            else:
                per_year = defaultdict(dict)
                for title, by in pop_year_plays(sys.argv[3]).items():
                    for y, n in by.items():
                        per_year[str(y)][title] = n
            for y, titles in per_year.items():
                if y in have or y not in yearend[key]:
                    continue
                by_key = {}
                for sid in sorted(charted[int(y)]):
                    for kk in keys(songs[sid]['name']):
                        by_key.setdefault(kk, sid)
                for title, n in titles.items():
                    sid = next((by_key[kk] for kk in keys(title) if kk in by_key), None)
                    if sid:
                        out[key][y].setdefault(sid, n)
        # Will's year-end lists give the rest, and win from 2020 on
        for y, v in yearend[key].items():
            for row in v['songs']:
                if row.get('songId') and row.get('plays') is not None:
                    if int(y) >= 2020 or row['songId'] not in out[key][y]:
                        out[key][y][row['songId']] = row['plays']
    json.dump(out, open('year_plays.json', 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
    for key in out:
        print(key, ', '.join(f'{y}: {len(v)}' for y, v in sorted(out[key].items())))
    if missed:
        print(f'\n{len(missed)} workbook rows not matched to a song that charted that year:')
        print('\n'.join(missed))


if __name__ == '__main__':
    main()
