# -*- coding: utf-8 -*-
"""阅览围读插件后端，挂载于 /api/plugins/qiaomu-reader/。

职责：按需唤醒本地书库服务（server.py, 127.0.0.1:8766），不做别的。
服务本身完全独立进程，这里只负责 spawn + 探活。
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter

log = logging.getLogger(__name__)
router = APIRouter()

def _server_dir() -> Path:
    """定位 server.py 所在目录：QMU_SERVER_DIR 环境变量 > 从本文件向上找 > 默认仓库根。"""
    env = os.environ.get("QMU_SERVER_DIR")
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "server.py").exists():
            return parent
    return Path(r"D:\jalon\yuelan-weidu")

SERVER_DIR = _server_dir()
SERVER_SCRIPT = SERVER_DIR / "server.py"
PORT = 8766
LOG_FILE = SERVER_DIR / "server.log"
START_TIMEOUT = 20.0

# Windows: 新进程组 + 不弹窗，服务脱离本插件生命周期独立存活
DETACHED = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW


def _port_open(host: str = "127.0.0.1", port: int = PORT, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_python() -> str | None:
    """找可用的独立 Python：py -3.14 解析到系统级安装；先实测 encodings 可导入。"""
    import shutil
    py = shutil.which("py")
    if py:
        r = subprocess.run([py, "-3.14", "-I", "-c", "import encodings;print(1)"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and "1" in r.stdout:
            return py
    return None


def _spawn() -> str:
    py = _find_python()
    if not py:
        return "no-python"
    args = [py, "-3.14", "-I", "-u", str(SERVER_SCRIPT)]
    logf = open(LOG_FILE, "ab")
    kwargs: dict = {"stdout": logf, "stderr": logf, "cwd": str(SERVER_DIR)}
    if os.name == "nt":
        kwargs["creationflags"] = DETACHED
    subprocess.Popen(args, **kwargs)
    return "spawned"


@router.get("/status")
def status() -> dict:
    return {"running": _port_open(), "port": PORT}


@router.post("/start")
def start() -> dict:
    if _port_open():
        return {"ok": True, "state": "already-running", "port": PORT}
    try:
        state = _spawn()
    except OSError as e:
        return {"ok": False, "state": "spawn-failed", "error": str(e)}
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if _port_open():
            return {"ok": True, "state": state, "port": PORT}
        time.sleep(0.5)
    return {"ok": False, "state": state, "error": f"服务 {START_TIMEOUT}s 内未监听 {PORT}，看 {LOG_FILE}"}


@router.post("/stop")
def stop() -> dict:
    """ graceful：写一个停止标记文件让 server 自查？目前用 taskkill 兜底。"""
    try:
        subprocess.run(["taskkill", "/F", "/FI", f"WINDOWTITLE eq qiaomu*"],
                       capture_output=True, timeout=10)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    # 更可靠：按端口找 PID 杀
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10).stdout
    pids = {line.rsplit(None, 1)[-1] for line in out.splitlines()
            if f":{PORT}" in line and "LISTENING" in line}
    killed = []
    for pid in pids:
        if pid.isdigit():
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=10)
            killed.append(pid)
    return {"ok": True, "killed": killed}
