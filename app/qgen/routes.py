from app import db
from app.models import User
from app.routes import admin_only, pw_check
from app.qgen import qgen_bp
from app.qgen.probspec import process_spec
from app.qgen.formfact import renderable_factory, assign_form_factory
from app.qgen.forms import VProbAdd, VQuizAdd
from app.qgen.models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup
from flask import flash, render_template, render_template_string, redirect, url_for, request, current_app
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, PasswordField, BooleanField, SubmitField, FileField
from wtforms_sqlalchemy.orm import model_form
from random import randint
from re import sub, search, split, findall
from json import dumps, loads
from datetime import datetime

def gen_cprob(cquiz, vprob, ordinal):
    cp, ca = process_spec(vprob.raw_prob, vprob.raw_ansr)
    nucprob = CProblem(ordinal=ordinal, cquiz_id=cquiz.id, conc_prob=cp, conc_ansr=ca, vproblem_id=vprob.id)
    return nucprob

def create_vquiz(lst, title, img, calculator_ok):
    nuquiz = VQuiz(image=img, title=title, vpid_lst=dumps(lst), author_id=current_user.id, calculator_ok=calculator_ok)
    nuquiz.save()
    probs = [VProblem.query.filter_by(id=a).first_or_404('No vproblem with id {}'.format(a)) for a in set(lst)]
    nuquiz.vproblems.extend(probs)
    nuquiz.vqgroups.append(VQGroup.query.filter_by(title='Archive').first())
    nuquiz.save()
    return nuquiz

def create_cquiz(vquiz, assignee):
    try:
        nuquiz = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id)
        ordered_vids = loads(vquiz.vpid_lst)
        vprobs = [(o, VProblem.query.filter_by(id=vid).first()) for o, vid in enumerate(ordered_vids, 1)]
        probs = [gen_cprob(nuquiz, vp, o) for o,vp in vprobs]
        nuquiz.cproblems.extend(probs)
        nuquiz.save()
        return nuquiz
    except Exception as exc:
        current_app.logger.error(str(exc))
        flash(str(exc))
        db.session.rollback()
        return None

