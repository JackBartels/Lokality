#!/bin/bash
# source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
"$(dirname "$0")/.venv/bin/python3" src/gui_assistant.py "$@"
