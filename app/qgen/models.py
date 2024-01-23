from app import db
from app.models import User

class Ppatt(db.Model):
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
        return '<Ppattern: {}>'.format(self.raw_prob)

