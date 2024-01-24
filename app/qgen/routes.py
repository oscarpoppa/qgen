#!/usr/bin/env python
from random import randint
from re import sub, search, split
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem, VQuizProblem, CQuizProblem
from json import dumps, loads

#should this be here?
class V2CProb:
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
        nuconc = CProblem(conc_prob=ct, conc_answer=ca, vparent=self.pid, requestor=1)
        nuconc.save()
        return nuconc.id


# dct is some posted data - may be jsonified already
def create_vquiz(dct):
    nuquiz = VQuiz(vpid_dict=dumps(dct), author_id=1)
    nuquiz.save()
    qid = nuquiz.id
    for pid in dct.values():
        vqp = VQuizProblem(vq_id=qid, vp_id=pid)
        vqp.save()
    return qid


def create_cquiz(vqid):
    cquiz = CQuiz(vparent=vqid)
    cquiz.save()
    cqid = cquiz.id
    vquiz = VQuiz.query.filter_by(id=vqid).first()
    entries = VQuizProblem.query.filter_by(vq_id=vqid).all()
    vpids = [a.vp_id for a in entries]
    for vid in vpids:
        cpid = V2CProb(vid).gen_conc_to_db()
        cqp = CQuizProblem(cq_id=cqid, cp_id=cpid)
        cqp.save()
    return cqid


def dump_cquiz(cqid):
    # figure out how to nest these...
    cq = CQuiz.query.filter_by(id=cqid).first()
    cqp = VQuiz.query.filter_by(id=cq.vparent)
    entries = CQuizProblem.query.filter_by(cq_id=cqid).all()
    cpids = [a.cp_id for a in entries]
    for pid in cpids:
        x = CProblem.query.filter_by(id=pid).first()
        print('{}\n({})\n\n'.format(x.conc_prob, x.conc_answer))

