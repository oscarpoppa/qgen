#!/usr/bin/env python
from random import randint
from re import sub, search, split
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem
from json import dumps, loads

#should this be here?
class V2CProb:
    funcs = {'randint':randint, 'ri':randint}
    mainpatt = r'{{([^}]*)}}'

    def __init__(self, vp, cq):
        self.vp = vp
        self.cq = cq 
        self.raw_text = vp.raw_prob
        self.conc_text = ''
        self.raw_ansr = vp.raw_answer
        self.conc_ansr = ''
        self.symbols = {}
    
    def extract_symbol(self, chunk):
        patt = r'(?P<symbol>\w+)\s*:\s*(?P<func>\w+)\((?P<args>.+)\)'
        mo = search(patt, chunk.group(0))
        if not mo:
            return chunk.group(0)
        pdict = mo.groupdict()
        args = split('\W+', pdict['args'])
        if pdict['func'] in V2CProb.funcs:
            func = V2CProb.funcs[pdict['func']]
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
        self.conc_text = sub(V2CProb.mainpatt, self.extract_symbol, self.raw_text)
        return self.conc_text
    
    def gen_conc_ansr(self):
        # !! must be called after gen_conc_text
        ans_upd = sub(V2CProb.mainpatt, self.upt_ansr, self.raw_ansr)
        # not for prime time b4 this is locked down
        self.conc_ansr = str(eval(ans_upd))
        return self.conc_ansr

    def gen_conc_to_db(self):
        ct = self.gen_conc_text() 
        ca = self.gen_conc_ansr() 
        nuconc = CProblem(cquiz_id=self.cq.id, conc_prob=ct, conc_answer=ca, vproblem_id=self.vp.id, requestor=1)
        nuconc.save()
        return nuconc


# dct is some posted data - may be jsonified already
def create_vquiz(dct):
    nuquiz = VQuiz(vpid_dict=dumps(dct), author_id=1)
    nuquiz.save()
    for pid in dct.values():
        prob = VProblem.query.filter_by(id=pid).first()
        nuquiz.vproblems.append(prob)
    nuquiz.save()
    return nuquiz

def create_cquiz(vquiz):
    nuquiz = CQuiz(vquiz_id=vquiz.id)
    nuquiz.save()
    for vp in vquiz.vproblems:
        cp = V2CProb(vp, nuquiz).gen_conc_to_db()
        nuquiz.cproblems.append(cp)
    nuquiz.save()
    return nuquiz

def dump_cquiz(cquiz):
    for cp in cquiz.cproblems:
        print('{}\n({})\n\n'.format(cp.conc_prob, cp.conc_answer))

