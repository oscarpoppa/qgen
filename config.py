import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))

# secrets live in .env (never committed) -- see .env.example
load_dotenv(os.path.join(basedir, '.env'))

#fail fast with a clear message instead of falling back to a built-in secret
def required(name):
    val = os.environ.get(name)
    if not val:
        raise RuntimeError('{} is not set. Copy .env.example to .env and fill it in.'.format(name))
    return val


class Config(object):
    SQLALCHEMY_DATABASE_URI = required('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = required('SECRET_KEY')
    #uploaded images/files and site css/js (nginx serves /static from here too)
    STATIC_DIR = os.environ.get('STATIC_DIR') or os.path.join(basedir, 'static')
    #workbook pages being scanned (private: not under static), until saved or discarded
    SCAN_DIR = os.environ.get('SCAN_DIR') or os.path.join(basedir, 'instance', 'scans')
    #optional: enables the "Fill in for me" helper on the problem page
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
