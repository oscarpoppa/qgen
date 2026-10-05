from . import db
from app.user.models import User
from datetime import datetime, timedelta
import json
from sqlalchemy.dialects import mysql

#add save method
class SaveMixin:
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except:
            db.session.rollback()
            raise

#when a row was made, in the app's local time (like every other time it stores; the
#database's NOW() is UTC on SQLite)
class DateMixin:
    create_date = db.Column(db.DateTime, default=datetime.now)


# for many-to-many between vprobs and vquizzes
vproblem_vquiz = db.Table('vproblem_vquiz',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id', ondelete='CASCADE')),
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id', ondelete='CASCADE')))
    
# which problems are in which problem subjects (a problem can be in several)
vproblem_vpgroup = db.Table('vproblem_vpgroup',
    db.Column('vproblem_id', db.Integer, db.ForeignKey('vproblem.id', ondelete='CASCADE'), nullable=False),
    db.Column('vpgroup_id', db.Integer, db.ForeignKey('vpgroup.id', ondelete='CASCADE'), nullable=False),
    db.UniqueConstraint('vproblem_id', 'vpgroup_id', name='uq_vproblem_vpgroup'))

# which quizzes are in which quiz subjects
vquiz_vqgroup = db.Table('vquiz_vqgroup',
    db.Column('vquiz_id', db.Integer, db.ForeignKey('vquiz.id', ondelete='CASCADE'), nullable=False),
    db.Column('vqgroup_id', db.Integer, db.ForeignKey('vqgroup.id', ondelete='CASCADE'), nullable=False),
    db.UniqueConstraint('vquiz_id', 'vqgroup_id', name='uq_vquiz_vqgroup'))

#a teacher's subject for sorting problems (shown as "Subjects"; not the "2 of these 6"
#question groups inside a quiz)
class VPGroup(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vpgroup'
    __table_args__ = (db.UniqueConstraint('title', name='uq_vpgroup_title'),)
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(64))
    summary = db.Column(db.String(256))

    vproblems = db.relationship('VProblem', back_populates='vpgroups', secondary=vproblem_vpgroup, lazy=True)

    def __repr__(self):
        return '<VProblem Group: {}>'.format(self.title)

#a teacher's subject for sorting quizzes
class VQGroup(db.Model, SaveMixin, DateMixin):
    __tablename__ = 'vqgroup'
    __table_args__ = (db.UniqueConstraint('title', name='uq_vqgroup_title'),)
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
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
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
    #JSON list of problem ids and groups, see layout.py
    vpid_lst = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    title = db.Column(db.String(64))
    calculator_ok = db.Column(db.Boolean, default=False)
    #each student gets the questions in a different random order
    shuffle_order = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    #how several attempts combine into one score: see RETAKE_RULES
    retake_rule = db.Column(db.String(16), default='best', nullable=False, server_default='best')
    #keep correct answers off results pages until the teacher releases them
    hide_answers = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    answers_released = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())

    @property
    def answers_visible(self):
        return not self.hide_answers or self.answers_released

    @property
    def calculator_problems(self):
        """The problems in it (any group's too) that allow a calculator."""
        return [p for p in self.vproblems if p.calculator_ok]

    @property
    def calculator_allowed(self):
        """What students get: allowed if the quiz's box is checked or any problem it can give allows one."""
        return bool(self.calculator_ok or self.calculator_problems)

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
    #added by the older sandbox branch (new-qgen-everything); unused here, kept so its data is safe
    ans_field = db.Column(db.String(1024))
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
    graded_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    graded_date = db.Column(db.DateTime, nullable=True)
    #correct answers released to this student even though the quiz still hides them
    answers_released = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    #optional window and time limit (minutes) for this assignment
    opens_at = db.Column(db.DateTime, nullable=True)
    closes_at = db.Column(db.DateTime, nullable=True)
    time_limit = db.Column(db.Integer, nullable=True)
    #the teacher can override the quiz's retake rule for this student
    retake_rule = db.Column(db.String(16), nullable=True)
    @property
    def own_retake_rule(self):
        """This student's own rule, only when it really differs from the quiz's (a rule
        set to the same thing as the quiz's isn't a difference)."""
        rule = self.retake_rule
        return rule if rule and self.vquiz and rule != self.vquiz.retake_rule else None

    #a quiz with a future start: the student has been told it's open (or there's nothing to tell)
    open_notice_sent = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    #the taker has had My quizzes open since it was given to them (else it's counted next to
    #"My quizzes" in the menu); set False only when a quiz is given (assign, retake)
    seen_by_taker = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())

    cproblems = db.relationship('CProblem', backref='cquiz', lazy=True, order_by='CProblem.ordinal')
    taker = db.relationship('User', backref='cquizzes', lazy=True, foreign_keys=[assignee])
    grader = db.relationship('User', lazy=True, foreign_keys=[graded_by])

    def deadline(self):
        """When answers stop being accepted: the time limit or the close time, whichever is first."""
        ends = [t for t in (self.closes_at,) if t]
        if self.time_limit and self.startdate:
            ends.append(self.startdate + timedelta(minutes=self.time_limit))
        return min(ends) if ends else None

    def not_open_yet(self, now=None):
        return bool(self.opens_at and (now or datetime.now()) < self.opens_at)

    @property
    def when_label(self):
        """How an attempt is named in lists: its hand-in time, or when it was started or assigned."""
        def day(d):
            return '{:%b} {}'.format(d, d.day)
        if self.compdate and (self.completed or self.needs_review):
            d = self.compdate
            return '{}, {}:{:%M} {:%p}'.format(day(d), d.hour % 12 or 12, d, d)
        if self.startdate:
            return 'started {}'.format(day(self.startdate))
        return 'assigned {}'.format(day(self.create_date)) if self.create_date else 'not started'

    @property
    def answers_visible(self):
        """Correct answers show on this attempt's results: the quiz doesn't hide them,
        they were released for the whole quiz, or released to this student."""
        return self.vquiz.answers_visible or bool(self.answers_released)

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    created = db.Column(db.DateTime, default=db.func.now(), index=True)
    kind = db.Column(db.String(16))
    request = db.Column(db.Text)
    ok = db.Column(db.Boolean, default=False)
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)


