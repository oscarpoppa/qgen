from . import db
from app.user.models import User
from datetime import datetime
import json

#add save method
class SaveMixin:
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

#add create_date method
class DateMixin:
    create_date = db.Column(db.DateTime, default=db.func.now())


# for many-to-many between vprobs and vquizzes
vproblem_vquiz = db.Table('vproblem_vquiz',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id', ondelete='CASCADE')),
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id', ondelete='CASCADE')))
    
# for many-to-many between vprobs and vpgroups
vproblem_vpgroup = db.Table('vproblem_vpgroup',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id', ondelete='CASCADE')),
    db.Column('vpgroup_id', db.Integer, db.ForeignKey('vpgroup.id', ondelete='CASCADE')))

# for many-to-many between vquizzes and vqgroups
vquiz_vqgroup = db.Table('vquiz_vqgroup',
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id', ondelete='CASCADE')),
    db.Column('vqgroup_id', db.Integer, db.ForeignKey('vqgroup.id', ondelete='CASCADE')))

#for grouping of virtual problems
class VPGroup(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vpgroup'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(64))
    summary = db.Column(db.String(256))

    vproblems = db.relationship('VProblem', back_populates='vpgroups', secondary=vproblem_vpgroup, lazy=True)

    def __repr__(self):
        return '<VProblem Group: {}>'.format(self.title)

#for grouping of virtual quizzes
class VQGroup(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vqgroup'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(64))
    summary = db.Column(db.String(256))

    vquizzes = db.relationship('VQuiz', back_populates='vqgroups', secondary=vquiz_vqgroup, lazy=True)

    def __repr__(self):
        return '<VQuiz Group: {}>'.format(self.title)

#for virtual problem DB storage
class VProblem(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vproblem'
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(128))
    raw_prob = db.Column(db.String(1024))
    raw_ansr = db.Column(db.Text)
    example = db.Column(db.String(128))
    #no longer used; question type lives in qtype
    form_elem = db.Column(db.String(64))
    #see app/qgen/qtypes.py
    qtype = db.Column(db.String(32), default='numeric', nullable=False, server_default='numeric')
    #JSON: values table, choices and type settings
    options_json = db.Column('options', db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(64))
    calculator_ok = db.Column(db.Boolean, default=False)

    vpgroups = db.relationship('VPGroup', back_populates='vproblems', secondary=vproblem_vpgroup, lazy=True)
    vquizzes = db.relationship('VQuiz', back_populates='vproblems', secondary=vproblem_vquiz, lazy=True)
    cproblems = db.relationship('CProblem', backref='vproblem', lazy=True)

    @property
    def options(self):
        return json.loads(self.options_json or '{}')

    @options.setter
    def options(self, val):
        self.options_json = json.dumps(val)

    def __repr__(self):
        return '<Virtual Problem: {} : {}>'.format(self.title or 'Untitled', self.raw_prob)

#for virtual quiz DB storage
class VQuiz(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vquiz'
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(128))
    vpid_lst = db.Column(db.String(256))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(64))
    calculator_ok = db.Column(db.Boolean, default=False)

    vqgroups = db.relationship('VQGroup', back_populates='vquizzes', secondary=vquiz_vqgroup, lazy=True)
    vproblems = db.relationship('VProblem', back_populates='vquizzes', secondary=vproblem_vquiz, lazy=True)
    cquizzes = db.relationship('CQuiz', backref='vquiz', lazy=True)

    def __repr__(self):
        return '<Virtual Quiz: {} : {}>'.format(self.title or 'Untitled', self.vpid_lst)

#for concrete problem DB storage
class CProblem(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'cproblem'
    id = db.Column(db.Integer, primary_key=True)
    cquiz_id = db.Column(db.Integer, db.ForeignKey('cquiz.id', ondelete='CASCADE'))
    conc_prob = db.Column(db.String(1024))
    conc_ansr = db.Column(db.Text)
    #JSON: what this student was shown, e.g. choices and which are correct
    conc_opts_json = db.Column('conc_opts', db.Text)
    #the student's answer, as stored by its question type
    submitted = db.Column(db.Text)
    #0..1; None until graded
    credit = db.Column(db.Float)
    #instructor comment and [start, end, "right"|"wrong"] spans (JSON) on essays
    feedback = db.Column(db.Text)
    highlights_json = db.Column('highlights', db.Text)
    vproblem_id = db.Column(db.Integer, db.ForeignKey('vproblem.id'))
    ordinal = db.Column(db.Integer)

    @property
    def conc_opts(self):
        return json.loads(self.conc_opts_json or '{}')

    @conc_opts.setter
    def conc_opts(self, val):
        self.conc_opts_json = json.dumps(val)

    @property
    def highlights(self):
        return json.loads(self.highlights_json or '[]')

    @highlights.setter
    def highlights(self, val):
        self.highlights_json = json.dumps(val)

    def __repr__(self):
        return '<Concrete Problem: {} : {}>'.format(self.vproblem.title or 'Untitled', self.conc_prob)

#for concrete quiz DB storage
class CQuiz(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'cquiz'
    id = db.Column(db.Integer, primary_key=True)
    assignee = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    vquiz_id = db.Column(db.Integer, db.ForeignKey('vquiz.id'))
    transcript = db.Column(db.Text)
    completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    startdate = db.Column(db.DateTime, nullable=True)
    compdate = db.Column(db.DateTime, nullable=True)
    #submitted, but essays still need an instructor's grading
    needs_review = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    graded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    graded_date = db.Column(db.DateTime, nullable=True)

    cproblems = db.relationship('CProblem', backref='cquiz', lazy=True, order_by='CProblem.ordinal')
    taker = db.relationship('User', backref='cquizzes', lazy=True, foreign_keys=[assignee])
    grader = db.relationship('User', lazy=True, foreign_keys=[graded_by])

    @property
    def status(self):
        if self.completed:
            return 'completed'
        if self.needs_review:
            return 'review'
        if self.startdate:
            return 'started'
        return 'new'

    def __repr__(self):
        return '<Concrete Quiz: {} : {}>'.format(self.taker.username, self.vquiz.title or 'Untitled')




#log of "Fill in for me" requests; also used for the hourly limit
class AICall(db.Model):
    __tablename__ = 'aicall'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created = db.Column(db.DateTime, default=db.func.now(), index=True)
    kind = db.Column(db.String(16))
    request = db.Column(db.Text)
    ok = db.Column(db.Boolean, default=False)
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
