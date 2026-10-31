"""Print Deezer and Apple candidates for a few songs (diagnostic only)."""
import json, sys, urllib.parse, time
from fetch_artist_photos import get
for q in sys.argv[1:]:
    print('=== DEEZER', q)
    for h in json.loads(get('https://api.deezer.com/search/track?limit=25&q=' + urllib.parse.quote(q))).get('data', []):
        print(f"  {h['id']} | {h.get('title')} | v={h.get('title_version')} | {h['artist']['name']} | {h['album']['title']} | {h.get('duration')}s | rank {h.get('rank')} | prev={bool(h.get('preview'))}")
    time.sleep(3)
    print('=== APPLE', q)
    for h in json.loads(get('https://itunes.apple.com/search?entity=song&country=us&limit=25&term=' + urllib.parse.quote(q))).get('results', []):
        print(f"  {h['trackId']} | {h.get('trackName')} | {h.get('artistName')} | {h.get('collectionName')} | {h.get('trackTimeMillis', 0)//1000}s | {h.get('previewUrl')}")
for i in (136258284,):
    print('=== DEEZER TRACK', i, get(f'https://api.deezer.com/track/{i}')[:600])
