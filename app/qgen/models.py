from . import db
from app.user.models import User
from datetime import datetime

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
    raw_ansr = db.Column(db.String(128))
    example = db.Column(db.String(128))
    form_elem = db.Column(db.String(64))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(64))
    calculator_ok = db.Column(db.Boolean, default=False)

    vpgroups = db.relationship('VPGroup', back_populates='vproblems', secondary=vproblem_vpgroup, lazy=True)
    vquizzes = db.relationship('VQuiz', back_populates='vproblems', secondary=vproblem_vquiz, lazy=True)
    cproblems = db.relationship('CProblem', backref='vproblem', lazy=True)

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
    conc_ansr = db.Column(db.String(128))
    vproblem_id = db.Column(db.Integer, db.ForeignKey('vproblem.id'))
    ordinal = db.Column(db.Integer)

    def __repr__(self):
        return '<Concrete Problem: {} : {}>'.format(self.vproblem.title or 'Untitled', self.conc_prob)

#for concrete quiz DB storage
class CQuiz(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'cquiz'
    id = db.Column(db.Integer, primary_key=True)
    assignee = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    vquiz_id = db.Column(db.Integer, db.ForeignKey('vquiz.id'))
    transcript = db.Column(db.String(8192))
    completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    startdate = db.Column(db.DateTime, nullable=True)
    compdate = db.Column(db.DateTime, nullable=True)

    cproblems = db.relationship('CProblem', backref='cquiz', lazy=True)
    taker = db.relationship('User', backref='cquizzes', lazy=True)

    def __repr__(self):
        return '<Concrete Quiz: {} : {}>'.format(self.taker.username, self.vquiz.title or 'Untitled')


