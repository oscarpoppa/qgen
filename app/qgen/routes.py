#!/usr/bin/env python
from app import db
from app.qgen import qgen_bp
from app.routes import admin_only
from random import randint
from re import sub, search, split, findall
from app.models import User
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem
from json import dumps, loads
from flask import flash, render_template, render_template_string, redirect, url_for, request
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, PasswordField, BooleanField, SubmitField, FileField
from flask_login import current_user, login_user, login_required, logout_user
from app.qgen.forms import VProbAdd, VQuizAdd
from datetime import datetime
from wtforms_sqlalchemy.orm import model_form


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
<b>{{ title }}<br><br></b>
"""

prob_capsule = """
    {}. {} {}<br>{}<br><br>
"""

fieldname_base = 'Number{}'

class V2CProb:
    funcs = {'randint':randint, 'ri':randint}
    mainpatt = r'{{([^}{]*)}}'

    def __init__(self, vp, cq):
        self.vp = vp
        self.cq = cq 
        self.raw_text = vp.raw_prob
        self.conc_text = ''
        self.raw_ansr = vp.raw_ansr
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
        return chunk.group(0)
    
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
        nuconc = CProblem(ordinal=ordinal, cquiz_id=self.cq.id, conc_prob=ct, conc_ansr=ca, vproblem_id=self.vp.id)
        nuconc.save()
        return nuconc

def create_vquiz(lst, title, img):
    nuquiz = VQuiz(image=img, title=title, vpid_lst=dumps(lst), author_id=current_user.id)
    nuquiz.save()
    probs = [VProblem.query.filter_by(id=a).first_or_404('No vproblem with id {}'.format(a)) for a in set(lst)]
    nuquiz.vproblems.extend(probs)
    nuquiz.save()
    return nuquiz

@qgen_bp.route('/quiz/makevquiz', methods=['POST', 'GET'])
@login_required
@admin_only
def mkvquiz():
    form = VQuizAdd()
    if form.validate_on_submit():
        lstr = form.vplist.data
        numlist = [int(a) for a in findall('(\d+)', lstr)]
        title = form.title.data
        image = form.image.data
        nq = create_vquiz(numlist, title, image)
        flash('Created vquiz: ({}) {}'.format(nq.id, title))
        return redirect(url_for('qgen.mkvquiz'))
    return render_template('vqadd.html', title='Create VQuiz', form=form)

@qgen_bp.route('/quiz/makevprob', methods=['POST', 'GET'])
@login_required
@admin_only
def mkvprob():
    form = VProbAdd()
    if form.validate_on_submit():
        nuprob = VProblem(image=form.image.data, raw_prob=form.rawprob.data, raw_ansr=form.rawansr.data, example=form.example.data, form_elem=form.formelem.data, author_id=current_user.id, title=form.title.data, calculator_ok=form.calculator_ok.data)
        nuprob.save()
        flash('Created vproblem: ({} "{}" ({})) {}'.format(nuprob.id, nuprob.title, 'calc OK' if nuprob.calculator_ok else 'no calc', nuprob.raw_prob))
        return redirect(url_for('qgen.mkvprob'))
    return render_template('vpadd.html', title='Create VProblem', form=form)

def assign_form_factory():

    class A(FlaskForm):
        submit = SubmitField('Submit')

    users = User.query.all()
    vquizzes = VQuiz.query.all()
    setattr(A,'user', SelectField('Assign CQuiz to User', choices=[(a.id, a.username) for a in users]))
    setattr(A,'vquiz', SelectField('Using VQuiz', choices=[(a.id, a.title) for a in vquizzes]))
    return A

@qgen_bp.route('/quiz/assign', methods=['POST', 'GET'])
@login_required
@admin_only
def assign():
    fcls = assign_form_factory()
    form = fcls()
    if form.validate_on_submit():
        vquiz = VQuiz.query.filter_by(id=int(form.vquiz.data)).first()
        user = User.query.filter_by(id=int(form.user.data)).first()
        cq = create_cquiz(vquiz, user) 
        flash('Created quiz: "{}" ({}) for {}'.format(vquiz.title, cq.id, user.username))
        return redirect(url_for('qgen.assign'))
    return render_template('assign.html', title='Assign Quiz', form=form)

def create_cquiz(vquiz, assignee):
    nuquiz = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id)
    nuquiz.save()
    ordered_vids = loads(vquiz.vpid_lst)
    vprobs = [(o, VProblem.query.filter_by(id=vid).first()) for o, vid in enumerate(ordered_vids, 1)]
    probs = [V2CProb(vp, nuquiz).gen_conc_to_db(o) for o,vp in vprobs]
    nuquiz.cproblems.extend(probs)
    nuquiz.save()
    return nuquiz

def renderable_factory(cquiz):
    ftypes = {'text':StringField, 'txt':StringField, 'string':StringField}
    ttlst = [block_header]
    phash = {p.ordinal:p for p in cquiz.cproblems}
    skeys = sorted(phash.keys())
    imgtmpl = '<br><img src="/static/{}" style="width:35%"/><br><br>'

    class OTF(FlaskForm):
        submit = SubmitField('Submit')

        @property
        def result_template(self): # AKA transcript
            date_header = '<b>Started:</b> {}<br><b>Completed:</b> {}<br>'.format(cquiz.startdate, cquiz.compdate)
            head_chunks = [block_header, date_header]
            prob_chunks = []
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
                pimg = phash[idx].vproblem.image
                if pimg:
                    img = imgtmpl.format(pimg)
                else:
                    img = ''
                prob_chunks += prob_capsule.format(idx, img, problem, summary)
            pimg = cquiz.vquiz.image
            if pimg:
                img = imgtmpl.format(pimg)
            else:
                img = ''
            self.score = 100*num_correct/self.count
            head_chunks += '<br><b>Score:</b> {}%<br><br>'.format(100*num_correct/self.count)
            all_chunks = head_chunks + prob_chunks
            #add to object
            prob_section = ''.join(all_chunks)
            return block_top+img+prob_section+block_bottom

    for ordinal in skeys:
        problem = phash[ordinal]
        field_name = fieldname_base.format(ordinal)
        inpstr = '{{ '+'form.{}'.format(field_name)+' }}'
        pimg = problem.vproblem.image
        if pimg:
            img = imgtmpl.format(pimg)
        else:
            img = ''
        ttlst += prob_capsule.format(ordinal, img, problem.conc_prob, inpstr)
        ftype = ftypes[problem.vproblem.form_elem]
        setattr(OTF, field_name, ftype(field_name)) 
        setattr(OTF, field_name+'_ansr', problem.conc_ansr) 
        setattr(OTF, field_name+'_prob', problem.conc_prob) 
    setattr(OTF, 'count', len(cquiz.cproblems))
    ttext = ''.join(ttlst)
    pimg = cquiz.vquiz.image
    if pimg:
        img = imgtmpl.format(pimg)
    else:
        img = ''
    templ = block_top+img+form_top+ttext+form_bottom+block_bottom
    return templ, OTF

@qgen_bp.route('/quiz/take/<cidx>', methods=['GET','POST'])
@login_required
def qtake(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first_or_404('No cquiz with id {}'.format(cidx))
    title = '{} ({})'.format(cq.vquiz.title, cq.taker.username)
    if not cq.taker:
        flash('{} unassigned'.format(request.__dict__['environ']['RAW_URI']))
        return redirect(url_for('mypage'))
    if current_user != cq.taker and not current_user.is_admin:
        flash('{} unauthorized'.format(request.__dict__['environ']['RAW_URI']))
        return redirect(url_for('mypage'))
    if cq.completed:
        return render_template_string(cq.transcript, title=title)
    templ, cform = renderable_factory(cq)
    form = cform()
    if current_user == cq.taker:
        if form.validate_on_submit():
            cq.compdate = datetime.now()
            cq.save()
            cq.transcript = form.result_template
            cq.completed = True
            cq.score = form.score
            cq.save()
            return render_template_string(form.result_template, title=title)
        if not cq.startdate:
            cq.startdate = datetime.now()
            cq.save()
    return render_template_string(templ, title=title, form=form)

@qgen_bp.route('/quiz/listuser', methods=['GET'])
@login_required
@admin_only
def list_users():
    ulst = User.query.all()
    return render_template('ulist.html', ulst=ulst, title='User Info')

@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    return render_template('ulist.html', ulst=[ulst], title="{}'s Info".format(ulst.username))

@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@admin_only
def list_vquizzes():
    vqlst = VQuiz.query.all()
    return render_template('vqlist.html', vqlst=vqlst, title='All VQuizzes')

@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first_or_404('No vquiz with id {}'.format(vqid))
    return render_template('vqlist.html', vqlst=[vqlst], title='VQuiz {} detail'.format(vqid))

@qgen_bp.route('/quiz/listcq/<cqid>', methods=['GET'])
@login_required
@admin_only
def list_cquiz(cqid):
    cqlst = CQuiz.query.filter_by(id=cqid).first_or_404('No cquiz with id {}'.format(cqid))
    return render_template('cqlist.html', cqlst=[cqlst], title='CQuiz {} detail'.format(cqid))

@qgen_bp.route('/quiz/listvp', methods=['GET'])
@login_required
@admin_only
def list_vprobs():
    vplst = VProblem.query.all()
    return render_template('vplist.html', vplst=vplst, title='All VProblems')

@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@admin_only
def list_vprob(vpid):
    vplst = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    return render_template('vplist.html', vplst=[vplst], title='VProblem {} detail'.format(vpid))

@qgen_bp.route('/quiz/editvprob/<vpid>', methods=['POST', 'GET'])
@login_required
@admin_only
def edvprob(vpid):
    vpform = model_form(VProblem, base_class=FlaskForm, db_session=db)
    vpobj = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    form = vpform(obj=vpobj)
    if request.method == 'POST':
        vpobj.image = form.image.data
        vpobj.raw_prob = form.raw_prob.data
        vpobj.raw_ansr = form.raw_ansr.data
        vpobj.form_elem = form.form_elem.data
        vpobj.title = form.title.data
        vpobj.example = form.example.data
        vpobj.calculator_ok = form.calculator_ok.data
        vpobj.save()
        flash('Updated vproblem: ({} "{}") {}'.format(vpobj.id, vpobj.title, vpobj.raw_prob))
        return redirect(url_for('qgen.list_vprobs'))
    return render_template('vped.html', title='Update VProblem', form=form)


@qgen_bp.route('/quiz/editvquiz/<vqid>', methods=['POST', 'GET'])
@login_required
@admin_only
def edvquiz(vqid):
    vqform = model_form(VQuiz, base_class=FlaskForm, db_session=db)
    vqobj = VQuiz.query.filter_by(id=vqid).first_or_404('No vquiz with id {}'.format(vqid))
    form = vqform(obj=vqobj)
    if request.method == 'POST':
        vqobj.image = form.image.data
        vqobj.title = form.title.data
        numlist = [int(a) for a in findall('(\d+)', form.vpid_lst.data)]
        #this way to check for 404
        plist = [VProblem.query.filter_by(id=a).first_or_404('No vproblem with id {}'.format(a)) for a in set(numlist)]
        vqobj.vpid_lst = dumps(numlist)
        vqobj.vproblems = plist
        vqobj.save()
        flash('Updated vquiz: ({} "{}") {}'.format(vqobj.id, vqobj.title, vqobj.vpid_lst))
        return redirect(url_for('qgen.list_vquizzes'))
    return render_template('vqed.html', title='Update VQuiz', form=form)


@qgen_bp.route('/quiz/delcq/<cqid>', methods=['GET'])
@login_required
@admin_only
def del_cquiz(cqid):
    cqquery = CQuiz.query.filter_by(id=cqid)
    cq = cqquery.first_or_404('No cquiz with id {}'.format(cqid))
    title = cq.vquiz.title
    owner = cq.taker.username
    cqquery.delete()
    db.session.commit()
    flash("Deleted {}'s cquiz:({}) '{}'".format(owner, cqid, title))
    return redirect(url_for('qgen.list_users'))