#how a student's attempts at the same quiz combine into one score
RETAKE_RULES = {
    'best': 'The best attempt',
    'latest': 'The latest attempt',
    'average': 'The average of all attempts',
    'first': 'The first attempt',
    'best2': 'The average of the best two attempts',
}


def combined_score(rule, scores):
    """scores: finished attempts' scores, oldest first."""
    if not scores:
        return None
    if rule == 'latest':
        return scores[-1]
    if rule == 'first':
        return scores[0]
    if rule == 'average':
        return sum(scores) / len(scores)
    if rule == 'best2':
        top = sorted(scores, reverse=True)[:2]
        return sum(top) / len(top)
    return max(scores)


def counted_attempts(rule, done):
    """The finished attempt (oldest first) whose score is the one that counts, to mark it:
    [that attempt], or [] when none is or the score combines several (an average)."""
    if len(done) == 1:
        return list(done)
    if not done or rule in ('average', 'best2'):
        return []
    if rule == 'latest':
        return [done[-1]]
    if rule == 'first':
        return [done[0]]
    return [max(done, key=lambda c: c.score)]


#simple site-wide settings, e.g. the class code needed to sign up
class Setting(db.Model):
    __tablename__ = 'setting'
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)

    @staticmethod
    def get(key, default=None):
        row = db.session.get(Setting, key)
        return row.value if row and row.value is not None else default

    @staticmethod
    def put(key, value):
        row = db.session.get(Setting, key) or Setting(key=key)
        row.value = value
        db.session.add(row)
        db.session.commit()


def new_quizzes(user_id):
    """Quizzes given to this person (student or teacher) since they last opened My quizzes."""
    return CQuiz.query.filter(CQuiz.assignee == user_id, CQuiz.seen_by_taker.is_(False)).count()


def mark_quizzes_seen(user_id):
    """They've opened My quizzes: nothing there is new to the menu any more."""
    if CQuiz.query.filter(CQuiz.assignee == user_id, CQuiz.seen_by_taker.is_(False)) \
            .update({'seen_by_taker': True}, synchronize_session=False):
        db.session.commit()


