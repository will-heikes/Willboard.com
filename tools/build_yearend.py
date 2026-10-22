#!/usr/bin/env python3
"""Build yearend.json: the Year-End Hot 20 and Pop 10 lists for every finished year.

    python3 tools/build_yearend.py country.csv pop.csv [pop_plays.csv]

Run from the repo folder, after build_data.py. Inputs:
  - yearend_lists.tsv: Will's own published year-end lists (chart, year, rank, song,
    artist, peak, wks1, wc, plays, points). These are used as written.
  - country.csv / pop.csv: the CS Era Points archive exports build_data.py reads.
  - pop_plays.csv (optional): the Pop weekly plays tab, one column per week from 2020.

Years without one of Will's lists are ranked the way he ranks them: each song's
share of the year's top play count plus its share of the year's top chart points.
Plays in a year come from pop_plays.csv for Pop and from data.json's weekly running
totals for the Hot 20. For older Hot 20 years, where weekly plays weren't kept, a
song's plays are split across years in proportion to the points it earned in each.
"""
import csv
import difflib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

from add_week import norm, points
from build_data import WEEK_LABEL, first_year, week_dates

LISTS = 'yearend_lists.tsv'
SIZE = {'willboard': 20, 'pop': 10}
TOP = 40
# Will's own #1 where the formula would say otherwise. Pop 2011: the chart only ran from
# late October, so he weighs pre-chart factors and puts In The Dark on top.
FIRST = {('pop', 2011): 'In The Dark'}


def chart_runs(path, size):
    """{normalised title: [(week date, position), ...]} from an archive export."""
    rows_all = list(csv.reader(open(path, encoding='utf-8')))
    head, rows = rows_all[1], [r for r in rows_all[2:] if len(r) > 3 and r[1].strip()]
    cols = [i for i, h in enumerate(head) if WEEK_LABEL.fullmatch(h.strip())]
    dates = week_dates(head, cols, first_year(rows), False)
    runs = []
    for r in rows:
        run = [(dates[i], int(r[c])) for i, c in enumerate(cols)
               if re.fullmatch(r'\d+', r[c].strip()) and 1 <= int(r[c]) <= size]
        if run:
            runs.append((r[1].strip(), r[2].strip(), run))
    return runs


def pop_weekly_plays(path):
    """{normalised title: {year: plays}} from the Pop plays tab (weekly, not running)."""
    rows = list(csv.reader(open(path, encoding='utf-8')))
    head = rows[0]
    year, prev, years = 2020, None, {}
    for i, h in enumerate(head[1:], 1):
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
                out[norm(r[0])][y] += int(r[i])
    return out


def match(songs_by_name, title, artist, year):
    """The data.json song for a title on a year's list."""
    # Will tells same-named songs apart with a suffix in his sheet: "Heaven - Niall"
    cands = songs_by_name.get(norm(title), []) + [s for ss in songs_by_name.values() for s in ss
                                                 if re.fullmatch(re.escape(title.strip()) + r' - .+', s['name'], re.I)]
    if not cands:
        # Lists sometimes carry a credit or note in the title: "Post To Be (Feat. ..."
        base = norm(re.split(r'\s[\(\[]', title)[0])
        cands = [s for k, ss in songs_by_name.items() if k.startswith(base) and base for s in ss]
    if not cands:
        # Small spelling differences: "Dancing" / "Dancin'", "&" / "and"
        close = difflib.get_close_matches(norm(title.replace('&', 'and')), songs_by_name, n=1, cutoff=0.9)
        cands = list(songs_by_name[close[0]]) if close else []
    if len(cands) > 1:
        lead = norm(re.split(r',| & | ft\.? | feat\.? | x | with |;', artist, flags=re.I)[0])
        cands.sort(key=lambda s: (not norm(s['artistName']).startswith(lead[:6]),
                                  abs(int(s['debutDate'][:4]) - year)))
    return cands[0] if cands else None


