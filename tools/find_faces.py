#!/usr/bin/env python3
"""Find the face in each artist photo so square tiles crop around it instead of the middle.

    pip install "opencv-python-headless<5"   # OpenCV 5 dropped the face finders used here
    python3 tools/find_faces.py            # photos not yet in focus.json
    python3 tools/find_faces.py --all      # every photo again

Run from the repo folder. Writes images/artists/focus.json: {"carly-pearce-2022.jpg": [50, 8], ...},
the CSS object-position (in %) that puts the face in the middle of a square crop. The site
applies it to the photo. Photos with no face found are left out and crop from the middle.
Square photos are skipped too, since a square tile shows all of them.
"""
import json
import os
import sys

import cv2

DIR = 'images/artists'
OUT = os.path.join(DIR, 'focus.json')


def square_pos(c, ratio):
    """object-position along one side that centres point c (0-1) in a square crop.
    ratio is that side's length over the other side's; at 1 or less nothing is cropped."""
    if ratio <= 1:
        return .5
    return min(1, max(0, (c * ratio - .5) / (ratio - 1)))


def find(cascade, grey, size, near):
    """Faces as (x, y, w, h), also looking with the photo turned a little each way,
    since the finder misses a tilted head (one leaning on a duo partner, say)."""
    h, w = grey.shape
    faces = []
    for angle in (0, -15, 15):
        turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
        back = cv2.invertAffineTransform(turn)
        for x, y, fw, fh in cascade.detectMultiScale(cv2.warpAffine(grey, turn, (w, h)) if angle else grey, 1.1, near, minSize=(size, size)):
            cx, cy = back @ (x + fw / 2, y + fh / 2, 1)
            # A turned photo throws up stray "faces", so take only a partner for one already found
            # upright: about the same size and height. The same face found again counts once.
            if angle and not any(.75 < fw / f[2] < 1.33 and abs(cy - (f[1] + f[3] / 2)) < f[3] for f in faces):
                continue
            if all(abs(cx - (f[0] + f[2] / 2)) > fw / 2 or abs(cy - (f[1] + f[3] / 2)) > fh / 2 for f in faces):
                faces.append((cx - fw / 2, cy - fh / 2, fw, fh))
    return faces


def main():
    redo = '--all' in sys.argv
    focus = {} if redo or not os.path.exists(OUT) else json.load(open(OUT, encoding='utf-8'))
    # File sizes as last checked, so a photo replaced under the same name is looked at again
    sizes = focus.pop('#sizes', {})
    front = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    side = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
    found = missed = 0
    for name in sorted(os.listdir(DIR)):
        size_now = os.path.getsize(os.path.join(DIR, name)) if name.endswith('.jpg') else 0
        if not name.endswith('.jpg') or sizes.get(name) == size_now:
            continue
        sizes[name] = size_now
        focus.pop(name, None)
        img = cv2.imread(os.path.join(DIR, name))  # .webp saved as .jpg reads fine too
        if img is None:
            continue
        h, w = img.shape[:2]
        if abs(w - h) < 0.05 * max(w, h):
            continue
        # Work on a copy about 600px across so huge uploads stay quick
        k = 600 / max(w, h)
        grey = cv2.equalizeHist(cv2.cvtColor(cv2.resize(img, None, fx=k, fy=k) if k < 1 else img, cv2.COLOR_BGR2GRAY))
        k = min(k, 1)
        size = int(min(grey.shape) * 0.06)
        faces = find(front, grey, size, 6) or [*side.detectMultiScale(grey, 1.1, 5, minSize=(size, size))]
        if not len(faces):
            missed += 1
            continue
        # In a tall photo a face sits in the top part; lower "faces" are hands, shirts and the like
        if h > w:
            faces = [f for f in faces if (f[1] + f[3] / 2) / k < 0.6 * h]
            if not faces:
                missed += 1
                continue
        # The biggest face, plus any near its size (a duo or group), sets the centre
        big = max(f[2] * f[3] for f in faces)
        group = [f for f in faces if f[2] * f[3] >= big / 2]
        x0, y0 = min(f[0] for f in group), min(f[1] for f in group)
        x1, y1 = max(f[0] + f[2] for f in group), max(f[1] + f[3] for f in group)
        cx, cy = (x0 + x1) / 2 / k / w, (y0 + y1) / 2 / k / h
        focus[name] = [round(square_pos(cx, w / h) * 100), round(square_pos(cy, h / w) * 100)]
        found += 1
    json.dump({**dict(sorted(focus.items())), '#sizes': dict(sorted(sizes.items()))}, open(OUT, 'w', encoding='utf-8'), indent=0)
    print(f'{found} faces found, {missed} photos without one, {len(focus)} in {OUT}')


if __name__ == '__main__':
    main()
