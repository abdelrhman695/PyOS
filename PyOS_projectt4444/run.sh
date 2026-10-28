#!/bin/bash
# Run PyOS — installs dependencies and launches the app
cd "$(dirname "$0")"
pip install -r requirements.txt -q
python main.py
