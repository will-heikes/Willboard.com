#!/usr/bin/env python3
"""Fill missing weeks in data.json from Will's full-history CSV exports of CS Era Points.

    python3 tools/catch_up.py country.csv pop.csv [--dry-run]

Each CSV is the Country or Pop tab as downloaded: row 2 holds the headers,
song/artist in columns B/C and one column per chart week labelled like "15-Oct".
The week labels carry no year, so the column of the last week already in
data.json is found by its label and checked against data.json before anything
after it is added.
"""
import csv
import json
import re
import sys
from datetime import date, datetime

from add_week import apply_week, norm


def week_columns(path, last_week, known_entries, song_name):
    rows = list(csv.reader(open(path, encoding='utf-8')))
    head = rows[1]
    label = f'{last_week.day}-{last_week.strftime("%b")}'
    col = max(i for i, h in enumerate(head) if h.strip() == label)
    chart = {int(r[col]): r[1] for r in rows[2:] if re.fullmatch(r'\d+', r[col].strip())}
    if any(norm(chart.get(e['position'])) != norm(song_name[e['songId']]) for e in known_entries):
        sys.exit(f'{path}: column {label} does not match data.json for {last_week}; stopping.')
    out = []
    for c in range(col + 1, len(head)):
        if not re.fullmatch(r'\d{1,2}-[A-Z][a-z]{2}', head[c].strip()):
            break
        entries = sorted(({'position': int(r[c]), 'name': r[1].strip(),
                           'artist': r[2].strip().replace('; ', ', '), 'plays': None}
                          for r in rows[2:] if re.fullmatch(r'\d+', r[c].strip())), key=lambda e: e['position'])
        if entries:
            out.append((head[c].strip(), entries))
    return out


def label_to_date(label, after):
    d = datetime.strptime(f'{label}-{after.year}', '%d-%b-%Y').date()
    return d if d > after else d.replace(year=after.year + 1)


def main():
    country, pop = [a for a in sys.argv[1:] if not a.startswith('--')]
    data = json.load(open('data.json', encoding='utf-8'))
    names = {s['id']: s['name'] for s in data['songs']}
    cols = {}
    for key, path in (('willboard', country), ('pop', pop)):
        last = date.fromisoformat(data[key][-1]['week'])
        cols[key] = week_columns(path, last, data[key][-1]['entries'], names)
    if [l for l, _ in cols['willboard']] != [l for l, _ in cols['pop']]:
        sys.exit('Country and Pop tabs list different weeks; stopping.')
    after = date.fromisoformat(data['willboard'][-1]['week'])
    for (label, wb), (_, pp) in zip(cols['willboard'], cols['pop']):
        when = label_to_date(label, after)
        print(f'--- {when}')
        print('\n'.join(apply_week(data, when, {'willboard': wb, 'pop': pp}, allow_gap=True)))
        after = when
    if '--dry-run' not in sys.argv:
        json.dump(data, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        print(f'data.json updated through {after}.')


if __name__ == '__main__':
    main()
