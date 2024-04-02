from flask_wtf import FlaskForm
from wtforms import SubmitField, FileField
from wtforms.validators import DataRequired, ValidationError


class UploadForm(FlaskForm):
    thefile = FileField('Select File', validators=[DataRequired()])
    submit = SubmitField('Submit')