def main():
    country_csv, pop_csv = sys.argv[1:3]
    pop_plays = pop_weekly_plays(sys.argv[3]) if len(sys.argv) > 3 else {}
    data = json.load(open('data.json', encoding='utf-8'))
    out, unmatched = {'willboard': {}, 'pop': {}}, []

    for key, path in (('willboard', country_csv), ('pop', pop_csv)):
        songs = [s for s in data['songs'] if s['chart'] == key]
        by_name = defaultdict(list)
        for s in songs:
            by_name[norm(s['name'])].append(s)
        by_id = {s['id']: s for s in songs}

        # Per song and year: points, peak, weeks at #1, weeks on chart
        stats = defaultdict(lambda: defaultdict(lambda: {'points': 0, 'peak': 99, 'wks1': 0, 'wc': 0}))
        last_week = None
        for title, artist, run in chart_runs(path, SIZE[key]):
            s = match(by_name, title, artist, run[0][0].year)
            if not s:
                continue
            for d, p in run:
                t = stats[s['id']][d.year]
                t['points'] += points(p)
                t['peak'] = min(t['peak'], p)
                t['wks1'] += p == 1
                t['wc'] += 1
                last_week = max(last_week or d, d)
        # A year is finished once its last December chart is in
        done = last_week.year if (last_week.month, last_week.day) >= (12, 25) else last_week.year - 1

        # Plays in each year
        running = defaultdict(dict)  # Hot 20: data.json's weekly running totals
        for w in data[key]:
            for e in w['entries']:
                if e.get('plays') is not None:
                    running[e['songId']][w['week']] = e['plays']
        # Will's lists show each song's whole run (peak, weeks at #1, weeks on chart), not just that year
        def career(sid):
            v = stats[sid].values()
            return {'peak': min((x['peak'] for x in v), default=None), 'wks1': sum(x['wks1'] for x in v),
                    'wc': sum(x['wc'] for x in v)}

        window_start = data[key][0]['week']

        def plays_in(sid, year):
            s = by_id[sid]
            if key == 'pop' and pop_plays:
                return pop_plays.get(norm(s['name']), {}).get(year)
            # Running totals cover the year only if the 52-week window reaches back far enough
            r = running.get(sid, {})
            inyear = [v for k, v in r.items() if k[:4] == str(year)]
            if inyear and (window_start <= f'{year}-01-07' or s['debutDate'] >= window_start):
                before = [v for k, v in r.items() if k[:4] < str(year)]
                return max(inyear) - (max(before) if before else 0)
            total, pts = s.get('itunesPlays'), stats[sid]
            if not total:
                return None
            return round(total * pts[year]['points'] / max(1, sum(v['points'] for v in pts.values())))

        # Will's own lists come first
        lists = defaultdict(list)
        if os.path.exists(LISTS):
            for r in csv.DictReader(open(LISTS, encoding='utf-8'), delimiter='\t'):
                if (r['chart'] == 'country') == (key == 'willboard'):
                    lists[int(r['year'])].append(r)
        years = sorted({y for v in stats.values() for y in v if y <= done} | set(lists))
        for y in years:
            rows, src = [], ''
            if lists.get(y):
                for r in sorted(lists[y], key=lambda r: int(r['rank'])):
                    s = match(by_name, r['song'], r['artist'], y)
                    st = career(s['id']) if s else {}
                    if not s:
                        unmatched.append(f'{key} {y} #{r["rank"]} {r["song"]} - {r["artist"]}')
                    num = lambda v: int(re.sub(r'\D', '', v)) if re.search(r'\d', v or '') else None
                    rows.append({'rank': int(r['rank']), 'songId': s['id'] if s else None,
                                 'name': s['name'] if s else r['song'].strip(),
                                 'artistName': s['artistName'] if s else r['artist'].strip(),
                                 'peak': num(r['peak']) or (st.get('peak') if st else None),
                                 'wks1': num(r['wks1']) or (st.get('wks1') if st else 0),
                                 'wc': num(r['wc']) or (st.get('wc') if st else None)})
                src = 'will'
            if len(rows) < 10:
                # No list, or only a short one (2010 has a top five): rank the rest by formula
                year_songs = [(sid, v[y]) for sid, v in stats.items() if y in v]
                pl = {sid: plays_in(sid, y) or 0 for sid, _ in year_songs}
                top_pl = max(pl.values()) or 1
                top_pt = max(t['points'] for _, t in year_songs)
                ranked = sorted(year_songs, key=lambda x: -(pl[x[0]] / top_pl + x[1]['points'] / top_pt))
                listed = {r['songId'] for r in rows}
                for sid, t in ranked:
                    if len(rows) >= (25 if rows else TOP):
                        break
                    if sid not in listed:
                        s, c = by_id[sid], career(sid)
                        rows.append({'rank': len(rows) + 1, 'songId': sid, 'name': s['name'],
                                     'artistName': s['artistName'], 'peak': c['peak'], 'wks1': c['wks1'], 'wc': c['wc']})
                src = 'will+formula' if src == 'will' else 'formula'
            if (key, y) in FIRST:
                # Will's call outranks the formula here
                rows.sort(key=lambda r: r['name'] != FIRST[key, y])
                for i, r in enumerate(rows):
                    r['rank'] = i + 1
            out[key][str(y)] = {'source': src, 'songs': rows}
        print(key, ', '.join(f"{y}{'' if v['source'] == 'will' else '*'}" for y, v in out[key].items()))

    json.dump(out, open('yearend.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('* = ranked by formula')
    if unmatched:
        print(f'\n{len(unmatched)} list entries not matched to a site song:')
        print('\n'.join(unmatched))


if __name__ == '__main__':
    main()
