#!/usr/bin/env python
from app.qgen import qgen_bp
from random import randint
from re import sub, search, split
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem
from json import dumps, loads
from flask import flash, render_template, render_template_string, redirect, url_for, request
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField

top = """
{% extends "base.html" %}

{% block content %}
"""

ftop = """
    <form action="" method="post">
        {{ form.hidden_tag() }}
"""

fbottom = """
        {{ form.submit() }}
    </form>
"""

bottom = """
{% endblock %}
"""

header = """
<b>{{ name }}</b><br><br>
"""

capsule = """
    {}. {}<br>{}<br><br>
"""

otfelem = 'Number{}'

class OTF(FlaskForm):
    @property
    def result_template(self):
        psections = [header]
        for num in range(1, int(self.count)+1):
            name = otfelem.format(num)
            submitted_ansr = getattr(self, name).data or 'None'
            correct_ansr = getattr(self, name+'_ansr')
            problem = getattr(self, name+'_prob')
            rez = 'W'
            try:
                if submitted_ansr != 'None' and abs(float(submitted_ansr) - float(correct_ansr)) < 0.1:
                    rez = 'R'
            except:
                pass
            msg = '({}) Your answer: {} : Correct answer: {}'.format(rez, submitted_ansr, correct_ansr)
            ptxt = capsule.format(num, problem, msg)
            psections += ptxt
        ptext = ''.join(psections)
        return top+ptext+bottom


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


# lst is some posted data - may be jsonified already
# lst is reap ptyhon list
def create_vquiz(lst):
    nuquiz = VQuiz(vpid_lst=dumps(lst), author_id=1)
    nuquiz.save()
    probs = VProblem.query.filter(VProblem.id.in_(lst)).all()
    nuquiz.vproblems.extend(probs)
    nuquiz.save()
    return nuquiz

def create_cquiz(vquiz):
    nuquiz = CQuiz(vquiz_id=vquiz.id)
    nuquiz.save()
    probs = [V2CProb(vp, nuquiz).gen_conc_to_db() for vp in vquiz.vproblems]
    nuquiz.cproblems.extend(probs)
    nuquiz.save()
    return nuquiz

def create_renderables(cquiz):
    count = 0
    ftypes = {'text':StringField, 'txt':StringField, 'string':StringField}
    ttlst = [header]
    for number, problem in enumerate(cquiz.cproblems, 1):
        count += 1
        name = otfelem.format(number)
        inpstr = '{{ '+'form.{}'.format(name)+' }}'
        ptxt = capsule.format(number, problem.conc_prob, inpstr)
        ttlst += ptxt
        ftype = ftypes[problem.vproblem.form_elem]
        setattr(OTF, name, ftype(name)) 
        setattr(OTF, name+'_ansr', problem.conc_answer) 
        setattr(OTF, name+'_prob', problem.conc_prob) 
    setattr(OTF, 'submit', SubmitField('Submit'))
    setattr(OTF, 'count', count)
    ttext = ''.join(ttlst)
    templ = top+ftop+ttext+fbottom+bottom
    return templ, OTF


#POC
@qgen_bp.route('/quiz/alpha', methods=['GET','POST'])
def alpha():
    cq = CQuiz.query.all()[-2]
    templ, cform = create_renderables(cq)
    form = cform()
    if form.validate_on_submit():
        return render_template_string(form.result_template, name='Quiz Alpha')
    return render_template_string(templ, name='Quiz Alpha', form=form)

