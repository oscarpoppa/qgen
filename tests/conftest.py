import os
import sys

#tests never touch a real database or need a real .env
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
