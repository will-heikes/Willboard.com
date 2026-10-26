#!/usr/bin/env python3
"""Build week_plays.json: each charting song's plays in every chart week we have them for.

    python3 tools/build_week_plays.py <Plays Pages folder> <country_plays.csv> <pop_plays.csv>

Run from the repo folder. The Plays Pages folder holds Will's "Plays Page YYYY" workbooks
saved as YYYY.xlsx (2015-2019). Sources, per Will (2026-10-26):
  Hot 20  2015-2019  Plays Pages: a block per week of song, start, end, plays, position
          2020 on    CS Era Points plays archive: running total and position per week
  Pop 10  2018-2019  Plays Pages "Pop Plays" tab: plays per song per week (Last.fm)
          2020 on    CS Era Points pop plays archive: plays per song per week
Hot 20 weeks store [plays that week, running total]; the running total drives the
certification shown on old chart pages. Pop 10 weeks store plays that week only (Pop 10
certifications come from chart points). Plays Page blocks are matched to their chart week by
the songs and positions in them, since Will's chart numbers there don't line up with dates.
"""
import csv
import datetime
import difflib
import json
import os
import re
import sys
from collections import defaultdict

import openpyxl

from build_year_tops import is_num, keys
from build_data import WEEK_LABEL

MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def week_entries(runs, key):
    """{week: {position: songId}} from runs.json."""
    r = runs[key]
    out = defaultdict(dict)
    for sid, run in r['runs'].items():
        for i, p in enumerate(run[1:]):
            if p:
                out[r['weeks'][run[0] + i]][p] = sid
    return out


def matcher(songs):
    """Match a title to one of a week's songs by name, loosest form last."""
    def find(title, sids):
        title = re.sub(r'\*[^*]*\*', '', str(title)).strip()  # "*GREATEST GAINER*" notes on Plays Pages
        by = {}
        for sid in sids:
            for k in keys(songs[sid]['name']):
                by.setdefault(k, sid)
        for k in keys(title):
            if k in by:
                return by[k]
        for k in keys(title):
            hit = difflib.get_close_matches(k, list(by), n=1, cutoff=0.8)
            if hit:
                return by[hit[0]]
        return None
    return find


def plays_page_blocks(path, tab, year):
    """Every week block on a Hot 20 Plays Page: (dates the header could mean, [(song, start, end,
    plays, position)]). 2015-2018 headers carry a "Song M-D" label; 2019's carry only a number."""
    rows = list(openpyxl.load_workbook(path, data_only=True)[tab].iter_rows(values_only=True))
    blocks = defaultdict(list)  # (band start row, column) -> records
    band = 0
    for i, r in enumerate(rows):
        r = list(r)
        recs = [(c, (r[c], int(r[c + 1]), int(r[c + 2]), int(r[c + 3]), int(r[c + 4])))
                for c in range(len(r) - 4) if isinstance(r[c], str) and all(is_num(v) for v in r[c + 1:c + 5])]
        if not recs:
            band = i  # a header or blank row starts a new band of weeks
        for c, rec in recs:
            blocks[(band, c)].append(rec)
    out = []
    for (band, c), recs in blocks.items():
        if len(recs) < 10:
            continue
        dates = []
        for v in rows[band][c:c + 4]:
            m = re.search(r'(\d{1,2})-(\d{1,2})\s*$', v) if isinstance(v, str) else None
            for y in (year, year - 1) if m else ():
                try:
                    dates.append(datetime.date(y, int(m.group(1)), int(m.group(2))))
                except ValueError:
                    pass
        out.append((dates, recs))
    return out


