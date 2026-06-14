@echo off
REM Cheapest Buy-It-Now refresh for PokeHart Collectors (called by Task Scheduler).
cd /d "D:\Project Pokemon"
.venv\Scripts\python.exe run.py refresh-listings >> data\refresh-listings.log 2>&1
