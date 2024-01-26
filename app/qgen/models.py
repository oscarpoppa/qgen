from app import db
from app.models import User

class SaveMixin:
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

# for many-to-many between vprobs and vquizzes
vproblem_vquiz = db.Table('vproblem_vquiz',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id')),
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id')))
    

class VProblem(db.Model, SaveMixin):
    __tablename__ = 'vproblem'
    id = db.Column(db.Integer, primary_key=True)
    raw_prob = db.Column(db.String(256))
    raw_answer = db.Column(db.String(128))
    form_elem = db.Column(db.String(64))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    vquizzes = db.relationship('VQuiz', back_populates='vproblems', secondary=vproblem_vquiz, lazy=True)
    cproblems = db.relationship('CProblem', backref='vproblem', lazy=True)

    def __repr__(self):
        return '<Virtual Problem: {}>'.format(self.raw_prob)


class VQuiz(db.Model, SaveMixin):
    __tablename__ = 'vquiz'
    id = db.Column(db.Integer, primary_key=True)
    vpid_lst = db.Column(db.String(256))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    vproblems = db.relationship('VProblem', back_populates='vquizzes', secondary=vproblem_vquiz, lazy=True)
    cquizzes = db.relationship('CQuiz', backref='vquiz', lazy=True)

    def __repr__(self):
        return '<Virtual Quiz: {}>'.format(self.vpid_lst)


class CProblem(db.Model, SaveMixin):
    __tablename__ = 'cproblem'
    id = db.Column(db.Integer, primary_key=True)
    cquiz_id = db.Column(db.Integer, db.ForeignKey('cquiz.id'))
    conc_prob = db.Column(db.String(256))
    conc_answer = db.Column(db.String(128))
    requestor = db.Column(db.Integer, db.ForeignKey('user.id'))
    vproblem_id = db.Column(db.Integer, db.ForeignKey('vproblem.id'))

    def __repr__(self):
        return '<Concrete Problem: {}>'.format(self.conc_prob)


class CQuiz(db.Model, SaveMixin):
    __tablename__ = 'cquiz'
    id = db.Column(db.Integer, primary_key=True)
    requestor = db.Column(db.Integer, db.ForeignKey('user.id'))
    vquiz_id = db.Column(db.Integer, db.ForeignKey('vquiz.id'))

    cproblems = db.relationship('CProblem', backref='cquiz', lazy=True)

    def __repr__(self):
        return '<Concrete Quiz: {}>'.format(self.id)

