#!/bin/bash
sudo nginx -c /etc/nginx/sites-available/quiz-app
sudo /home/dan/proj/quiz/venv/bin/gunicorn --bind unix:/tmp/quizapp.sock --workers 4 quizapp:app --daemon --access-logfile /var/log/gunicorn/access.log --error-logfile /var/log/gunicorn/error.log --log-level DEBUG
