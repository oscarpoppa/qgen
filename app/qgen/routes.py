#!/usr/bin/env python
from app.qgen import qgen_bp
from app.routes import admin_only
from random import randint
from re import sub, search, split
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem
from json import dumps, loads
from flask import flash, render_template, render_template_string, redirect, url_for, request
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField
from flask_login import current_user, login_user, login_required, logout_user

block_top = """
{% extends "base.html" %}

{% block content %}
"""

form_top = """
    <form action="" method="post">
        {{ form.hidden_tag() }}
"""

form_bottom = """
        {{ form.submit() }}
    </form>
"""

block_bottom = """
{% endblock %}
"""

block_header = """
<b>{{ title }}</b><br><br>
"""

prob_capsule = """
    {}. {}<br>{}<br><br>
"""

fieldname_base = 'Number{}'

class OTF(FlaskForm):
    @property
    def result_template(self):
        prob_chunks = [block_header]
        num_correct = 0
        for idx in range(1, int(self.count)+1):
            field_name = fieldname_base.format(idx)
            submitted_ansr = getattr(self, field_name).data or 'None'
            correct_ansr = getattr(self, field_name+'_ansr')
            problem = getattr(self, field_name+'_prob')
            right_or_wrong = 'W'
            try:
                if submitted_ansr != 'None' and abs(float(submitted_ansr) - float(correct_ansr)) < 0.1:
                    num_correct += 1
                    right_or_wrong = 'R'
            except:
                pass
            summary = '({}) Your answer: {} : Correct answer: {}'.format(right_or_wrong, submitted_ansr, correct_ansr)
            prob_chunks += prob_capsule.format(idx, problem, summary)
        prob_chunks += '<br>Score: {}%'.format(100*num_correct/self.count)
        prob_section = ''.join(prob_chunks)
        return block_top+prob_section+block_bottom


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

    def gen_conc_to_db(self, ordinal):
        ct = self.gen_conc_text() 
        ca = self.gen_conc_ansr() 
        nuconc = CProblem(ordinal=ordinal, cquiz_id=self.cq.id, conc_prob=ct, conc_answer=ca, vproblem_id=self.vp.id, requestor=1)
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
    ordered_vids = loads(vquiz.vpid_lst)
    vprobs = [(o, VProblem.query.filter_by(id=vid).first()) for o, vid in enumerate(ordered_vids, 1)]
    probs = [V2CProb(vp, nuquiz).gen_conc_to_db(o) for o,vp in vprobs]
    nuquiz.cproblems.extend(probs)
    nuquiz.save()
    return nuquiz

def create_renderables(cquiz):
    ftypes = {'text':StringField, 'txt':StringField, 'string':StringField}
    ttlst = [block_header]
    phash = {p.ordinal:p for p in cquiz.cproblems}
    skeys = sorted(phash.keys())
    for ordinal in skeys:
        problem = phash[ordinal]
        field_name = fieldname_base.format(ordinal)
        inpstr = '{{ '+'form.{}'.format(field_name)+' }}'
        ttlst += prob_capsule.format(ordinal, problem.conc_prob, inpstr)
        ftype = ftypes[problem.vproblem.form_elem]
        setattr(OTF, field_name, ftype(field_name)) 
        setattr(OTF, field_name+'_ansr', problem.conc_answer) 
        setattr(OTF, field_name+'_prob', problem.conc_prob) 
    setattr(OTF, 'submit', SubmitField('Submit'))
    setattr(OTF, 'count', len(cquiz.cproblems))
    ttext = ''.join(ttlst)
    templ = block_top+form_top+ttext+form_bottom+block_bottom
    return templ, OTF

@qgen_bp.route('/quiz/take/<cidx>', methods=['GET','POST'])
@login_required
def qtake(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first_or_404()
    templ, cform = create_renderables(cq)
    form = cform()
    title = 'Quiz {}'.format(cidx)
    if form.validate_on_submit():
        return render_template_string(form.result_template, title=title)
    return render_template_string(templ, title=title, form=form)

@qgen_bp.route('/quiz/take/new/<vidx>', methods=['GET','POST'])
@login_required
def make_take(vidx):
    vq = VQuiz.query.filter_by(id=vidx).first_or_404()
    cq = create_cquiz(vq) 
    return redirect(url_for('qgen.qtake', cidx=cq.id))

@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@admin_only
def list_vquizzes():
    vqlst = VQuiz.query.all()
    return render_template('vqlist.html', vqlst=vqlst)

@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first_or_404()
    return render_template('vqlist.html', vqlst=[vqlst])

@qgen_bp.route('/quiz/listcq/<cqid>', methods=['GET'])
@login_required
@admin_only
def list_cquiz(cqid):
    cqlst = CQuiz.query.filter_by(id=cqid).first_or_404()
    return render_template('cqlist.html', cqlst=[cqlst])

@qgen_bp.route('/quiz/listvp', methods=['GET'])
@login_required
@admin_only
def list_vprobs():
    vplst = VProblem.query.all()
    return render_template('vplist.html', vplst=vplst)

@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@admin_only
def list_vprob(vpid):
    vplst = VProblem.query.filter_by(id=vpid).first_or_404()
    return render_template('vplist.html', vplst=[vplst])

