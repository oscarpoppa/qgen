from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo
from app.models import User


class ChPassForm(FlaskForm):
    old_password = PasswordField('Old Password', validators=[DataRequired()])
    password = PasswordField('New Password', validators=[DataRequired()])
    retype_password = PasswordField('Re-type New Password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email(message='Bad email address')])
    password = PasswordField('Password', validators=[DataRequired()])
    retype_password = PasswordField('Re-type Password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Username {} already taken'.format(username.data))

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Email address {} already taken'.format(email.data))


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Submit')


class UploadForm(FlaskForm):
    thefile = FileField('Select File', validators=[DataRequired()])
    submit = SubmitField('Submit')


class GameForm(FlaskForm):
    name = StringField('Game Name', validators=[DataRequired()])