@qgen_bp.route('/quiz/makevquiz', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvquiz():
    form = VQuizAdd()
    if form.validate_on_submit():
        lstr = form.vplist.data
        numlist = [int(a) for a in findall('(\d+)', lstr)]
        title = form.title.data
        image = form.image.data
        calculator_ok = form.calculator_ok.data
        nq = create_vquiz(numlist, title, image, calculator_ok)
        flash('Created VQuiz: ({}) {}'.format(nq.id, title))
        return redirect(url_for('qgen.mkvquiz'))
    return render_template('vqadd.html', title='Create VQuiz', form=form)

@qgen_bp.route('/quiz/makevprob', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvprob():
    form = VProbAdd()
    if form.validate_on_submit():
        nuprob = VProblem(image=form.image.data, raw_prob=form.rawprob.data, raw_ansr=form.rawansr.data, example=form.example.data, form_elem=form.formelem.data, author_id=current_user.id, title=form.title.data, calculator_ok=form.calculator_ok.data)
        nuprob.vpgroups.append(VPGroup.query.filter_by(title='Archive').first())
        nuprob.save()
        flash('Created vproblem: ({} "{}" ({})) {}'.format(nuprob.id, nuprob.title, 'calc OK' if nuprob.calculator_ok else 'no calc', nuprob.raw_prob))
        return redirect(url_for('qgen.mkvprob'))
    return render_template('vpadd.html', title='Create VProblem', form=form)

@qgen_bp.route('/quiz/assign', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def assign():
    fcls = assign_form_factory()
    form = fcls()
    if form.validate_on_submit():
        vquiz = VQuiz.query.filter_by(id=int(form.vquiz.data)).first()
        user = User.query.filter_by(id=int(form.user.data)).first()
        cq = create_cquiz(vquiz, user) 
        if cq:
            flash('Assigned quiz: "{}" ({}) to {}'.format(vquiz.title, cq.id, user.username))
            current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vquiz.title, cq.id, user.username))
        else:
            estr = 'Failed to create quiz: "{}" for {}'.format(vquiz.title, user.username)
            flash(estr)
            current_app.logger.error(estr)
        return redirect(url_for('qgen.assign'))
    return render_template('assign.html', title='Assign Quiz', form=form)

@qgen_bp.route('/quiz/take/<cidx>', methods=['GET','POST'])
@login_required
@pw_check
def qtake(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first_or_404('No CQuiz with id {}'.format(cidx))
    cok = cq.vquiz.calculator_ok
    title = '{} ({}) ({})'.format(cq.vquiz.title, cq.taker.username, 'Calculator OK' if cok else 'No Calculator')
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
            current_app.logger.info('{} completed "{}"'.format(current_user.username, cq.vquiz.title))
            cq.save()
            cq.transcript = form.transcript
            cq.completed = True
            cq.score = form.score
            cq.save()
            return render_template_string(form.transcript, title=title)
        if not cq.startdate:
            cq.startdate = datetime.now()
            current_app.logger.info('{} is starting "{}"'.format(current_user.username, cq.vquiz.title))
            cq.save()
    elif request.method == 'POST':
        flash("you're not {}".format(cq.taker.username))
    return render_template_string(templ, title=title, form=form)

@qgen_bp.route('/quiz/listuser', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_users():
    ulst = User.query.all()
    return render_template('ulist.html', ulst=ulst, title='Quizzes by User')

@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    return render_template('ulist.html', ulst=[ulst], title="{}'s Info".format(ulst.username))

@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquizzes():
    vqlst = VQuiz.query.all()
    return render_template('vqlist.html', vqlst=vqlst, title='All VQuizzes')

@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    return render_template('vqlist.html', vqlst=[vqlst], title='VQuiz {} detail'.format(vqid))

@qgen_bp.route('/quiz/listcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_cquiz(cqid):
    cqlst = CQuiz.query.filter_by(id=cqid).first_or_404('No cquiz with id {}'.format(cqid))
    return render_template('cqlist.html', cqlst=[cqlst], title='CQuiz {} detail'.format(cqid))

@qgen_bp.route('/quiz/listvp', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprobs():
    vplst = VProblem.query.all()
    return render_template('vplist.html', vplst=vplst, title='All VProblems')

@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprob(vpid):
    vplst = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    return render_template('vplist.html', vplst=[vplst], title='VProblem {} detail'.format(vpid))

@qgen_bp.route('/quiz/editvprob/<vpid>', methods=['POST', 'GET'])
@login_required
@pw_check
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
@pw_check
@admin_only
def edvquiz(vqid):
    vqform = model_form(VQuiz, base_class=FlaskForm, db_session=db)
    vqobj = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    form = vqform(obj=vqobj)
    if request.method == 'POST':
        vqobj.image = form.image.data
        vqobj.title = form.title.data
        vqobj.calculator_ok = form.calculator_ok.data
        numlist = [int(a) for a in findall('(\d+)', form.vpid_lst.data)]
        #this way to check for 404
        plist = [VProblem.query.filter_by(id=a).first_or_404('No VProblem with id {}'.format(a)) for a in set(numlist)]
        vqobj.vpid_lst = dumps(numlist)
        vqobj.vproblems = plist
        vqobj.save()
        flash('Updated VQuiz: ({} "{}") {}'.format(vqobj.id, vqobj.title, vqobj.vpid_lst))
        return redirect(url_for('qgen.list_vquizzes'))
    return render_template('vqed.html', title='Update VQuiz', form=form)

@qgen_bp.route('/quiz/delcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_cquiz(cqid):
    cqquery = CQuiz.query.filter_by(id=cqid)
    cq = cqquery.first_or_404('No CQuiz with id {}'.format(cqid))
    title = cq.vquiz.title
    owner = cq.taker.username
    cqquery.delete()
    db.session.commit()
    current_app.logger.info("{}'s quiz '{}' deleted by {}".format(owner, title, current_user.username))
    flash("Deleted {}'s CQuiz:({}) '{}'".format(owner, cqid, title))
    return redirect(url_for('qgen.list_users'))

@qgen_bp.route('/quiz/delvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_vquiz(vqid):
    vqquery = VQuiz.query.filter_by(id=vqid)
    vq = vqquery.first_or_404('No VQuiz with id {}'.format(vqid))
    title = vq.title
    cq = vq.cquizzes
    if cq:
        estr = "VQuiz '{}' NOT deleted. Referenced by CQuizzes".format(title)
        current_app.logger.error(estr)
        flash(estr)
        flash('CQuizzes referencing this VProblem: {}'.format(cq))
    else:
        vqquery.delete()
        db.session.commit()
        current_app.logger.info("VQuiz '{}' deleted by {}".format(title, current_user.username))
        flash("Deleted VQuiz:({}) '{}'".format(vqid, title))
    return redirect(url_for('qgen.list_vquizzes'))

@qgen_bp.route('/quiz/delvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_vprob(vpid):
    vpquery = VProblem.query.filter_by(id=vpid)
    vp = vpquery.first_or_404('No VProblem with id {}'.format(vpid))
    title = vp.title
    vq = vp.vquizzes
    if vq:
        estr = "VProblem '{}' NOT deleted. Referenced by VQuizzes".format(title)
        current_app.logger.error(estr)
        flash(estr)
        flash('VQuizzes referencing this VProblem: {}'.format(vq))
    else:
        vpquery.delete()
        db.session.commit()
        current_app.logger.info("VProblem '{}' deleted by {}".format(title, current_user.username))
        flash("Deleted VProblem:({}) '{}'".format(vpid, title))
    return redirect(url_for('qgen.list_vprobs'))

