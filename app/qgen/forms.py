from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired
from app.user.models import User

#form for virtual problem creation page
class VProbAdd(FlaskForm):
    rawprob = StringField('Raw Problem', validators=[DataRequired()])
    rawansr = StringField('Raw Answer', validators=[DataRequired()])
    example = StringField('Example')
    image = StringField('Image')
    title = StringField('Problem Title')
    formelem = SelectField('Form Element', choices=[('text','Text'), ('selmul', 'Select Multiple'), ('selone', 'Select One')], validators=[DataRequired()])
    calculator_ok = BooleanField('Calculator OK')
    submit = SubmitField('Submit')

#form for virtual quiz creation page
class VQuizAdd(FlaskForm):
    #user = SelectField('Assign CQuiz to User')
    #vquiz = SelectField('using VQuiz')
    vplist = StringField('VProblem List', validators=[DataRequired()])
    title = StringField('Quiz Title', validators=[DataRequired()])
    image = StringField('Image')
    calculator_ok = BooleanField('Calculator OK')
    submit = SubmitField('Submit')

class VQuizAssign(FlaskForm):
    submit = SubmitField('Submit')
    user = SelectField('Assign CQuiz to User')
    vquiz = SelectField('UsingVQuiz')
