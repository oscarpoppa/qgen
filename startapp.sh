#!/bin/bash
# Start the site: nginx in front, gunicorn running the app.
# Runs from the conda base environment (nginx + gunicorn from ~/anaconda3).
# Safe to run again: whatever is already running is left alone.
cd "$(dirname "$0")"
HERE=$(pwd -P)
NGINX_CONF=/home/dan/anaconda3/etc/nginx/nginx.conf
LIVE=/home/dan/proj/qgen-qtypes

# Only a copy with a .env (the database and other settings) can run the site. The
# development copies don't have one: started there, the app stops at once and
# nginx answers every page with 502.
if [ ! -f .env ]; then
    echo "NOT started: there's no .env in $HERE, so the app has no database settings here."
    if [ "$HERE" != "$LIVE" ]; then
        echo "The live site runs from $LIVE. Start it with:"
        echo "    $LIVE/startapp.sh"
    fi
    exit 1
fi

# Check the app loads before gunicorn goes into the background, where an error
# would only show as "gunicorn: started" and then a 502.
if ! out=$(timeout 60 python -c "import quizapp" 2>&1); then
    echo "NOT started: the app fails to load:"
    echo "$out" | tail -5
    exit 1
fi

# nginx.conf says "daemon off", so start it detached from this terminal;
# otherwise this script would wait on it forever and never start gunicorn,
# and closing the terminal would stop the site.
if pgrep -x nginx >/dev/null; then
    echo "nginx: already running"
else
    setsid nohup nginx -c "$NGINX_CONF" >/dev/null 2>&1 < /dev/null &
    echo "nginx: started"
fi

running=$(pgrep -o -f "gunicorn --bind unix:/tmp/qgen.sock")
if [ -S /tmp/qgen.sock ] && [ -n "$running" ]; then
    from=$(readlink "/proc/$running/cwd")
    echo "gunicorn: already running (from $from)"
    [ "$from" != "$HERE" ] && echo "  note: that's not this folder ($HERE)"
else
    rm -f /tmp/qgen.sock
    gunicorn --bind unix:/tmp/qgen.sock --workers 4 quizapp:app --daemon --log-level DEBUG
    #it runs in the background: make sure it's still there once it has had time to start
    for i in 1 2 3 4 5 6 7 8 9 10; do
        [ -S /tmp/qgen.sock ] && break
        sleep 1
    done
    if [ -S /tmp/qgen.sock ] && pgrep -f "gunicorn --bind unix:/tmp/qgen.sock" >/dev/null; then
        echo "gunicorn: started"
    else
        echo "gunicorn: NOT running (it started, then stopped). To see why, run it in this terminal:"
        echo "    cd $HERE && gunicorn --bind unix:/tmp/qgen.sock quizapp:app"
        exit 1
    fi
fi

# wait a moment, then check the site answers
for i in 1 2 3 4 5 6 7 8 9 10; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:8080/login)
    [ "$code" = "200" ] && echo "site: up at http://localhost:8080" && exit 0
    sleep 1
done
echo "site: NOT answering yet (last status $code); check the logs"
exit 1
