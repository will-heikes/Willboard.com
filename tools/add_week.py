#!/usr/bin/env python3
"""Add one chart week to data.json from the "Current Week 2" tab of CS Era Points.

    python3 tools/add_week.py current_week.csv [--allow-gap] [--dry-run]

The CSV is that tab exported as-is: Hot 20 in columns A-I, Pop 10 in K-S,
each entry on two rows (song, then artist), the chart date in row 1.
Points per week follow Will's table: #1-#5 = 500/400/300/200/100,
then #6 = 95 down to #20 = 81.
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta

KEEP_WEEKS = 52


def points(pos):
    return (6 - pos) * 100 if pos <= 5 else 101 - pos


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def num(s):
    s = (s or '').strip()
    return int(s) if re.fullmatch(r'-?\d+', s) else None


def parse(path):
    rows = list(csv.reader(open(path, encoding='utf-8')))
    when = None
    for cell in rows[0]:
        try:
            when = datetime.strptime(cell.strip(), '%B %d, %Y').date()
            break
        except ValueError:
            pass
    if not when:
        sys.exit('Could not find the chart date in the first row.')

    def block(c_pos, c_title, c_plays):
        out = []
        for i in range(2, len(rows) - 1, 2):
            song, artist = rows[i], rows[i + 1]
            pos = num(song[c_pos]) if len(song) > c_pos else None
            if pos is None:
                continue
            out.append({'position': pos, 'name': song[c_title].strip(),
                        'artist': artist[c_title].strip(), 'plays': num(song[c_plays])})
        return out

    # Pop's column R is a running points total, not weekly plays
    wb = block(0, 3, 7)
    pop = [dict(e, plays=None) for e in block(10, 13, 17)]
    return when, wb, pop


def load_runs():
    try:
        return json.load(open('runs.json', encoding='utf-8'))
    except FileNotFoundError:
        return None


def add_to_runs(runs, key, week, entries):
    """runs.json holds every song's full chart run for the song pages:
    {chart: {'weeks': [dates], 'runs': {songId: [first week index, pos, pos, 0 (off chart), pos, ...]}}}"""
    c = runs.setdefault(key, {'weeks': [], 'runs': {}})
    if c['weeks'] and c['weeks'][-1] >= week:
        return
    c['weeks'].append(week)
    i = len(c['weeks']) - 1
    for e in entries:
        r = c['runs'].setdefault(e['songId'], [i])
        r.extend([0] * (i - (r[0] + len(r) - 1)))
        r.append(e['position'])


def apply_week(data, when, charts, allow_gap=False, runs=None):
    """Append one week (charts = {'willboard': [...], 'pop': [...]}) to data. Returns report lines."""
    week = when.isoformat()
    songs = data['songs']
    artists = {norm(a['name']): a for a in data['artists']}
    next_art = max(int(a['id'].split('_')[1]) for a in data['artists']) + 1
    report = []

    for key, hist, prefix in (('willboard', 'wbHistory', 'song_'), ('pop', 'popHistory', 'pop_song_')):
        weeks = data[key]
        last = date.fromisoformat(weeks[-1]['week'])
        if when <= last:
            sys.exit(f'{key}: week {week} is already in data.json (last week is {last}).')
        if when - last != timedelta(days=7) and not allow_gap:
            sys.exit(f'{key}: {week} is not the week after {last}. Fill the gap first, or pass --allow-gap.')

        prev = {e['songId']: e['position'] for e in weeks[-1]['entries']}
        on_chart = {e['songId'] for w in weeks[-8:] for e in w['entries']}
        by_name = {}
        for s in songs:
            if s['chart'] == key:
                by_name.setdefault(norm(s['name']), []).append(s)
        next_id = max(int(s['id'].split('_')[-1]) for s in songs if s['chart'] == key) + 1

        entries = []
        for e in charts[key]:
            cands = by_name.get(norm(e['name']), [])
            # Prefer a song charting recently, then one by the same lead artist
            cands.sort(key=lambda s: (s['id'] not in on_chart, norm(s['artistName']) != norm(e['artist'])))
            s = cands[0] if cands else None
            if s is None:
                a = artists.get(norm(e['artist']))
                if a is None:
                    a = {'id': f'art_{next_art}', 'name': e['artist']}
                    next_art += 1
                    data['artists'].append(a)
                    artists[norm(a['name'])] = a
                s = {'id': f'{prefix}{next_id}', 'name': e['name'], 'chart': key, 'debutDate': week,
                     'peakPosition': None, 'itunesPlays': None, 'totalPoints': 0,
                     'artistId': a['id'], 'artistName': e['artist']}
                next_id += 1
                songs.append(s)
                by_name.setdefault(norm(s['name']), []).append(s)
                report.append(f'{key}: new song "{s["name"]}" by {s["artistName"]} at #{e["position"]}')
            s['totalPoints'] = (s['totalPoints'] or 0) + points(e['position'])
            s['peakPosition'] = min(s['peakPosition'] or 99, e['position'])
            s['weeksOnChart'] = (s.get('weeksOnChart') or 0) + 1
            if e['plays'] is not None:
                s['itunesPlays'] = max(s['itunesPlays'] or 0, e['plays'])
            entries.append({'songId': s['id'], 'position': e['position'], 'plays': e['plays'],
                            'weeks': s['weeksOnChart'], '_s': s})

        # #1 and the week's notable event: best debut, else biggest climb
        top = entries[0]['_s']
        notable = None
        debuts = [x for x in entries if x['songId'] not in prev]
        if debuts:
            x = min(debuts, key=lambda x: x['position'])
            notable = {'type': 'hotshot', 'position': x['position']}
        else:
            climbs = [(prev[x['songId']] - x['position'], x) for x in entries if prev[x['songId']] > x['position']]
            if climbs:
                gain, x = max(climbs, key=lambda c: c[0])
                notable = {'type': 'mover', 'gain': gain, 'position': x['position']}
        h = {'week': week, 'no1': {'songId': top['id'], 'songName': top['name'], 'artistName': top['artistName'],
                                   'plays': entries[0]['plays']}}
        if notable:
            notable.update(songId=x['songId'], songName=x['_s']['name'], artistName=x['_s']['artistName'])
            h['notable'] = notable
        data[hist].append(h)

        weeks.append({'week': week, 'entries': [{k: v for k, v in x.items() if k != '_s'} for x in entries]})
        if runs is not None:
            add_to_runs(runs, key, week, entries)
        del weeks[:-KEEP_WEEKS]
        report.append(f'{key}: #1 is "{top["name"]}" by {top["artistName"]}')

    data['meta'].update(generated=datetime.now().isoformat(timespec='seconds'),
                        wbLastWeek=week, popLastWeek=week)
    return report


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    allow_gap, dry = '--allow-gap' in sys.argv, '--dry-run' in sys.argv
    charts = {}
    when, charts['willboard'], charts['pop'] = parse(args[0])
    week = when.isoformat()
    data, runs = json.load(open('data.json', encoding='utf-8')), load_runs()
    print('\n'.join(apply_week(data, when, charts, allow_gap, runs)))
    if not dry:
        json.dump(data, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        if runs is not None:
            json.dump(runs, open('runs.json', 'w', encoding='utf-8'), separators=(',', ':'))
        print(f'data.json updated through {week}.')


if __name__ == '__main__':
    main()
