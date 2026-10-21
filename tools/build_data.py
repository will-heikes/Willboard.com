#!/usr/bin/env python3
"""Rebuild data.json from Will's full-history CSV exports of CS Era Points.

    python3 tools/build_data.py country.csv pop.csv [country_plays.csv] [--consecutive]

Each CSV is the Country or Pop tab as downloaded: headers in row 2, song and
artist in columns B and C, then one column per chart week labelled like
"15-Oct". Labels carry no year, so years are counted forward from the first
week. With --consecutive every column is one week after the last, ignoring
jumps in the labels.

Existing song and artist ids are kept where the song still matches, so links
to artist pages keep working.
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta

from add_week import norm, points

KEEP_WEEKS = 52
CHARTS = (  # key, file arg index, history key, id prefix, plays column header, chart size
    ('willboard', 0, 'wbHistory', 'song_', 'Plays', 20),
    ('pop', 1, 'popHistory', 'pop_song_', None, 10),
)
MONTHS = {m: i for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), 1)}
WEEK_LABEL = re.compile(r'(\d{1,2})-([A-Z][a-z]{2})')


def week_dates(head, cols, first_year, consecutive):
    out, year, prev = [], first_year, None
    for c in cols:
        day, mon = WEEK_LABEL.fullmatch(head[c].strip()).groups()
        d = date(year, MONTHS[mon], int(day))
        if prev and d <= prev:
            year += 1
            d = date(year, MONTHS[mon], int(day))
        if consecutive and prev:
            d = prev + timedelta(weeks=1)
        out.append(d)
        prev = d
    return out


def first_year(rows):
    # Column D holds debut dates like "28-Jan-10"; the earliest one gives the starting year
    years = []
    for r in rows:
        try:
            years.append(datetime.strptime(r[3].strip(), '%d-%b-%y').year)
        except ValueError:
            pass
    return min(years)


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]
    consecutive = '--consecutive' in sys.argv
    plays_csv = paths[2] if len(paths) > 2 else None  # optional "Plays - Country" export (Song, LW, TW columns)
    old = json.load(open('data.json', encoding='utf-8'))

    artists = {norm(a['name']): a for a in old['artists']}
    next_art = max(int(a['id'].split('_')[1]) for a in old['artists']) + 1

    def artist_for(name):
        nonlocal next_art
        a = artists.get(norm(name))
        if a is None:
            a = artists[norm(name)] = {'id': f'art_{next_art}', 'name': name}
            next_art += 1
        return a

    data = {'meta': {}, 'artists': [], 'songs': [], 'facts': []}
    for key, idx, hist, prefix, plays_head, size in CHARTS:
        rows_all = list(csv.reader(open(paths[idx], encoding='utf-8')))
        head, rows = rows_all[1], [r for r in rows_all[2:] if len(r) > 3 and r[1].strip()]
        cols = [i for i, h in enumerate(head) if WEEK_LABEL.fullmatch(h.strip())]
        dates = week_dates(head, cols, first_year(rows), consecutive)
        plays_col = head.index(plays_head) if plays_head in head else None

        old_by_name = {}
        for s in old['songs']:
            if s['chart'] == key:
                old_by_name.setdefault(norm(s['name']), []).append(s)
        used = set()
        old_ids = {s['id']: s for s in old['songs'] if s['chart'] == key}
        next_id = max(int(s['id'].split('_')[-1]) for s in old['songs'] if s['chart'] == key) + 1

        # Will's written "Chart Fact" lines sit in rows of their own, one cell per week
        for r in rows:
            if r[1].strip().startswith('Chart Fact'):
                data['facts'] += [{'week': d.isoformat(), 'chart': key, 'text': r[c].strip()}
                                  for d, c in zip(dates, cols) if r[c].strip()]

        songs, weekly = [], [[] for _ in cols]
        for r in rows:
            run = [(i, int(r[c])) for i, c in enumerate(cols)
                   if re.fullmatch(r'\d+', r[c].strip()) and 1 <= int(r[c]) <= size]
            if not run:
                continue
            artist_name = r[2].strip().replace('; ', ', ')
            debut = dates[run[0][0]].isoformat()
            cands = [s for s in old_by_name.get(norm(r[1]), []) if s['id'] not in used]
            # Country rows are numbered like the old song ids, which survives title edits
            by_row = old_ids.get(f'{prefix}{r[0].strip()}')
            if key == 'willboard' and not cands and by_row and by_row['id'] not in used:
                cands = [by_row]
            cands.sort(key=lambda s: (s['debutDate'] != debut, norm(s['artistName']) != norm(artist_name)))
            if cands:
                sid = cands[0]['id']
            else:
                sid, next_id = f'{prefix}{next_id}', next_id + 1
            used.add(sid)
            # Songs already on the site keep their cleaned-up title and artist credit
            name = r[1].strip()
            if cands:
                name, artist_name, a = cands[0]['name'], cands[0]['artistName'], {'id': cands[0]['artistId']}
            else:
                a = artist_for(artist_name.split(',')[0].strip())
            plays = r[plays_col].strip().replace(',', '') if plays_col is not None else ''
            songs.append({'id': sid, 'name': name, 'chart': key, 'debutDate': debut,
                          'peakPosition': min(p for _, p in run),
                          'itunesPlays': int(plays) if plays.isdigit() else None,
                          'totalPoints': sum(points(p) for _, p in run),
                          'weeksOnChart': len(run), 'artistId': a['id'], 'artistName': artist_name})
            for n, (i, p) in enumerate(run, 1):
                weekly[i].append({'songId': sid, 'position': p, 'plays': None, 'weeks': n})

        # Weekly running play counts aren't in the archive; keep the ones data.json already has
        old_plays = {(w['week'], e['songId']): e.get('plays') for w in old.get(key, []) for e in w['entries']}
        for d, entries in zip(dates, weekly):
            for e in entries:
                e['plays'] = old_plays.get((d.isoformat(), e['songId']))
        by_id = {s['id']: s for s in songs}
        history, prev = [], {}
        for d, entries in zip(dates, weekly):
            if not entries:
                continue
            entries.sort(key=lambda e: e['position'])
            top = by_id[entries[0]['songId']]
            h = {'week': d.isoformat(), 'no1': {'songId': top['id'], 'songName': top['name'],
                                                'artistName': top['artistName'], 'plays': None}}
            debuts = [e for e in entries if e['weeks'] == 1]
            climbs = [(prev[e['songId']] - e['position'], e) for e in entries
                      if prev.get(e['songId'], 0) > e['position']]
            if debuts:
                e = debuts[0]
                h['notable'] = {'type': 'hotshot', 'position': e['position']}
            elif climbs:
                gain, e = max(climbs, key=lambda c: c[0])
                h['notable'] = {'type': 'mover', 'gain': gain, 'position': e['position']}
            if 'notable' in h:
                s = by_id[e['songId']]
                h['notable'].update(songId=s['id'], songName=s['name'], artistName=s['artistName'])
            history.append(h)
            prev = {e['songId']: e['position'] for e in entries}

        # A song's play count is a running total, so its latest figure is the largest one seen
        for w in weekly:
            for e in w:
                if e['plays'] is not None:
                    s = by_id[e['songId']]
                    s['itunesPlays'] = max(s['itunesPlays'] or 0, e['plays'])
        if key == 'willboard' and plays_csv:
            totals = {norm(r[0]): int(r[2]) for r in csv.reader(open(plays_csv, encoding='utf-8'))
                      if len(r) > 2 and r[2].strip().isdigit()}
            for s in songs:
                t = totals.get(norm(s['name']))
                if t:
                    s['itunesPlays'] = max(s['itunesPlays'] or 0, t)
        data['songs'] += songs
        data[hist] = history
        data[key] = [{'week': d.isoformat(), 'entries': e} for d, e in zip(dates, weekly) if e][-KEEP_WEEKS:]
        data['meta']['wbLastWeek' if key == 'willboard' else 'popLastWeek'] = data[key][-1]['week']
        print(f'{key}: {len(songs)} songs, {len(history)} weeks, {history[0]["week"]} to {history[-1]["week"]}')

    old_ids = {a['id'] for a in old['artists']}
    data['artists'] = old['artists'] + [a for a in artists.values() if a['id'] not in old_ids]
    data['meta']['generated'] = datetime.now().isoformat(timespec='seconds')
    data['facts'].sort(key=lambda f: f['week'])
    out = {k: data[k] for k in ('meta', 'artists', 'songs', 'willboard', 'pop', 'wbHistory', 'popHistory', 'facts')}
    json.dump(out, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
