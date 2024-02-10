from app import db
from app.models import User
from datetime import datetime

class SaveMixin:
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

class DateMixin:
    create_date = db.Column(db.DateTime, default=db.func.now())


# for many-to-many between vprobs and vquizzes
vproblem_vquiz = db.Table('vproblem_vquiz',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id')),
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id')))
    

class VProblem(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vproblem'
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(128))
    raw_prob = db.Column(db.String(256))
    raw_ansr = db.Column(db.String(128))
    example = db.Column(db.String(128))
    form_elem = db.Column(db.String(64))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    vquizzes = db.relationship('VQuiz', back_populates='vproblems', secondary=vproblem_vquiz, lazy=True)
    cproblems = db.relationship('CProblem', backref='vproblem', lazy=True)

    def __repr__(self):
        return '<Virtual Problem: {}>'.format(self.raw_prob)


class VQuiz(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vquiz'
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(128))
    vpid_lst = db.Column(db.String(256))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(64))

    vproblems = db.relationship('VProblem', back_populates='vquizzes', secondary=vproblem_vquiz, lazy=True)
    cquizzes = db.relationship('CQuiz', backref='vquiz', lazy=True)

    def __repr__(self):
        return '<Virtual Quiz: {}>'.format(self.vpid_lst)


class CProblem(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'cproblem'
    id = db.Column(db.Integer, primary_key=True)
    cquiz_id = db.Column(db.Integer, db.ForeignKey('cquiz.id'))
    conc_prob = db.Column(db.String(256))
    conc_ansr = db.Column(db.String(128))
    vproblem_id = db.Column(db.Integer, db.ForeignKey('vproblem.id'))
    ordinal = db.Column(db.Integer)

    def __repr__(self):
        return '<Concrete Problem: {}>'.format(self.conc_prob)


class CQuiz(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'cquiz'
    id = db.Column(db.Integer, primary_key=True)
    assignee = db.Column(db.Integer, db.ForeignKey('user.id'))
    vquiz_id = db.Column(db.Integer, db.ForeignKey('vquiz.id'))
    transcript = db.Column(db.String(2048))
    completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    startdate = db.Column(db.DateTime, nullable=True)
    compdate = db.Column(db.DateTime, nullable=True)

    cproblems = db.relationship('CProblem', backref='cquiz', lazy=True)
    taker = db.relationship('User', backref='cquizzes', lazy=True)

    def __repr__(self):
        return '<Concrete Quiz: {}>'.format(self.id)


