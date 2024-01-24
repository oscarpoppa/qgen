#!/usr/bin/env python
from random import randint
from re import sub, search, split
from app.qgen.models import VProblem, CProblem

#should this be here?
class P2C:
    funcs = {'randint':randint, 'ri':randint}
    mainpatt = r'{{([^}]*)}}'

    def __init__(self, pid):
        self.pid = pid
        record = VProblem.query.filter_by(id=self.pid).first()
        if not record:
            raise KeyError('pattern id {} not found'.format(self.pid))
        self.raw_text = record.raw_prob
        self.conc_text = ''
        self.raw_ansr = record.raw_answer
        self.conc_ansr = ''
        self.symbols = {}
    
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
    
    def gen_conc_text(self):
        self.conc_text = sub(P2C.mainpatt, self.extract_symbol, self.raw_text)
        return self.conc_text
    
    def gen_conc_ansr(self):
        # !! must be called after gen_conc_text
        ans_upd = sub(P2C.mainpatt, self.upt_ansr, self.raw_ansr)
        # not for prime time b4 this is locked down
        self.conc_ansr = str(eval(ans_upd))
        return self.conc_ansr

    def gen_conc_to_db(self):
        ct = self.gen_conc_text() 
        ca = self.gen_conc_ansr() 
        nuconc = CProblem(conc_prob=ct, conc_answer=ca, vparent=self.pid, requestor=1)
        nuconc.save()
        return nuconc.id

