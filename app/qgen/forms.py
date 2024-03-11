from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField, BooleanField
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo
from app.models import User

class VProbAdd(FlaskForm):
    rawprob = StringField('Raw Problem', validators=[DataRequired()])
    rawansr = StringField('Raw Answer', validators=[DataRequired()])
    example = StringField('Example')
    image = StringField('Image')
    title = StringField('Problem Title')
    formelem = StringField('Form Element', validators=[DataRequired()])
    calculator_ok = BooleanField('Calculator OK')
    submit = SubmitField('Submit')


class VQuizAdd(FlaskForm):
    vplist = StringField('VProblem List', validators=[DataRequired()])
    title = StringField('Quiz Title', validators=[DataRequired()])
    image = StringField('Image')
    calculator_ok = BooleanField('Calculator OK')
    submit = SubmitField('Submit')

