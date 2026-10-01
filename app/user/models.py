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
        """Logged in, with a page open: seen in the last couple of minutes (an open page
        checks in every 30 seconds) and not logged out since."""
        from datetime import datetime
        return bool(self.logged_in and self.last_seen and datetime.now() - self.last_seen < ONLINE_WINDOW)

    @staticmethod
    def online_condition(now):
        """The same as .online, for queries."""
        return db.and_(User.last_seen >= now - ONLINE_WINDOW, User.logged_in.is_(True))

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

    def seen_label(self, now=None):
        """When this user was last on the site, in words: 'online now', '12 min ago',
        '3 h ago', 'yesterday', 'Sep 28', or 'never'."""
        from datetime import datetime
        if not self.last_seen:
            return 'never'
        now = now or datetime.now()
        ago = now - self.last_seen
        if ago < ONLINE_WINDOW and self.logged_in:
            return 'online now'
        if ago < timedelta(minutes=1):
            return 'just now'
        if ago < timedelta(hours=1):
            return '{} min ago'.format(int(ago.total_seconds() // 60))
        if self.last_seen.date() == now.date():
            return '{} h ago'.format(int(ago.total_seconds() // 3600))
        if (now.date() - self.last_seen.date()).days == 1:
            return 'yesterday'
        return '{:%b} {}'.format(self.last_seen, self.last_seen.day)

    def __repr__(self):
        return '<User {}>'.format(self.username)


#last_seen is written at most this often per user
SEEN_EVERY = timedelta(minutes=1)


def note_seen(user, now=None):
    """Record that this user is using the site (commits; never raises)."""
    from datetime import datetime
    now = now or datetime.now()
    #still signed in here after logging out somewhere else: they're logged in after all
    if user.last_seen and timedelta(0) <= now - user.last_seen < SEEN_EVERY and user.logged_in:
        return
    try:
        user.last_seen, user.logged_in = now, True
        db.session.commit()
    except Exception:
        db.session.rollback()

