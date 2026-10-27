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
    #pictures and other files in the Trash (private: not under static), until restored or deleted for good (the owner,
    #2026-10-26, To do 66); beside STATIC_DIR when that's set, so each site keeps its own
    UPLOAD_TRASH_DIR = os.environ.get('UPLOAD_TRASH_DIR') or (
        os.path.join(os.path.dirname(os.environ['STATIC_DIR'].rstrip('/')), 'upload-trash') if os.environ.get('STATIC_DIR')
        else os.path.join(basedir, 'instance', 'upload-trash'))
    #the AI helper's answers while the page waits for them (app/qgen/ai_jobs.py)
    AI_JOB_DIR = os.environ.get('AI_JOB_DIR') or os.path.join(basedir, 'instance', 'ai-jobs')
    #optional: enables the "Fill in for me" helper on the problem page
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
