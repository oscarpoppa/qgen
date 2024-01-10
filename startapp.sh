#!/bin/bash
sudo nginx -c /etc/nginx/sites-available/quiz-app
gunicorn --bind unix:run/quizapp.sock -m 007 --workers 4 quizapp:app --daemon --access-logfile /var/log/gunicorn/access.log --error-logfile /var/log/gunicorn/error.log --log-level DEBUG
