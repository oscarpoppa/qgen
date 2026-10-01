import hashlib
import secrets
from datetime import datetime, timedelta

from app import db

TOKEN_DAYS = 90
TOKEN_PREFIX = 'qg_'
#failed API sign-ins allowed per username in the window below
MAX_FAILURES = 10
FAILURE_WINDOW = timedelta(minutes=15)


def fingerprint(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


#a personal access token for apps; only its fingerprint is stored
class ApiToken(db.Model):
    __tablename__ = 'api_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    #the first characters, so people can tell their tokens apart
    prefix = db.Column(db.String(12), nullable=False)
    created = db.Column(db.DateTime, default=datetime.now, nullable=False)
    last_used = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', backref=db.backref('api_tokens', cascade='all, delete-orphan', passive_deletes=True))

    @property
    def active(self):
        return not self.revoked and self.expires_at > datetime.now()

    @staticmethod
    def issue(user, name, days=TOKEN_DAYS):
        """Make a new token. Returns (row, the token text, which is shown only now)."""
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = ApiToken(user_id=user.id, name=(name or 'App')[:64], token_hash=fingerprint(token),
                       prefix=token[:10], expires_at=datetime.now() + timedelta(days=days))
        db.session.add(row)
        db.session.commit()
        return row, token

    @staticmethod
    def find(token):
        """The active token row for this text, or None."""
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        row = ApiToken.query.filter_by(token_hash=fingerprint(token)).first()
        return row if row and row.active else None


#failed API sign-ins, to slow down password guessing
class LoginFailure(db.Model):
    __tablename__ = 'login_failure'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    created = db.Column(db.DateTime, default=datetime.now, nullable=False)
    __table_args__ = (db.Index('ix_login_failure_username_created', 'username', 'created'),)

    @staticmethod
    def too_many(username):
        since = datetime.now() - FAILURE_WINDOW
        return LoginFailure.query.filter(LoginFailure.username == username, LoginFailure.created >= since).count() >= MAX_FAILURES

    @staticmethod
    def record(username):
        db.session.add(LoginFailure(username=(username or '')[:64]))
        #old rows are no longer needed
        LoginFailure.query.filter(LoginFailure.created < datetime.now() - FAILURE_WINDOW * 4).delete()
        db.session.commit()
