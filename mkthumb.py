#!/usr/bin/env python

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
    except Exception as exc:
        print(str(exc))
        print('{} failed'.format(fname))

