#!/usr/bin/env python3
"""Apply chart_fixes.json to runs.json, data.json, archive.json, yearend.json and decade.json.

    python3 tools/apply_chart_fixes.py

Run from the repo folder. Will's CS Era Points sheet has a few weeks with two songs at one
position or a gap (see /mnt/project-files/willboard/chart-audit.md). chart_fixes.json holds the
corrections: whole charts copied from Will's iTunes chart playlists, and single-song moves taken
from his Plays Pages. The sheet itself stays as it is, so build_data.py calls this after every
rebuild. Applying the fixes twice changes nothing. Year-End and Decade-End rows are shifted by
what a fix changes, so after rebuilding those from the sheet, rebuild runs.json without the fixes
first (or patch them by hand).
"""
import difflib
import json
from datetime import date

from add_week import add_to_runs, points
from build_data import archive_facts
from build_year_tops import keys

HIST = {'willboard': 'wbHistory', 'pop': 'popHistory'}


def week_charts(runs, key):
    """{week: {songId: position}} for every week in runs.json."""
    r = runs[key]
    out = {w: {} for w in r['weeks']}
    for sid, run in r['runs'].items():
        for i, p in enumerate(run[1:]):
            if p:
                out[r['weeks'][run[0] + i]][sid] = p
    return out


def finder(songs, weeks, charts):
    """Match a title to the song of that name charting nearest the week."""
    def find(title, week):
        i = weeks.index(week)
        near = {sid for w in weeks[max(0, i - 12):i + 13] for sid in charts[w]}
        pool = [s for s in songs if s['id'] in near] + [s for s in songs if s['id'] not in near]
        for loose in (False, True):
            for k in keys(title):
                for s in pool:
                    names = keys(s['name'])
                    if k in names or (loose and difflib.get_close_matches(k, names, n=1, cutoff=0.85)):
                        return s['id']
        raise SystemExit(f'chart_fixes.json: no song matches {title!r} ({week})')
    return find


def apply():
    fixes = json.load(open('chart_fixes.json', encoding='utf-8'))
    runs = json.load(open('runs.json', encoding='utf-8'))
    data = json.load(open('data.json', encoding='utf-8'))
    archive = json.load(open('archive.json', encoding='utf-8'))
    changed = []
    for key, fx in fixes.items():
        if key.startswith('_'):
            continue
        songs = [s for s in data['songs'] if s['chart'] == key]
        by_id = {s['id']: s for s in songs}
        weeks = runs[key]['weeks']
        charts = week_charts(runs, key)
        before = {w: dict(c) for w, c in charts.items()}
        find = finder(songs, weeks, charts)
        for w, titles in fx.get('charts', {}).items():
            new = {find(t, w): i for i, t in enumerate(titles, 1)}
            if new != charts[w]:
                charts[w] = new
                changed.append(w)
        for w, moves in fx.get('moves', {}).items():
            for t, p in moves.items():
                sid = find(t, w)
                if charts[w].get(sid) != p:
                    charts[w][sid] = p
                    changed.append(w)
        if not changed:
            continue

        # Rebuild the runs and every song's chart stats from the corrected weeks
        fresh = {}
        for w in weeks:
            add_to_runs(fresh, key, w, [{'songId': sid, 'position': p} for sid, p in sorted(charts[w].items(), key=lambda x: x[1])])
        runs[key] = fresh[key]
        on = {}
        for w in weeks:
            for sid, p in charts[w].items():
                on.setdefault(sid, []).append((w, p))
        for sid, run in on.items():
            s = by_id[sid]
            s.update(debutDate=run[0][0], peakPosition=min(p for _, p in run), weeksOnChart=len(run),
                     totalPoints=sum(points(p) for _, p in run))

        # Weekly #1s and notable moves for each corrected week and the week after it
        touched = {w for c in changed for w in weeks[weeks.index(c):weeks.index(c) + 2]}
        hist, prev, count = {h['week']: h for h in data[HIST[key]]}, {}, {}
        for w in weeks:
            ents = sorted(charts[w].items(), key=lambda x: x[1])
            for sid, _ in ents:
                count[sid] = count.get(sid, 0) + 1
            h = hist.get(w)
            if h and ents and w in touched:
                top = by_id[ents[0][0]]
                h['no1'].update(songId=top['id'], songName=top['name'], artistName=top['artistName'])
                h.pop('notable', None)
                debuts = [(sid, p) for sid, p in ents if count[sid] == 1]
                climbs = [(prev[sid] - p, sid, p) for sid, p in ents if prev.get(sid, 0) > p]
                if debuts:
                    sid, p = debuts[0]
                    h['notable'] = {'type': 'hotshot', 'position': p}
                elif climbs:
                    gain, sid, p = max(climbs, key=lambda c: c[0])
                    h['notable'] = {'type': 'mover', 'gain': gain, 'position': p}
                if 'notable' in h:
                    s = by_id[sid]
                    h['notable'].update(songId=s['id'], songName=s['name'], artistName=s['artistName'])
            prev = dict(ents)
        for wk in data[key]:
            if wk['week'] in changed:
                plays = {e['songId']: e.get('plays') for e in wk['entries']}
                wk['entries'] = [{'songId': sid, 'position': p, 'plays': plays.get(sid), 'weeks': count_upto(on[sid], wk['week'])}
                                 for sid, p in sorted(charts[wk['week']].items(), key=lambda x: x[1])]

        # Archive stories are written from the charts. Rewrite them for each corrected week and the
        # year after it, where running counts (20th week on the chart, nth top five) can shift
        window = {w for c in changed for w in weeks[weeks.index(c):weeks.index(c) + 53]}
        dates = [date.fromisoformat(w) for w in weeks]
        weekly = [[{'songId': sid, 'position': p} for sid, p in charts[w].items()] for w in weeks]
        names = {a['id']: a['name'] for a in data['artists']}
        archive = [f for f in archive if f['chart'] != key or f['week'] not in window] + \
                  [f for f in archive_facts(key, dates, weekly, by_id, names) if f['week'] in window]
        archive.sort(key=lambda f: (f['week'], f['chart'], -f['score']))

        # Year-End and Decade-End rows keep Will's own lists' figures, so shift them by what the
        # fixes changed rather than recounting
        moved = {sid for w in set(changed) for sid in set(before[w]) | set(charts[w])}
        def period_stats(ch, sid, pre):
            ps = [c[sid] for w, c in ch.items() if w.startswith(pre) and sid in c]
            return min(ps) if ps else None, ps.count(1), len(ps)
        for path, periods in (('yearend.json', lambda d: d[key].items()),
                              ('decade.json', lambda d: [(dec[:3], v[key]) for dec, v in d.items()])):
            doc = json.load(open(path, encoding='utf-8'))
            for pre, block in periods(doc):
                for r in block.get('songs', []):
                    if r['songId'] not in moved:
                        continue
                    (p0, n0, c0), (p1, n1, c1) = period_stats(before, r['songId'], pre), period_stats(charts, r['songId'], pre)
                    r['wks1'] += n1 - n0
                    r['wc'] += c1 - c0
                    if p0 != p1 and r['peak'] == p0:
                        r['peak'] = p1
            json.dump(doc, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    if changed:
        json.dump(runs, open('runs.json', 'w', encoding='utf-8'), separators=(',', ':'))
        json.dump(data, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        json.dump(archive, open('archive.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'chart fixes: {len(set(changed))} weeks corrected')
    return sorted(set(changed))


def count_upto(run, week):
    return sum(1 for w, _ in run if w <= week)


if __name__ == '__main__':
    apply()
