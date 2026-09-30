#!/bin/bash
# Start the site: nginx in front, gunicorn running the app.
# Runs from the conda base environment (nginx + gunicorn from ~/anaconda3).
# Safe to run again: whatever is already running is left alone.
cd "$(dirname "$0")"
NGINX_CONF=/home/dan/anaconda3/etc/nginx/nginx.conf

# nginx.conf says "daemon off", so start it detached from this terminal;
# otherwise this script would wait on it forever and never start gunicorn,
# and closing the terminal would stop the site.
if pgrep -x nginx >/dev/null; then
    echo "nginx: already running"
else
    setsid nohup nginx -c "$NGINX_CONF" >/dev/null 2>&1 < /dev/null &
    echo "nginx: started"
fi

if [ -S /tmp/qgen.sock ] && pgrep -f "gunicorn.*quizapp:app" >/dev/null; then
    echo "gunicorn: already running"
else
    rm -f /tmp/qgen.sock
    gunicorn --bind unix:/tmp/qgen.sock --workers 4 quizapp:app --daemon --log-level DEBUG
    echo "gunicorn: started"
fi

# wait a moment, then check the site answers
for i in 1 2 3 4 5 6 7 8 9 10; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:8080/login)
    [ "$code" = "200" ] && echo "site: up at http://localhost:8080" && exit 0
    sleep 1
done
echo "site: NOT answering yet (last status $code); check the logs"
exit 1
