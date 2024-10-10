import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://dan:***REMOVED***@localhost/quiz'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'whatever...'

