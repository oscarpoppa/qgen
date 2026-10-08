"""Profile pictures and app tokens on the profile page."""
import io
import os

from PIL import Image

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_api import Api


def photo(size=(300, 200), color='orange', exif_gps=False):
    buf = io.BytesIO()
    img = Image.new('RGB', size, color)
    if exif_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: 'N', 2: (40.0, 26.0, 46.0)}  # GPS info
        img.save(buf, 'JPEG', exif=exif)
    else:
        img.save(buf, 'PNG')
    buf.seek(0)
    return buf


def test_student_sets_and_removes_own_picture(app_db):
    app, db = app_db
    from app.user.models import User
    sam = login(app, 'sam')
    r = sam.post('/profile/avatar', data={'file': (photo(exif_gps=True), 'me.jpg')}, content_type='multipart/form-data')
    assert r.get_json()['ok'], r.get_json()
    u = User.query.filter_by(username='sam').one()
    path = os.path.join(app.config['STATIC_DIR'], u.avatar)
    saved = Image.open(path)
    assert saved.size == (256, 256) and saved.format == 'PNG' and not saved.getexif()  # cropped, location data gone
    # shown on the home page and in the menu
    home = sam.get('/home').data.decode()
    assert u.avatar in home and 'title="Change your nickname or picture">My profile</a>' in home  # a button on Home, and in the menu
    # not a picture
    r = sam.post('/profile/avatar', data={'file': (io.BytesIO(b'hello'), 'x.png')}, content_type='multipart/form-data')
    assert not r.get_json()['ok']
    # a new picture replaces the old file
    sam.post('/profile/avatar', data={'file': (photo(color='blue'), 'b.png')}, content_type='multipart/form-data')
    db.session.expire_all()
    assert not os.path.exists(path) and os.path.exists(os.path.join(app.config['STATIC_DIR'], User.query.filter_by(username='sam').one().avatar))
    # students can't remove someone else's picture
    kim_id = User.query.filter_by(username='kim').one().id
    sam.post('/avatar/remove/{}'.format(kim_id))
    sam.post('/avatar/remove/{}'.format(u.id))
    db.session.expire_all()
    assert User.query.filter_by(username='sam').one().avatar is None


def test_teacher_removes_a_picture_and_initials_show(app_db):
    app, db = app_db
    from app.user.models import User
    sam = login(app, 'sam')
    sam.post('/profile/avatar', data={'file': (photo(), 'me.png')}, content_type='multipart/form-data')
    teacher = login(app, 'teach')
    users = teacher.get('/userdet').data.decode()
    assert 'Remove picture' in users and 'avatar-initials' in users  # kim and the teacher have initials
    sam_u = User.query.filter_by(username='sam').one()
    teacher.post('/avatar/remove/{}'.format(sam_u.id))
    db.session.expire_all()
    assert User.query.filter_by(username='sam').one().avatar is None
    # deleting a user deletes their picture file too
    kim = login(app, 'kim')
    kim.post('/profile/avatar', data={'file': (photo(), 'k.png')}, content_type='multipart/form-data')
    kim_u = User.query.filter_by(username='kim').one()
    db.session.refresh(kim_u)
    path = os.path.join(app.config['STATIC_DIR'], kim_u.avatar)
    teacher.post('/deluser/{}'.format(kim_u.id))
    assert not os.path.exists(path)


def test_tokens_on_the_profile_page_are_for_teachers(app_db):
    app, db = app_db
    from app.api.models import ApiToken
    from app.user.models import User
    # students see no app/API section and can't make tokens from the page
    sam = login(app, 'sam')
    page = sam.get('/profile').data.decode()
    assert 'Apps' not in page and 'Create token' not in page and '/api/' not in page
    sam.post('/profile/tokens', data={'name': 'x'})
    assert ApiToken.query.count() == 0
    # teachers do
    teach = login(app, 'teach')
    page = teach.post('/profile/tokens', data={'name': 'My phone'}).data.decode()
    token = page.split('id="new-token">')[1].split('<')[0]
    assert token.startswith('qg_')
    assert token not in teach.get('/profile').data.decode()  # shown once only
    api = Api(app)
    api.token = token
    assert api.get('/me').get_json()['username'] == 'teach'
    row = ApiToken.query.one()
    t2 = User(username='t2', is_admin=True); t2.set_password('pw-for-tests'); db.session.add(t2); db.session.commit()
    login(app, 't2').post('/profile/tokens/{}/revoke'.format(row.id))
    assert api.get('/me').status_code == 200  # not t2's to revoke
    teach.post('/profile/tokens/{}/revoke'.format(row.id))
    assert api.get('/me').status_code == 401


def test_picture_through_the_api(app_db):
    app, db = app_db
    sam = Api(app, 'sam')
    r = sam.post('/me/avatar', data={'file': (photo(), 'me.png')}, content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['avatar_url'].endswith('.png')
    assert sam.post('/me/avatar', data={}, content_type='multipart/form-data').status_code == 400
    assert sam.delete('/me/avatar').status_code == 204
    assert sam.get('/me').get_json()['avatar_url'] is None
