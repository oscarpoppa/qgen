#!/bin/bash
sudo nginx -c /etc/nginx/sites-available/quiz-app
gunicorn --bind unix:/home/dan/proj/quiz/run/quizapp.sock --workers 4 quizapp:app --daemon --access-logfile /var/log/gunicorn/access.log --error-logfile /var/log/gunicorn/error.log --log-level DEBUG
