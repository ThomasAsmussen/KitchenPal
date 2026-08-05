#!/usr/bin/env bash
pkill -f "streamlit run" 2>/dev/null
sleep 1
streamlit run streamlit_app.py --server.port 8501 --server.headless true > /tmp/streamlit.log 2>&1 &
sleep 3
echo "http://localhost:8501 — logs at /tmp/streamlit.log"
