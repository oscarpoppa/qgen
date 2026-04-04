from flask_wtf import FlaskForm
import wtforms as wtf
from flask import flash

## Answer-Checking Validators ##

# checks answer for select-one field
# assume answer is int & field.data is int
def check_selone_ans(form, field):
    if form.answer == field.data:
        form.is_correct = True
    else:
        form.is_correct = False

# checks answer for select-many field
# requires answer field--[int,...]--present in form
# assume answer is [int,...] & field.data is [int,...]
def check_selmult_ans(form, field):
    cor_lst = sorted([a for a in form.answer])
    ans_lst = sorted([a for a in field.data])
    if cor_lst == ans_lst:
        form.is_correct = True
    else:
        form.is_correct = False


## Select-From-List Forms ##

# Base of select forms
class QASelBase(FlaskForm):
    question = None
    answer = None
    is_correct = False
    submit = wtf.SubmitField('Submit')

# QA form with select multiple 
class SelMultStatic(QASelBase):
    selfield = wtf.SelectMultipleField(coerce=int, validators=[check_selmult_ans])

# QA form with select one 
class SelOneStatic(QASelBase):
    selfield = wtf.SelectField(coerce=int, validators=[check_selone_ans])

