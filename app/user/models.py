from . import db, login
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import UserMixin
from datetime import timedelta

#"online": seen within this long
ONLINE_WINDOW = timedelta(minutes=2)

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    pw_man_reset = db.Column(db.Boolean, default=False)
    logged_in = db.Column(db.Boolean, default=False)
    #file name of the profile picture's square thumbnail (in the static folder)
    avatar = db.Column(db.String(128))
    #when this user last used the site (at most a minute out of date); see app/__init__.py
    last_seen = db.Column(db.DateTime, nullable=True, index=True)

    @property
    def online(self):
        """Active in the last couple of minutes (an open page checks in every 30 seconds)."""
        from datetime import datetime
        return bool(self.last_seen and datetime.now() - self.last_seen < ONLINE_WINDOW)

    def set_password(self, pswd):
        self.password_hash = generate_password_hash(pswd)

    def check_password(self, pswd):
        return check_password_hash(self.password_hash, pswd)

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

    def __repr__(self):
        return '<User {}>'.format(self.username)


#last_seen is written at most this often per user
SEEN_EVERY = timedelta(minutes=1)


def note_seen(user, now=None):
    """Record that this user is using the site (commits; never raises)."""
    from datetime import datetime
    now = now or datetime.now()
    if user.last_seen and timedelta(0) <= now - user.last_seen < SEEN_EVERY:
        return
    try:
        user.last_seen = now
        db.session.commit()
    except Exception:
        db.session.rollback()

