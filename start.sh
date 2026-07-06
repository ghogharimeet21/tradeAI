#!/bin/sh

ollama serve &

# Wait until Ollama is ready
until ollama list >/dev/null 2>&1; do
    sleep 1
done

exec python3.12 app.py