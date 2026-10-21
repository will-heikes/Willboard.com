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


ORD = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']


def ordinal(n):
    if n < len(ORD):
        return ORD[n]
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def lead_artist(name):
    return re.split(r',| & | ft\.? | feat\.? | x | with ', name or '', flags=re.I)[0].strip()


POP_CERTS = (1250, 2500, 1250)  # gold, platinum, each extra platinum


def pop_cert(pts):
    gold, plat, step = POP_CERTS
    if pts < gold:
        return None
    if pts < plat:
        return 'Gold'
    x = 1 + (pts - plat) // step
    return f'{x}x Platinum' if x > 1 else 'Platinum'


def archive_facts(key, dates, weekly, by_id, names, per_week=3):
    """Write short chart stories for every week: first top fives, certifications, debuts, milestones.

    Returns [{week, chart, type, score, text, artist}], the best few per week."""
    label = 'Hot 20' if key == 'willboard' else 'Pop 10'
    best, wks, pts = {}, {}, {}
    art_top5, art_top10, art_no1, art_seen = {}, {}, {}, set()
    out, prev, n_week = [], {}, 1
    for d, entries in zip(dates, weekly):
        if not entries:
            continue
        facts = []

        def add(kind, score, text, s):
            # In a chart's first year every act is new to it, so "first" stories would mislead
            if n_week <= 52 and ('first' in text):
                return
            facts.append({'week': d.isoformat(), 'chart': key, 'type': kind, 'score': score,
                          'text': text, 'artist': s['artistName']})

        debuts = [e for e in entries if e['songId'] not in best]
        top_debut = min(debuts, key=lambda e: e['position'])['songId'] if debuts else None
        top5_now = {}
        for e in sorted(entries, key=lambda e: e['position']):
            s, p, sid = by_id[e['songId']], e['position'], e['songId']
            aid = s['artistId']
            a = names.get(aid) or lead_artist(s['artistName'])
            t = f"\u2018{s['name']}\u2019"
            lw = prev.get(sid)
            move = f'rises {lw}-{p}' if lw else (f'debuts at #{p}' if sid not in best else f're-enters at #{p}')
            was = best.get(sid, 99)
            if sid not in best and aid not in art_seen:
                add('debut', 6 if p <= 10 else 4, f'{a} makes a first appearance on the {label} as {t} debuts at #{p}', s)
            elif sid == top_debut and p <= 10:
                add('debut', 3, f'{a} enters at #{p} with {t}, the week\'s highest debut', s)
            if p == 1 and was > 1:
                art_no1.setdefault(aid, set()).add(sid)
                k = len(art_no1[aid])
                if k == 1:
                    add('no1', 7, f'{a} earns a first {label} #1 as {t} {move}', s)
                else:
                    add('no1', 4, f'{t} {move}, giving {a} a {ordinal(k)} #1 hit', s)
            if p <= 5 and was > 5:
                art_top5.setdefault(aid, set()).add(sid)
                k = len(art_top5[aid])
                if p > 1:
                    if k == 1:
                        add('top5', 8, f'{a} earns a first {label} top five hit as {t} {move}', s)
                    elif k % 5 == 0:
                        add('top5', 7, f'{a} scores a {ordinal(k)} career top five with {t}, which {move}', s)
                    else:
                        add('top5', 3, f'{t} {move}, the {ordinal(k)} top five hit for {a}', s)
            if key == 'willboard' and p <= 10 and was > 10:
                art_top10.setdefault(aid, set()).add(sid)
                if len(art_top10[aid]) == 1 and p > 5:
                    add('top10', 6, f'{a} reaches the top ten for the first time as {t} {move}', s)
            if lw and lw - p >= 6:
                add('leap', 5, f'{t} leaps {lw}-{p} for {a}, one of the biggest climbs of the week', s)
            wks[sid] = wks.get(sid, 0) + 1
            if wks[sid] in (20, 30, 40, 50):
                add('weeks', 4, f'{t} by {a} logs a {ordinal(wks[sid])} week on the chart, now at #{p}', s)
            if key == 'pop':
                before = pop_cert(pts.get(sid, 0))
                pts[sid] = pts.get(sid, 0) + points(p)
                after = pop_cert(pts[sid])
                if after and after != before:
                    add('cert', 7 if 'Platinum' in after else 5, f'{t} by {a} goes {after.replace("x", "\u00d7")} with {pts[sid]:,} career chart points', s)
            if p <= 5:
                top5_now.setdefault(aid, []).append((p, s))
            best[sid] = min(was, p)
            art_seen.add(aid)
        for aid, hits in top5_now.items():
            if len(hits) >= 2 and any(prev.get(s['id'], 99) > 5 for _, s in hits):
                a = names.get(aid) or lead_artist(hits[0][1]['artistName'])
                pair = ' and '.join(f"\u2018{s['name']}\u2019 (#{p})" for p, s in hits)
                add('double', 6, f'{a} holds {len(hits)} of the top five spots this week with {pair}', hits[0][1])
        facts.sort(key=lambda f: -f['score'])
        if n_week > 8:  # the opening weeks of a chart are all firsts, so skip them
            out += facts[:per_week]
        n_week += 1
        prev = {e['songId']: e['position'] for e in entries}
    return out


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
    archive = []  # auto-written stories for past weeks, saved to archive.json
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
        archive += archive_facts(key, dates, weekly, by_id, {a['id']: a['name'] for a in artists.values()})
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
    archive.sort(key=lambda f: (f['week'], f['chart'], -f['score']))
    json.dump(archive, open('archive.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'archive.json: {len(archive)} stories')


if __name__ == '__main__':
    main()
