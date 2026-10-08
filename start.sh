#!/bin/sh
# Starts the Label Studio annotation stack:
#   1) snapshot CORS server on 127.0.0.1:8765  (article HTML embeds)
#   2) Label Studio itself on 127.0.0.1:8080   (foreground)
#
# The snapshot server keeps running in the background after Label Studio
# exits; stop it with: pkill -f cors_server.py

cd "$(dirname "$0")"

venv/bin/python cors_server.py &

echo "Open http://localhost:8080 and log in with your Label Studio account"
exec venv/bin/label-studio
