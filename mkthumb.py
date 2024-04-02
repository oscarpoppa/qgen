#!/usr/bin/env python
# Intended for after-the-fact thumbnailization from within static. Not needed if app used to upload.
from PIL import Image
from sys import stdin

for fname in stdin:
    fname = fname.rstrip('\n')
    print(fname)
    if fname.startswith('T_'):
        print('{} already done'.format(fname))
        continue
    try:
        im = Image.open(fname)    
        im.thumbnail((128, 128))
        tname = 'T_' + fname
        im.save(tname)
        print('{} created'.format(tname))
    except Exception as exc:
        print(str(exc))
        print('{} thumbnailization failed'.format(fname))

