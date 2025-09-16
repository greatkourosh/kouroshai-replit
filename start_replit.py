import os
import sys
import time
import subprocess
import signal
import shutil

PORT = os.getenv("PORT", os.getenv("FASTAPI_PORT", "8000"))
PY = sys.executable

def ensure_env():
    # ensure TELEGRAM_BOT_TOKEN is present in Replit Secrets
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("Missing TELEGRAM_BOT_TOKEN env var. Set it in Replit Secrets.")
        sys.exit(1)

def start_uvicorn():
    cmd = [PY, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", PORT, "--log-level", "info"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def wait_for_server(timeout=30.0):
    import httpx
    url = f"http://127.0.0.1:{PORT}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            # server reachable (any response)
            return True
        except Exception:
            time.sleep(0.5)
    return False

def start_bot():
    # run the project's telegram bot file
    bot_path = os.path.join("kouroshai", "bot", "telegram_bot.py")
    return subprocess.Popen([PY, "-u", bot_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def relay(proc, name):
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(f"[{name}] {line}", end="")

def main():
    ensure_env()

    # ensure DB dir exists (uses project config)
    try:
        from kouroshai.core.database import initialize_database
        initialize_database()
    except Exception as e:
        print("DB init warning:", e)

    uvicorn_proc = start_uvicorn()
    print("Started uvicorn (pid=%s), waiting for server..." % uvicorn_proc.pid)

    if not wait_for_server(timeout=20.0):
        print("Warning: FastAPI did not respond in time; starting bot anyway (it will retry requests).")

    bot_proc = start_bot()
    print("Started telegram-bot (pid=%s)" % bot_proc.pid)

    # simple log relay loop
    try:
        while True:
            if uvicorn_proc.poll() is not None:
                print("uvicorn exited with code", uvicorn_proc.returncode)
                break
            if bot_proc.poll() is not None:
                print("telegram-bot exited with code", bot_proc.returncode)
                break
            # print available lines without blocking
            relay(uvicorn_proc, "uvicorn")
            relay(bot_proc, "bot")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        for p in (bot_proc, uvicorn_proc):
            try:
                p.send_signal(signal.SIGINT)
                p.wait(timeout=3)
            except Exception:
                p.kill()

if __name__ == "__main__":
    main()