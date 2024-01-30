#!/usr/bin/env python
from app import app
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
    <form action="" method="post">
        {{ form.hidden_tag() }}
"""

bottom = """
        {{ form.submit() }}
    </form>
{% endblock %}
"""

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

def create_template(cquiz):
    felems = []
    ttlst = ['''<b>{{ name }}</b><br><br>''']
    for number, problem in enumerate(cquiz.cproblems, 1):
        name = 'Number{}'.format(number)
        inpstr = '{{ '+'form.{}'.format(name)+' }}'
        felem = {'name':name, 'num':number, 'ansr':problem.conc_answer, 'form':problem.vproblem.form_elem}
        felems.append(felem)
        ptxt = '''{}. {}<br>{}<br><br>'''.format(number, problem.conc_prob, inpstr)
        ttlst += ptxt
    ttext = ''.join(ttlst)
    whole = top+ttext+bottom
    return whole, felems

def create_form(felems):
    ftypes = {'text':StringField, 'txt':StringField, 'string':StringField}
    class OTF(FlaskForm):
        pass

    for elem in felems:
       ftype = ftypes[elem['form']]
       setattr(OTF, elem['name'], ftype(elem['name'])) 
       setattr(OTF, elem['name']+'_ansr', elem['ansr']) 
    setattr(OTF, 'submit', SubmitField('Submit'))
    setattr(OTF, 'count', len(felems))
    return OTF

@app.route('/quiz/alpha', methods=['GET','POST'])
def alpha():
    cq = CQuiz.query.all()[-2]
    templ,fdata = create_template(cq)
    fcls = create_form(fdata)
    form = fcls()
    if form.validate_on_submit():
        for num in range(1, int(form.count)+1):
            name = 'Number{}'.format(num)
            st_ansr = getattr(form, name).data or 'None'
            cor_ansr = getattr(form, name+'_ansr')
            try:
                fsta = float(st_ansr)
                fcora = float(cor_ansr)
                if st_ansr != 'None' and abs(float(st_ansr) - float(cor_ansr)) < 0.1:
                   rez = 'Correct'
                else: 
                   rez = 'Wrong'
            except:
               rez = 'Wrong'
            msg = 'Your answer: {} : Correct answer: {} : {}'.format(st_ansr, cor_ansr, rez)
            setattr(form, name, msg)
        return render_template_string(templ, name='Quiz Alpha', form=form)

    return render_template_string(templ, name='Quiz Alpha', form=form)

