#!/usr/bin/env python
from random import randint
from re import sub, search, split
from app.qgen.models import Ppatt

#should this be here?
class P2C:
    funcs = {'randint':randint, 'ri':randint}
    mainpatt = r'{{([^}]*)}}'

    def __init__(self, pid):
        self.symbols = {}
        record = Ppatt.query.filter_by(id=pid).first()
        if not record:
            print('Not found')
        self.text = record.raw_prob
        self.ansr = record.raw_answer
    
    def extract_symbol(self, chunk):
        patt = r'(?P<symbol>\w+)\s*:\s*(?P<func>\w+)\((?P<args>.+)\)'
        mo = search(patt, chunk.group(0))
        if not mo:
            return chunk.group(0)
        pdict = mo.groupdict()
        args = split('\W+', pdict['args'])
        if pdict['func'] in P2C.funcs:
            func = P2C.funcs[pdict['func']]
            iargs = [int(z) for z in args]
            self.symbols[pdict['symbol']] = func(*iargs)
            return str(self.symbols[pdict['symbol']])
        return chunk(0)
    
    def upt_ansr(self, chunk):
        patt = r'(?P<symbol>\w+)'
        mo = search(patt, chunk.group(0))
        if not mo:
            return chunk.group(0)
        if not mo.group('symbol') in self.symbols:
            return chunk.group(0)
        return str(self.symbols[mo.group('symbol')])
    
    def final_text(self):
        upd = sub(P2C.mainpatt, self.extract_symbol, self.text)
        return upd
    
    def final_ansr(self):
        ans_upd = sub(P2C.mainpatt, self.upt_ansr, self.ansr)
        return str(eval(ans_upd)) ## !!!!!!

