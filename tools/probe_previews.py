"""Print Deezer and Apple candidates (diagnostic only)."""
import json, sys, urllib.parse, time
from fetch_artist_photos import get
for q in sys.argv[1:]:
    print('=== DEEZER', q)
    for h in json.loads(get('https://api.deezer.com/search/track?limit=15&q=' + urllib.parse.quote(q))).get('data', []):
        print(f"  {h['id']} | {h.get('title')} | {h['artist']['name']} | {h['album']['title']} | {h.get('duration')}s | rank {h.get('rank')}")
    time.sleep(3)
    print('=== APPLE', q)
    for h in json.loads(get('https://itunes.apple.com/search?entity=song&country=us&limit=15&term=' + urllib.parse.quote(q))).get('results', []):
        print(f"  {h['trackId']} | {h.get('trackName')} | {h.get('artistName')} | {h.get('collectionName')} | {h.get('releaseDate','')[:10]} | {h.get('trackTimeMillis', 0)//1000}s")
