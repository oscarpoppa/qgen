"""The little picture in the browser tab (favicon): the one chosen in Settings, or else the
logo. It's made square (a wide picture is shrunk to fit, centred on a clear background) and
sized for tabs (32 px) and phone home screens (180 px)."""
import io
import os
import zlib

from flask import current_app

SIZES = (32, 180)
_made = {}  # (file, when it changed, size) -> PNG bytes, kept per server process


def chosen():
    """The picture's name in the static folder, or None: the favicon setting, else the logo."""
    from app.qgen.models import Setting
    return Setting.get('favicon') or Setting.get('logo')


def _path(name):
    folder = os.path.realpath(current_app.static_folder)
    path = os.path.realpath(os.path.join(folder, name))
    #never anything outside the static folder
    if not path.startswith(folder + os.sep) or not os.path.isfile(path):
        return None
    return path


def version(name):
    """Changes whenever the picture (or the choice) does, so browsers fetch the new one."""
    path = name and _path(name)
    if not path:
        return None
    return '{:x}{:x}'.format(zlib.crc32(name.encode()) & 0xffff, int(os.path.getmtime(path)))


def is_svg(name):
    return name.lower().endswith('.svg')


def png(name, size):
    """The picture as a square PNG of size x size, or None if it can't be read."""
    from PIL import Image
    path = name and _path(name)
    if not path or is_svg(name):
        return None
    key = (path, os.path.getmtime(path), size)
    if key not in _made:
        try:
            with Image.open(path) as im:
                im = im.convert('RGBA')
        except Exception:
            return None
        box = im.getbbox()  # leave out see-through edges
        if box:
            im = im.crop(box)
        side = max(im.size)
        square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
        square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        out = io.BytesIO()
        square.resize((size, size), Image.LANCZOS).save(out, 'PNG')
        if len(_made) > 50:
            _made.clear()
        _made[key] = out.getvalue()
    return _made[key]
