from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo, StopValidation

#the shortest password allowed is a Technical setting (app/tuning.py); read when checking
def min_password():
    from app import tuning
    return tuning.get('min_password')


def long_enough(form, field):
    if len(field.data or '') < min_password():
        raise ValidationError('Please use at least {} characters.'.format(min_password()))
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
    old_password = PasswordField('Old password', validators=[DataRequired()])
    password = PasswordField('New password', validators=[DataRequired(), long_enough])
    retype_password = PasswordField('Re-type new password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')


class RegistrationForm(FlaskForm):
    class_code = StringField('Class code', validators=[DataRequired(message='Ask your teacher for the class code.')])
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email (optional)', validators=[email_optional, Email(message='That doesn\'t look like an email address.')])
    password = PasswordField('Password', validators=[DataRequired(), long_enough])
    retype_password = PasswordField('Re-type password', validators=[DataRequired(), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')

    def validate_class_code(self, field):
        from app.qgen.models import Setting
        code = Setting.get('class_code')
        if not code or field.data.strip().lower() != code.strip().lower():
            raise ValidationError('That class code isn\'t right. Ask your teacher for it.')

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



#admin: site-wide settings
class SettingsForm(FlaskForm):
    site_name = StringField('Site name', validators=[DataRequired(message='Please give the site a name.')])
    logo = StringField('Logo')
    favicon = StringField('Browser tab icon')
    code = StringField('Class code for sign-up')
    submit = SubmitField('Save settings')
