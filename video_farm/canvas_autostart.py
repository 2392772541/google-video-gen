import os
import sys
import time
import socket
import threading
import subprocess
from pathlib import Path

CANVAS_ROOT = Path(r"D:\AI-Projects\infinite-canvas")
WEB_DIR = CANVAS_ROOT / "web"
VITE_BIN = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"
PROXY_DIR = CANVAS_ROOT / "canvas-proxy"

def is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except BaseException:
        return False

def ensure_canvas_3000():
    if is_port_listening(3000):
        return True
    if not WEB_DIR.exists() or not VITE_BIN.exists():
        return False
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["node", str(VITE_BIN), "preview", "--port", "3000", "--host", "127.0.0.1"]
    try:
        subprocess.Popen(
            cmd,
            cwd=str(WEB_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
        for _ in range(10):
            time.sleep(0.3)
            if is_port_listening(3000):
                return True
    except Exception as e:
        print(f"[Canvas Autostart] Failed to start canvas 3000: {e}", file=sys.stderr)
    return is_port_listening(3000)

def ensure_proxy_23210():
    if is_port_listening(23210):
        return True
    if not PROXY_DIR.exists() or not (PROXY_DIR / "index.js").exists():
        return False
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["node", "index.js", "--port", "23210", "--host", "127.0.0.1"]
    try:
        subprocess.Popen(
            cmd,
            cwd=str(PROXY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
        for _ in range(10):
            time.sleep(0.2)
            if is_port_listening(23210):
                return True
    except Exception as e:
        print(f"[Canvas Autostart] Failed to start proxy 23210: {e}", file=sys.stderr)
    return is_port_listening(23210)

def ensure_agent_17371():
    if is_port_listening(17371):
        return True
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["cmd.exe", "/c", "canvas-agent"]
    try:
        subprocess.Popen(
            cmd,
            cwd=str(CANVAS_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
        for _ in range(10):
            time.sleep(0.2)
            if is_port_listening(17371):
                return True
    except Exception as e:
        print(f"[Canvas Autostart] Failed to start agent 17371: {e}", file=sys.stderr)
    return is_port_listening(17371)

def ensure_canvas_services():
    """同步按需启动画布相关全套后台服务"""
    res_agent = ensure_agent_17371()
    res_proxy = ensure_proxy_23210()
    res_canvas = ensure_canvas_3000()
    return {
        "canvas_3000": res_canvas,
        "proxy_23210": res_proxy,
        "agent_17371": res_agent
    }

def ensure_canvas_services_async():
    """在后台独立线程中静默按需拉起，绝不阻塞主服务启动流程"""
    t = threading.Thread(target=ensure_canvas_services, daemon=True)
    t.start()
    return t
