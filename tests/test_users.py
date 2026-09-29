import pytest


@pytest.fixture
def client():
    from app import app, db
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def register(client, name, email, code='maple-7'):
    from app.qgen.models import Setting
    if Setting.get('class_code') is None:
        Setting.put('class_code', 'maple-7')
    return client.post('/register', data={'class_code': code, 'username': name, 'email': email,
                                          'password': 'pw-for-tests', 'retype_password': 'pw-for-tests'})


def test_email_is_optional(client):
    from app.user.models import User
    assert register(client, 'amy', '').status_code == 302
    assert register(client, 'ben', 'None').status_code == 302
    assert register(client, 'cal', '  none  ').status_code == 302
    assert [u.email for u in User.query.order_by(User.username)] == [None, None, None]


def test_email_still_checked_when_given(client):
    from app.user.models import User
    assert register(client, 'dee', 'dee@example.com').status_code == 302
    r = register(client, 'eve', 'not-an-email')
    assert r.status_code == 200 and b"look like an email address" in r.data
    r = register(client, 'fay', 'dee@example.com')
    assert r.status_code == 200 and b'already taken' in r.data
    assert User.query.count() == 1


def test_admin_can_clear_an_email(client):
    from app.user.models import User
    from app import db
    register(client, 'gus', 'gus@example.com')
    admin = User(username='boss', is_admin=True)
    admin.set_password('pw-for-tests')
    db.session.add(admin)
    db.session.commit()
    client.post('/login', data={'username': 'boss', 'password': 'pw-for-tests'})
    gus = User.query.filter_by(username='gus').first()
    r = client.post('/edituser/{}'.format(gus.id), data={'username': 'gus', 'email': ''})
    assert r.status_code == 302
    assert db.session.execute(db.text('SELECT email FROM user WHERE id = :i'), {'i': gus.id}).scalar() is None


def test_class_code_controls_sign_up(client):
    from app.user.models import User
    from app.qgen.models import Setting
    r = client.get('/register')
    assert b'Sign-up is closed' in r.data
    Setting.put('class_code', 'Maple-7')
    assert b'Class code' in client.get('/register').data
    r = register(client, 'hal', '', code='wrong')
    assert r.status_code == 200 and b"class code isn" in r.data
    assert register(client, 'hal', '', code='  maple-7 ').status_code == 302
    assert User.query.filter_by(username='hal').count() == 1
