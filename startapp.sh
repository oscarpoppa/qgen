#!/bin/bash
# runs from the conda base environment (nginx + gunicorn from ~/anaconda3)
cd "$(dirname "$0")"
nginx -c /home/dan/anaconda3/etc/nginx/nginx.conf
gunicorn --bind unix:/tmp/qgen.sock --workers 4 quizapp:app --daemon --log-level DEBUG
