from app import db
from app.models import User

class VProblem(db.Model):
    __tablename__ = 'vproblem'
    id = db.Column(db.Integer, primary_key=True)
    raw_prob = db.Column(db.String(256))
    raw_answer = db.Column(db.String(128))
    form_elem = db.Column(db.String(64))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

    def __repr__(self):
        return '<VProblem: {}>'.format(self.raw_prob)


class VQuiz(db.Model):
    __tablename__ = 'vquiz'
    id = db.Column(db.Integer, primary_key=True)
    vpid_dict = db.Column(db.String(256))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

    def __repr__(self):
        return '<Virtual Problem: {}>'.format(self.raw_prob)


class VQuizProblem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vq_id = db.Column(db.Integer, db.ForeignKey('vquiz.id'))
    vp_id = db.Column(db.Integer, db.ForeignKey('vproblem.id'))



##################################################################
class CProblem(db.Model):
    __tablename__ = 'cproblem'
    id = db.Column(db.Integer, primary_key=True)
    conc_prob = db.Column(db.String(256))
    conc_answer = db.Column(db.String(128))
    requestor = db.Column(db.Integer, db.ForeignKey('user.id'))
    vparent = db.Column(db.Integer, db.ForeignKey('vproblem.id'))

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

    def __repr__(self):
        return '<Concrete Problem: {}>'.format(self.conc_prob)

