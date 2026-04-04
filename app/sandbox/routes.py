from . import sandbox_bp
from flask import flash, render_template, redirect, request 
from .form_factory import true_false_static_form_factory, select_multiple_static_form_factory, select_one_static_form_factory, TRUE, FALSE, parse_spec_to_qa


@sandbox_bp.route('/sandbox/selone', methods=['GET', 'POST'])
def selone():
    #will come from db eventually
    form = select_one_static_form_factory('which one was a president', ['Sandusky', 'Washington', 'Bob', 'Eisendrath', 'Xanos'], 1)
    if form.validate_on_submit():
        flash('Correct' if form.is_correct else 'Wrong!')
    return render_template('sandtmpl.html', form=form)

@sandbox_bp.route('/sandbox/selmany', methods=['GET', 'POST'])
def selmany():
    #will come from db eventually
    form = select_multiple_static_form_factory('pick out the presidents', ['Washington', 'Bob', 'Lincoln', 'Xanos'], [0,2])
    if form.validate_on_submit():
        flash('Correct' if form.is_correct else 'Wrong!')
    return render_template('sandtmpl.html', form=form)

@sandbox_bp.route('/sandbox/truefalse', methods=['GET', 'POST'])
def truefalse():
    #will come from db eventually
    form = true_false_static_form_factory('True or False: The sky is blue', answer_idx=TRUE)
    if form.validate_on_submit():
        flash('Correct' if form.is_correct else 'Wrong!')
    return render_template('sandtmpl.html', form=form)

@sandbox_bp.route('/sandbox/tfvar', methods=['GET', 'POST'])
def tfvar():
    #will come from db eventually
        # regenerates each call--need workaround for repeatability
        indct = {'a': ['Carl', 'Gordy', 'Al', 'Curt', 'Dave', 'Bob', 'Paulie'], 'h': ['57', '33', '28'], 'l': ['15', '7', '6']}
        qstr = "True or False: If {{a[0]}} has ${{h[0]}} and {{a[1]}} has ${{l[0]}}, {{a[1]}} has more money"
        quest, _, __ = parse_spec_to_qa(qstr, indct, [])
        form = true_false_static_form_factory(quest, answer_idx=FALSE)
        if form.validate_on_submit():
            flash('Correct' if form.is_correct else 'Wrong!')
    return render_template('sandtmpl.html', form=form)