def attempts_by_quiz(cquizzes):
    """A student's assigned quizzes grouped by quiz, for showing retakes:
    [{'vquiz', 'attempts' (oldest first), 'best' (a CQuiz or None), 'combined',
      'counted' (the attempt to mark as the one that counts, if one does)}]"""
    groups = {}
    for cq in sorted(cquizzes, key=lambda c: c.id):
        groups.setdefault(cq.vquiz_id, []).append(cq)
    out = []
    for attempts in groups.values():
        done = [c for c in attempts if c.completed and c.score is not None]
        vq = attempts[0].vquiz
        best = max(done, key=lambda c: c.score) if done else None
        override = next((c.own_retake_rule for c in reversed(attempts) if c.own_retake_rule), None)
        rule = override or vq.retake_rule
        out.append({'vquiz': vq, 'attempts': attempts, 'best': best, 'latest': attempts[-1],
                    'combined': combined_score(rule, [c.score for c in done]),
                    'counted': counted_attempts(rule, done),
                    'rule': RETAKE_RULES.get(rule, RETAKE_RULES['best']), 'rule_key': rule,
                    'overridden': bool(override)})
    #newest activity first
    return sorted(out, key=lambda g: -g['attempts'][-1].id)


#a long text column: MySQL's plain TEXT stops at 64 KB
LongText = db.Text().with_variant(mysql.LONGTEXT(), "mysql")


#a folder on the Archive page. Each student gets one automatically (student_id), named
#after them; the teacher can also make their own. Renaming a student's folder makes it
#an ordinary folder (the student gets a new one in their name). Deleting a folder moves
#what's in it to Unsorted (attempts with no folder); a deleted student folder's row is
#kept (removed=True) so it isn't made again on its own, and the student's next archived
#attempt brings it back under their name. If the account is deleted, the folder stays.
class ArchiveFolder(db.Model):
    __tablename__ = 'archive_folder'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), unique=True)
    removed = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())

    def __repr__(self):
        return '<Archive folder {}>'.format(self.name)


#a student's attempt the teacher deleted (or whose account was deleted), kept so it can
#be looked at, restored or deleted for good later. The attempt is moved here whole, so
#the rest of the site never has to tell archived attempts from live ones.
class ArchivedAttempt(db.Model):
    __tablename__ = 'archived_attempt'
    id = db.Column(db.Integer, primary_key=True)
    #the attempt's id while it was live (restore puts it back under the same one)
    original_id = db.Column(db.Integer, nullable=False)
    vquiz_id = db.Column(db.Integer, db.ForeignKey('vquiz.id', ondelete='SET NULL'), index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), index=True)
    #kept as they were, so the record still reads right after a quiz or student is deleted
    student_name = db.Column(db.String(64), nullable=False)
    quiz_title = db.Column(db.String(64), nullable=False)
    score = db.Column(db.Float)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    needs_review = db.Column(db.Boolean, default=False, nullable=False)
    startdate = db.Column(db.DateTime)
    compdate = db.Column(db.DateTime)
    assigned = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    #",3,7," - the problems it used, so deleting a problem can say it is used here
    problem_ids = db.Column(db.Text, nullable=False, default=',')
    #the Archive folder it's in; none means Unsorted
    folder_id = db.Column(db.Integer, db.ForeignKey('archive_folder.id', ondelete='SET NULL'), index=True)
    #'deleted' (the attempt) or 'student deleted' (the account)
    reason = db.Column(db.String(16), default='deleted', nullable=False)
    #a compact JSON record of the attempt and its questions (no page markup): the
    #results page is drawn from it, and restoring rebuilds the attempt from it
    data = db.deferred(db.Column(LongText, nullable=False))

    vquiz = db.relationship('VQuiz', lazy=True)
    archiver = db.relationship('User', foreign_keys=[archived_by], lazy=True)
    folder = db.relationship('ArchiveFolder', lazy=True)

    def __repr__(self):
        return '<Archived attempt {}: {} : {}>'.format(self.original_id, self.student_name, self.quiz_title)
