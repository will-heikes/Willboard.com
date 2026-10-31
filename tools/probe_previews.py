"""Compare preview files (diagnostic only)."""
import hashlib, subprocess, sys, urllib.request
for u in sys.argv[1:]:
    b = urllib.request.urlopen(u).read()
    open('/tmp/p.m4a', 'wb').write(b)
    vol = subprocess.run(['ffmpeg', '-i', '/tmp/p.m4a', '-af', 'volumedetect,astats=metadata=0', '-f', 'null', '-'], capture_output=True, text=True).stderr
    keep = [l for l in vol.splitlines() if any(k in l for k in ('mean_volume', 'max_volume', 'Duration', 'Flat factor', 'RMS level dB', 'Zero crossings rate'))]
    print(u[-40:], len(b), hashlib.md5(b).hexdigest(), *keep[:8], sep='\n  ')