def main():
    pp, country_csv, pop_csv = sys.argv[1:4]
    data = json.load(open('data.json', encoding='utf-8'))
    runs = json.load(open('runs.json', encoding='utf-8'))
    songs = {s['id']: s for s in data['songs']}
    find = matcher(songs)
    out = {'willboard': defaultdict(dict), 'pop': defaultdict(dict)}
    missed = defaultdict(int)

    # Hot 20, 2015-2019: a block goes to the chart week whose songs and positions it reproduces,
    # near the date in its header when it has one (2019's headers carry only a number)
    wb = week_entries(runs, 'willboard')
    def score(block, w):
        return sum(1 for song, *_, pos in block if wb[w].get(pos) and find(song, [wb[w][pos]]))
    blocks = []
    for y in range(2015, 2020):
        path = os.path.join(pp, f'{y}.xlsx')
        if os.path.exists(path):
            tab = next(t for t in openpyxl.load_workbook(path, read_only=True).sheetnames if t.startswith('Country') and 'Total' not in t and 'Points' not in t)
            blocks += [(y, dates, recs) for dates, recs in plays_page_blocks(path, tab, y)]
    # Header dates can be off by a week (two blocks labelled 10-18), so a dated block may go to any
    # week within ten days of its label; each block and week is used once, best match first
    def candidates(y, dates):
        if dates:
            return [w for w in wb if any(abs((datetime.date.fromisoformat(w) - d).days) <= 10 for d in dates)]
        return [w for w in wb if f'{y - 1}-12' <= w <= f'{y}-12-31']
    pairs = sorted(((score(recs, w), -min((abs((datetime.date.fromisoformat(w) - d).days) for d in dates), default=0), w, k)
                    for k, (y, dates, recs) in enumerate(blocks) for w in candidates(y, dates)), reverse=True)
    placed, used = {}, set()
    for sc, _, w, k in pairs:
        if sc >= 8 and w not in placed and k not in used:
            placed[w] = blocks[k][2]
            used.add(k)
    for k, (y, dates, recs) in enumerate(blocks):  # a week whose chart was since corrected
        exact = [d.isoformat() for d in dates if d.isoformat() in wb and d.isoformat() not in placed]
        if k not in used and exact:
            placed[exact[0]] = recs
            used.add(k)
    missed['hot20 blocks unplaced'] = len(blocks) - len(used)
    starts = defaultdict(dict)  # week -> {songId: running total going into that week}
    for w, recs in placed.items():
        for song, start, end, plays, pos in recs:
            sid = find(song, list(wb[w].values()))
            if sid:
                out['willboard'][w][sid] = [plays, end]
                starts[w][sid] = start
            else:
                missed['hot20 song'] += 1
    # A song's debut week isn't on the Plays Pages; its start the next week is its total going
    # out of the debut week, which also counts as that week's plays (everything up to its debut)
    weeks = sorted(wb)
    for i, w in enumerate(weeks[:-1]):
        if w in placed:
            for sid in wb[w].values():
                if sid not in out['willboard'][w] and sid in starts[weeks[i + 1]]:
                    total = starts[weeks[i + 1]][sid]
                    out['willboard'][w][sid] = [total, total]

    # Hot 20, 2020 on: the archive's running totals, a (total, position) column pair per week.
    # The pairs drift against the calendar (skipped and repeated weeks), so each position column
    # is matched to the chart week whose songs sit at those positions. Weeks from data.json's
    # first week on already carry their plays there.
    rows = list(csv.reader(open(country_csv, encoding='utf-8')))
    recent = data['willboard'][0]['week']
    span = [w for w in wb if '2019-12-26' <= w < recent and w not in out['willboard']]
    pairs = []
    for c in range(2, max(map(len, rows))):
        tally = defaultdict(int)
        for r in rows[1:]:
            if c < len(r) and r[c].strip().isdigit():
                pos = int(r[c])
                for w in span:
                    if wb[w].get(pos) and find(r[0], [wb[w][pos]]):
                        tally[w] += 1
        pairs += [(n, w, c) for w, n in tally.items() if n >= 8]
    best, taken = {}, set()  # week -> (score, position column), best match first
    for n, w, c in sorted(pairs, key=lambda x: (x[0], x[1], -x[2]), reverse=True):  # ties: earliest column
        if w not in best and c not in taken:
            best[w] = (n, c)
            taken.add(c)
    cols = sorted((c, w) for w, (_, c) in best.items())
    for k, (c, w) in enumerate(cols):
        before = cols[k - 1][0] - 1 if k and cols[k - 1][1] < w else None
        for r in rows[1:]:
            if c >= len(r) or not r[c].strip().isdigit() or not r[c - 1].strip().isdigit():
                continue
            pos, total = int(r[c]), int(r[c - 1])
            sid = wb[w].get(pos) if wb[w].get(pos) and find(r[0], [wb[w][pos]]) else find(r[0], list(wb[w].values()))
            if not sid:
                continue
            was = r[before].strip() if before is not None and before < len(r) else ''
            out['willboard'][w][sid] = [total - int(was) if was.isdigit() else None, total]
        # Debut weeks carry a running total but no position; the total is that week's plays
        for r in rows[1:]:
            if c < len(r) and not r[c].strip() and r[c - 1].strip().isdigit():
                left = [sid for sid in wb[w].values() if sid not in out['willboard'][w]]
                sid = find(r[0], left) if left else None
                if sid:
                    out['willboard'][w][sid] = [int(r[c - 1])] * 2
    # Around a few weeks the archive has running totals with no positions beside them. Those weeks
    # take the totals column between their neighbours' columns that holds the most of their songs
    # at or above the week before's totals
    W = sorted(wb)
    for w in sorted(set(span) - set(best)):
        cp = max((c for c, x in cols if x < w), default=1)
        cn = min((c for c, x in cols if x > w), default=max(map(len, rows)))
        prev = out['willboard'].get(W[W.index(w) - 1], {})
        def fit(t):
            got = {}
            for r in rows[1:]:
                v = r[t].strip() if t < len(r) else ''
                sid = find(r[0], list(wb[w].values())) if v.isdigit() else None
                if sid and int(v) >= prev.get(sid, [0, 0])[1]:
                    got[sid] = int(v)
            return got
        tries = [fit(t) for t in range(cp + 1, cn - 1)
                 if max((int(r[t]) for r in rows[1:] if t < len(r) and r[t].strip().isdigit()), default=0) > 20]
        got = max(tries, key=len, default={})
        # A column copied from the week before (Aug 1, 2024) isn't that week's plays
        if len(got) >= 12 and sum(v > prev.get(sid, [0, 0])[1] for sid, v in got.items()) >= 12:
            best[w] = None
            for sid, total in got.items():
                was = prev.get(sid, [None, None])[1]
                out['willboard'][w][sid] = [total - was if was is not None else total, total]
    missed['hot20 archive weeks unmatched'] = len(set(span) - set(best))
    # The archive only gives running totals, so a week's plays are its total less the song's last
    # known total; in a song's first chart week, everything up to then
    first, last = {}, {}
    for w in W:
        for sid in wb[w].values():
            first.setdefault(sid, w)
    for i, w in enumerate(W):
        gap = i and not out['willboard'].get(W[i - 1])  # after a week with no plays, two weeks' worth
        for sid, v in out['willboard'].get(w, {}).items():
            if w in best:
                v[0] = None if gap else v[1] - last[sid] if sid in last else v[1] if first[sid] == w else None
                if v[0] is not None and v[0] < 0:  # two songs of one name
                    v[0] = None
            last[sid] = v[1]

    # Pop 10, 2018-2019: Plays Pages "Pop Plays" tabs
    pop = week_entries(runs, 'pop')
    def add_pop(w, title, plays):
        if w not in pop or not plays:
            return
        sid = find(title, list(pop[w].values()))
        if sid:
            out['pop'][w][sid] = int(plays)
    for y in (2018, 2019):
        path = os.path.join(pp, f'{y}.xlsx')
        if not os.path.exists(path):
            continue
        rows = list(openpyxl.load_workbook(path, data_only=True)['Pop Plays'].iter_rows(values_only=True))
        cols = {j: v.date().isoformat() for j, v in enumerate(rows[0]) if isinstance(v, datetime.datetime)}
        for r in rows[1:]:
            if not r[0]:
                continue
            for j, w in cols.items():
                if j < len(r) and is_num(r[j]):
                    add_pop(w, r[0], r[j])

    # Pop 10, 2020 on: the archive's weekly plays (dates are "2-Jan" labels, year rolls over in order)
    rows = list(csv.reader(open(pop_csv, encoding='utf-8')))
    # 2025's columns reuse 2024's labels (29-Feb, no 22-Aug), so a year whose labels aren't
    # Thursdays is read in order against that year's chart weeks instead
    year, prev, by_year = 2020, 0, defaultdict(list)
    for j, h in enumerate(rows[0]):
        m = WEEK_LABEL.fullmatch(h.strip()) if j else None
        if not m:
            continue
        mon = MONTHS.index(m.group(2)) + 1
        if mon < prev:
            year += 1
        prev = mon
        by_year[year].append((j, mon, int(m.group(1))))
    cols = {}
    for year, labels in by_year.items():
        chart = [w for w in runs['pop']['weeks'] if w.startswith(str(year))]
        try:
            dates = [datetime.date(year, mon, day).isoformat() for _, mon, day in labels]
        except ValueError:
            dates = []
        if dates and all(datetime.date.fromisoformat(d).weekday() == 3 for d in dates):
            cols.update({j: d for (j, *_), d in zip(labels, dates) if d in chart})
        elif len(labels) == len(chart):
            cols.update({j: d for (j, *_), d in zip(labels, chart)})
        else:
            missed[f'pop {year} columns'] += 1
    for j, w in cols.items():
        for r in rows[1:]:
            if j < len(r) and r[j].strip().isdigit():
                add_pop(w, r[0], r[j])

    # A debut week's plays are everything up to the debut. That's one week's listening for most
    # songs, but an album cut that charted late (Genevieve, 295) brings months of it: leave those out
    hw = sorted(out['willboard'])
    for i, w in enumerate(hw[:-1]):
        for sid, v in out['willboard'][w].items():
            nxt = out['willboard'][hw[i + 1]].get(sid, [None])[0]
            if v[0] is not None and v[0] == v[1] and nxt is not None and v[0] > 2 * nxt + 10:
                v[0] = None
    res = {k: {w: v[w] for w in sorted(v)} for k, v in out.items()}
    json.dump(res, open('week_plays.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    for k, v in res.items():
        print(k, len(v), 'weeks', min(v), '..', max(v), sum(len(x) for x in v.values()), 'song-weeks')
    print('missed', dict(missed))


if __name__ == '__main__':
    main()
