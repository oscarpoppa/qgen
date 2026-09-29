from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo, StopValidation
from .models import User


#email is optional: blank or "none" means no email
def clean_email(value):
    value = (value or '').strip()
    return None if value.lower() in ('', 'none') else value


def email_optional(form, field):
    if clean_email(field.data) is None:
        field.errors[:] = []
        raise StopValidation()


class ChPassForm(FlaskForm):
    old_password = PasswordField('Old Password', validators=[DataRequired()])
    password = PasswordField('New Password', validators=[DataRequired()])
    retype_password = PasswordField('Re-type New Password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email (optional)', validators=[email_optional, Email(message='That doesn\'t look like an email address.')])
    password = PasswordField('Password', validators=[DataRequired()])
    retype_password = PasswordField('Re-type Password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Username {} already taken'.format(username.data))

    def validate_email(self, email):
        if clean_email(email.data) is None:
            return
        user = User.query.filter_by(email=clean_email(email.data)).first()
        if user is not None:
            raise ValidationError('Email address {} already taken'.format(email.data))


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Submit')

