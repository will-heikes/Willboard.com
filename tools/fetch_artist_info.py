#!/usr/bin/env python3
"""Look up each Willboard act on Wikidata: a person or a group, and a person's birth date and gender.

Run from the Willboard.com repo folder (next to data.json), or from the "Fetch artist photos" Action with "info" ticked:
    python3 tools/fetch_artist_info.py            # acts not yet in artist_info.json
    python3 tools/fetch_artist_info.py --all      # every act again

Writes artist_info.json: {"Carrie Underwood": {"type": "person", "born": "1983-03-10", "sex": "f", "wd": "Q190888"}, ...}
The site's Ask page uses it for questions like the youngest act to hit #1 or the first group at #1.
Acts it can't place are listed in artist_info_missing.txt; point one at the right search in SEARCH_AS below.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

OUT, MISSING = 'artist_info.json', 'artist_info_missing.txt'
API = 'https://www.wikidata.org/w/api.php?'
# What to search for when Will's spelling or the act's name finds the wrong thing
SEARCH_AS = {'Ariana Grade': 'Ariana Grande', 'Justin Biever': 'Justin Bieber'}
MUSIC = re.compile(r'singer|musician|rapper|\bband\b|\bduo\b|\btrio\b|\bgroup\b|\bDJ\b|producer|songwriter|vocalist|guitarist|composer|quartet|ensemble', re.I)
NOT_ACT = re.compile(r'\b(song|single|album|EP|film|episode|television|tour|video game|novel|book)\b', re.I)
GROUP = re.compile(r'\b(band|duo|trio|group|quartet|quintet|ensemble|collective|boy band|girl group|orchestra|choir)\b', re.I)
OCCUPATIONS = {'Q177220', 'Q639669', 'Q488205', 'Q36834', 'Q753110', 'Q2252262', 'Q130857', 'Q183945', 'Q855091', 'Q2643890', 'Q386854'}
SEX = {'Q6581072': 'f', 'Q6581097': 'm', 'Q1052281': 'f', 'Q2449503': 'm'}


def get(params):
    req = urllib.request.Request(API + urllib.parse.urlencode({**params, 'format': 'json'}),
                                 headers={'User-Agent': 'willboard-artist-info/1.0 (https://will-heikes.github.io/Willboard.com/)'})
    for tries in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 ** tries)
    return {}


def claim_ids(e, prop):
    return [c['mainsnak'].get('datavalue', {}).get('value', {}).get('id') for c in e.get('claims', {}).get(prop, [])]


def claim_date(e, prop):
    for c in e.get('claims', {}).get(prop, []):
        v = c['mainsnak'].get('datavalue', {}).get('value', {})
        # Only dates known to the day ("+1983-03-10T00:00:00Z", precision 11)
        if v.get('precision', 0) >= 11 and v.get('time'):
            return v['time'][1:11]
    return None


def describe(e):
    desc = e.get('descriptions', {}).get('en', {}).get('value', '')
    person = 'Q5' in claim_ids(e, 'P31')
    musician = (bool(OCCUPATIONS & set(claim_ids(e, 'P106'))) or bool(MUSIC.search(desc))) and (person or not NOT_ACT.search(desc))
    info = {'type': 'person' if person else 'group', 'wd': e['id'], 'about': desc}
    if person:
        if claim_date(e, 'P569'):
            info['born'] = claim_date(e, 'P569')
        sex = [SEX[q] for q in claim_ids(e, 'P21') if q in SEX]
        if sex:
            info['sex'] = sex[0]
    elif not GROUP.search(desc) and not claim_ids(e, 'P527'):
        info['type'] = 'other'
    return info, musician


def lookup(name):
    found = get({'action': 'wbsearchentities', 'search': SEARCH_AS.get(name, name), 'language': 'en', 'type': 'item', 'limit': 7}).get('search', [])
    ids = [f['id'] for f in found]
    if not ids:
        return None
    ents = get({'action': 'wbgetentities', 'ids': '|'.join(ids), 'props': 'claims|descriptions', 'languages': 'en'}).get('entities', {})
    # The first search result that is a musician or a music group
    for qid in ids:
        e = ents.get(qid)
        if not e:
            continue
        info, musician = describe(e)
        if musician:
            return info if info['type'] != 'other' else None
    return None


def main():
    data = json.load(open('data.json', encoding='utf-8'))
    have = {} if '--all' in sys.argv or not os.path.exists(OUT) else json.load(open(OUT, encoding='utf-8'))
    missing = []
    for a in sorted(data['artists'], key=lambda a: a['name']):
        name = a['name']
        if name in have:
            continue
        info = lookup(name)
        if info:
            have[name] = info
        else:
            missing.append(name)
        time.sleep(0.2)
    json.dump(dict(sorted(have.items())), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    open(MISSING, 'w', encoding='utf-8').write('\n'.join(missing) + '\n')
    people = sum(1 for v in have.values() if v['type'] == 'person')
    print(f'{len(have)} acts placed ({people} people, {len(have) - people} groups, '
          f'{sum(1 for v in have.values() if v.get("born"))} birth dates); {len(missing)} not found')


if __name__ == '__main__':
    main()
