#!/bin/sh
# Pulls the chat and embedding models into the Ollama volume (first run only; cached afterwards).
set -e
: "${OLLAMA_HOST:=http://ollama:11434}"
: "${LLM_MODEL:=llama3.2:3b}"
: "${EMBEDDING_MODEL:=nomic-embed-text}"
export OLLAMA_HOST

echo "waiting for ollama at $OLLAMA_HOST ..."
until ollama list >/dev/null 2>&1; do sleep 2; done

for m in "$EMBEDDING_MODEL" "$LLM_MODEL"; do
  echo "pulling $m"
  ollama pull "$m"
done
echo "models ready"
