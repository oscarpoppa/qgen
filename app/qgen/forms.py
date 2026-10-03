from flask_wtf import FlaskForm
from wtforms import (Form, StringField, BooleanField, SubmitField, SelectField, TextAreaField,
                     IntegerField, FieldList, FormField, HiddenField, SelectMultipleField, DateTimeLocalField)
from wtforms.validators import DataRequired, Optional, NumberRange, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput

from .friendly import KINDS
from .qtypes import REGISTRY, PRECISIONS
from .models import RETAKE_RULES


#one row of the values table (not a FlaskForm: the page form carries the CSRF token)
class ValueRow(Form):
    name = StringField('Name')
    kind = SelectField('Kind', choices=[('', 'Choose…')] + list(KINDS.items()))
    min = StringField('From')
    max = StringField('To')
    step = StringField('In steps of')
    places = StringField('Decimal places')
    nonzero = BooleanField('Not zero')
    items = StringField('List (comma separated)')
    pick_n = StringField('How many to pick')
    formula = StringField('Formula')
    im_min = StringField('Imaginary part from')
    im_max = StringField('Imaginary part to')
    different_from = StringField('Different from')


#one picture; with several, each student gets one at random
class ImageRow(Form):
    file = StringField('Picture')
    label = StringField('Label')


#form for creating and editing a problem
class ProblemForm(FlaskForm):
    qtype = SelectField('Question type', choices=[(t.key, t.label) for t in REGISTRY.values()])
    title = StringField('Title', validators=[DataRequired(message='Please give the problem a short title.')])
    question = TextAreaField('Question')
    values = FieldList(FormField(ValueRow), min_entries=0)
    answer = TextAreaField('Answer')
    choices = TextAreaField('Choices (one per line, put * in front of correct ones)')
    combos = TextAreaField('Other correct combinations (optional)')
    shuffle = BooleanField('Shuffle the choices for each student', default=True)
    show_n = IntegerField('Show only this many choices', validators=[Optional(), NumberRange(min=2, max=50)])
    case_sensitive = BooleanField('Case sensitive (capital letters must match)')
    precision = SelectField('How close must the answer be?', choices=list(PRECISIONS.items()), default='close')
    ordered = BooleanField('Order matters (like a point (x, y))')
    answer_display = StringField('Show the correct answer as (optional)')
    complex = BooleanField('Use complex numbers (i = √−1)')
    grading_notes = TextAreaField('Grading notes (only you see these)')
    images = FieldList(FormField(ImageRow), min_entries=0)
    calculator_ok = BooleanField('Calculator allowed')
    submit = SubmitField('Save problem')

    def options(self):
        """The problem's settings as stored in VProblem.options."""
        values = []
        for row in self.values.data:
            if not any(str(v).strip() for k, v in row.items() if k != 'nonzero' and v is not None) and not row.get('nonzero'):
                continue  # untouched blank row
            val = {'name': (row['name'] or '').strip(), 'kind': row['kind']}
            for key in ('min', 'max', 'step', 'places', 'items', 'pick_n', 'formula', 'im_min', 'im_max'):
                if (row.get(key) or '').strip():
                    val[key] = row[key].strip()
            if row.get('nonzero'):
                val['nonzero'] = True
            diff = [d.strip() for d in (row.get('different_from') or '').split(',') if d.strip()]
            if diff:
                val['different_from'] = diff
            values.append(val)
        images = [{'file': r['file'].strip(), 'label': (r.get('label') or '').strip()}
                  for r in self.images.data if (r.get('file') or '').strip()]
        return {
            'markup': 'friendly',
            'values': values,
            'choices': self.choices.data or '',
            'combos': self.combos.data or '',
            'shuffle': bool(self.shuffle.data),
            'show_n': self.show_n.data,
            'case_sensitive': bool(self.case_sensitive.data),
            'precision': self.precision.data or 'close',
            'ordered': bool(self.ordered.data),
            'answer_display': (self.answer_display.data or '').strip(),
            'complex': bool(self.complex.data),
            'grading_notes': self.grading_notes.data or '',
            'images': images,
        }

    def load(self, vp):
        """Fill the form from a saved problem."""
        opts = vp.options
        self.qtype.data = vp.qtype
        self.title.data = vp.title
        self.question.data = vp.raw_prob
        self.answer.data = vp.raw_ansr
        self.choices.data = opts.get('choices', '')
        self.combos.data = opts.get('combos', '')
        self.shuffle.data = opts.get('shuffle', True)
        self.show_n.data = opts.get('show_n')
        self.case_sensitive.data = opts.get('case_sensitive', False)
        self.precision.data = opts.get('precision', 'close')
        self.ordered.data = opts.get('ordered', False)
        self.answer_display.data = opts.get('answer_display', '')
        self.complex.data = opts.get('complex', False)
        self.grading_notes.data = opts.get('grading_notes', '')
        self.calculator_ok.data = vp.calculator_ok
        for val in opts.get('values', []):
            row = dict(val)
            row['different_from'] = ', '.join(val.get('different_from', []))
            row['nonzero'] = bool(val.get('nonzero'))
            self.values.append_entry({k: row.get(k) for k in ValueRow().data})
        images = opts.get('images') or ([{'file': vp.image, 'label': ''}] if vp.image else [])
        for img in images:
            self.images.append_entry(img)


class CheckboxList(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


#form for creating and editing a quiz; problems are ticked on the page and their
#order kept in vplist ("4, 7, 5")
class QuizForm(FlaskForm):
    title = StringField('Quiz title', validators=[DataRequired(message='Please give the quiz a title.')])
    vplist = HiddenField('Problems')
    image = StringField('Picture shown at the top (optional)')
    calculator_ok = BooleanField('Calculator allowed')
    shuffle_order = BooleanField('Give each student the questions in a different order', default=True)
    retake_rule = SelectField('If a student takes this quiz more than once, the score is', choices=list(RETAKE_RULES.items()), default='best')
    hide_answers = BooleanField('Hide the correct answers until I release them')
    submit = SubmitField('Save quiz')


#form for assigning a quiz to one or more students
class AssignForm(FlaskForm):
    vquiz = SelectField('Quiz', coerce=int)
    users = CheckboxList('Students', coerce=int, validators=[DataRequired(message='Check at least one student.')])
    opens_at = DateTimeLocalField('Opens', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    closes_at = DateTimeLocalField('Closes', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    time_limit = IntegerField('Time limit (minutes)', validators=[Optional(), NumberRange(min=1, max=600, message='Between 1 and 600 minutes.')])
    submit = SubmitField('Assign')

    def validate_closes_at(self, field):
        if field.data and self.opens_at.data and field.data <= self.opens_at.data:
            raise ValidationError('The closing time must be after the opening time.')

    def validate_time_limit(self, field):
        from .services import time_limit_error
        message = time_limit_error(self.opens_at.data, self.closes_at.data, field.data)
        if message:
            raise ValidationError(message)


#instructor grading of one essay answer
class ReviewItem(Form):
    cpid = HiddenField()
    credit = IntegerField('Credit (%)', validators=[Optional(), NumberRange(min=0, max=100, message='Credit must be 0 to 100.')])
    feedback = TextAreaField('Comment for the student')
    highlights = HiddenField()


class ReviewForm(FlaskForm):
    items = FieldList(FormField(ReviewItem), min_entries=0)
    save = SubmitField('Save draft')
    finalize = SubmitField('Finish grading')
