"""Profile pictures: every upload is checked, cropped to a square, shrunk and
re-saved as PNG. Re-saving drops hidden photo data such as GPS location."""
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps

from app import db

SIZE = 256
FOLDER = 'avatars'
#a soft palette for initials, picked by name so each person always gets the same color
COLORS = ['#2f5bd3', '#1d7a46', '#b3261e', '#8a5a00', '#6b3fa0', '#0f7c8c', '#a1356e', '#46607a']


class AvatarError(ValueError):
    pass


def folder():
    path = os.path.join(current_app.config['STATIC_DIR'], FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def save(user, stream):
    """Replace a user's picture with the uploaded image."""
    try:
        img = Image.open(stream)
        img.verify()
        stream.seek(0)
        img = Image.open(stream)
        img = ImageOps.exif_transpose(img)  # phones store rotation separately
        img = ImageOps.fit(img.convert('RGB'), (SIZE, SIZE), Image.LANCZOS)
    except Exception:
        raise AvatarError('That doesn\'t look like a picture.')
    name = 'u{}-{}.png'.format(user.id, uuid.uuid4().hex[:8])
    img.save(os.path.join(folder(), name), 'PNG')
    remove(user, commit=False)
    user.avatar = '{}/{}'.format(FOLDER, name)
    db.session.commit()
    return user.avatar


def remove(user, commit=True):
    if user.avatar:
        path = os.path.join(current_app.config['STATIC_DIR'], user.avatar)
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder()) and os.path.exists(path):
            os.remove(path)
        user.avatar = None
    if commit:
        db.session.commit()


def initials(username):
    parts = [p for p in (username or '?').replace('_', ' ').replace('-', ' ').replace('.', ' ').split() if p]
    letters = ''.join(p[0] for p in parts[:2]) if len(parts) > 1 else (username or '?')[:2]
    return letters.upper()


def color(username):
    return COLORS[sum(map(ord, username or '')) % len(COLORS)]
