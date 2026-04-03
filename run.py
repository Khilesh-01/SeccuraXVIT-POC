#!/usr/bin/env python3
"""
DocVerify AI — Launch Script
Starts both the FastAPI backend and Streamlit frontend concurrently.

Usage:
    python run.py                    # Start both (default)
    python run.py --backend-only     # Only FastAPI backend
    python run.py --frontend-only    # Only Streamlit app
    python run.py --port-api 8000 --port-ui 8501
"""

import subprocess
import sys
import time
import signal
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).parent

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

processes = []


def banner():
    print(f"""
{BLUE}{BOLD}
╔══════════════════════════════════════════════════════════╗
║          🛡️  DocVerify AI — Document Verification        ║
║     Streamlit + LangGraph + Gemini 2.5 + FastAPI         ║
╚══════════════════════════════════════════════════════════╝
{RESET}""")


def start_backend(port: int = 8000):
    print(f"{GREEN}▶ Starting FastAPI backend on port {port}...{RESET}")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", str(port), "--reload"],
        cwd=ROOT,
        env=env,
    )
    processes.append(proc)
    return proc


def start_frontend(port: int = 8501, backend_url: str = "http://localhost:8000"):
    print(f"{GREEN}▶ Starting Streamlit frontend on port {port}...{RESET}")
    env = {**os.environ, "DOCVERIFY_BACKEND_URL": backend_url, "PYTHONPATH": str(ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(port),
         "--server.headless", "true",
         "--theme.base", "dark"],
        cwd=ROOT,
        env=env,
    )
    processes.append(proc)
    return proc


def shutdown(signum=None, frame=None):
    print(f"\n{YELLOW}⏹ Shutting down all services...{RESET}")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="DocVerify AI Launcher")
    parser.add_argument("--backend-only", action="store_true", help="Start only the backend API")
    parser.add_argument("--frontend-only", action="store_true", help="Start only the Streamlit frontend")
    parser.add_argument("--port-api", type=int, default=8000, help="Backend API port (default: 8000)")
    parser.add_argument("--port-ui", type=int, default=8501, help="Streamlit UI port (default: 8501)")
    args = parser.parse_args()

    banner()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    backend_url = f"http://localhost:{args.port_api}"

    if args.backend_only:
        start_backend(args.port_api)
        print(f"\n{BOLD}Backend API:{RESET} {BLUE}http://localhost:{args.port_api}{RESET}")
        print(f"{BOLD}API Docs:   {RESET} {BLUE}http://localhost:{args.port_api}/docs{RESET}\n")
    elif args.frontend_only:
        start_frontend(args.port_ui, backend_url)
        print(f"\n{BOLD}Frontend UI:{RESET} {BLUE}http://localhost:{args.port_ui}{RESET}")
        print(f"{YELLOW}Note: Backend not started — API calls will show 'unreachable' (amber){RESET}\n")
    else:
        start_backend(args.port_api)
        time.sleep(2)  # Give backend a moment to start
        start_frontend(args.port_ui, backend_url)

        print(f"""
{BOLD}{'─'*55}
  Services Running
{'─'*55}{RESET}
  {GREEN}✓{RESET} Backend API  → {BLUE}http://localhost:{args.port_api}{RESET}
  {GREEN}✓{RESET} API Docs     → {BLUE}http://localhost:{args.port_api}/docs{RESET}
  {GREEN}✓{RESET} Frontend UI  → {BLUE}http://localhost:{args.port_ui}{RESET}
{BOLD}{'─'*55}{RESET}
  Press {YELLOW}Ctrl+C{RESET} to stop all services
""")

    # Keep alive
    try:
        while True:
            for p in processes:
                if p.poll() is not None:
                    print(f"{RED}⚠ A process exited unexpectedly (code {p.returncode}){RESET}")
            time.sleep(2)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
