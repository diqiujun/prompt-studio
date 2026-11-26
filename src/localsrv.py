# -*- coding: utf-8 -*-
r"""本地 llama.cpp 服务管理：把 gemma-4-e2b 三件套（主模型 + 视觉投影 + MTP 草稿）
拉起来并注册成一个 OpenAI 兼容 provider，供本程序直接调用。

设计要点
- 模型与 llama.cpp 运行时随发行目录一起分发（<程序目录>/models 与 <程序目录>/llama），
  开发机上找不到时回退到 E:\llama。
- llama-server 由本程序托管：启动时拉起、退出时杀掉，用户不需要手动开窗口。
- 硬件自动适配：探测 NVIDIA 显存 / 内存 / CPU 核数，自动决定 GPU 层数与上下文长度；
  没有 NVIDIA 显卡或显存不足时纯 CPU 跑（-ngl 0），CUDA 版起不来自动降级重试。
- MTP（--spec-type draft-mtp）在该组合上不稳（进程会在加载后秒退），所以默认关闭，
  可在设置里手动开启；开启后若 N 秒内没就绪，自动回退成不开 MTP 再试一次。
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import settings

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

PROV_ID = "local-gemma"

MODEL_REL = os.path.join("models", "gemma-4-e2b")
MODEL_NAME = "gemma-4-E2B-it-Q4_K_M.gguf"
MMPROJ_NAME = "mmproj-F16.gguf"
MTP_NAME = "mtp-gemma-4-E2B-it.gguf"

DEFAULT_LOCAL = {
    "auto": True,
    "enabled": True,
    "llama_dir": r"E:\llama",
    "model": r"E:\llama\models\gemma-4-e2b\gemma-4-E2B-it-Q4_K_M.gguf",
    "mmproj": r"E:\llama\models\gemma-4-e2b\mmproj-F16.gguf",
    "mtp": r"E:\llama\models\gemma-4-e2b\mtp-gemma-4-E2B-it.gguf",
    "port": 8910,
    "ctx": 0,          # 0 = 按硬件自动决定
    "ngl": -1,         # -1 = 按硬件自动决定
    "threads": 0,
    "spec_n_max": 4,
    "use_mtp": False,
    "alias": "gemma-4-e2b",
    "ready_timeout": 240,
    "auto_unload": True,   # 生成前按需加载、生成完就卸载（省显存）
}


def bundled_paths() -> dict:
    """发行目录里自带的模型与运行时路径（拷贝到任何机器上都用这一套）。"""
    root = settings.app_root()
    d = os.path.join(root, MODEL_REL)
    return {
        "llama_dir": os.path.join(root, "llama"),
        "model": os.path.join(d, MODEL_NAME),
        "mmproj": os.path.join(d, MMPROJ_NAME),
        "mtp": os.path.join(d, MTP_NAME),
    }


# ---------------------------------------------------------------- 硬件探测

def _nvidia() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, timeout=10, encoding="mbcs", errors="ignore",
            creationflags=CREATE_NO_WINDOW).stdout or ""
        line = [l for l in out.strip().splitlines() if l.strip()]
        if not line:
            return None
        parts = [x.strip() for x in line[0].split(",")]
        return {"name": parts[0], "vram_mb": int(float(parts[1]))}
    except Exception:
        return None


def _ram_mb() -> int:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    try:
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullTotalPhys / (1024 * 1024))
    except Exception:
        return 0


def detect_hardware() -> dict:
    """返回 {gpu:{name,vram_mb}|None, ram_mb, cores, mode}"""
    gpu = _nvidia()
    ram = _ram_mb()
    cores = os.cpu_count() or 4
    if gpu and gpu["vram_mb"] >= 3500:
        mode = "gpu"
    elif gpu:
        mode = "gpu-lite"
    else:
        mode = "cpu"
    return {"gpu": gpu, "ram_mb": ram, "cores": cores, "mode": mode}


def auto_tune(hw: dict) -> dict:
    """按显存/内存决定 GPU 层数与上下文。权重约 3.9GB（主 2.96 + 视觉 0.94）。"""
    vram = int((hw.get("gpu") or {}).get("vram_mb") or 0)
    ram = int(hw.get("ram_mb") or 0)
    cores = int(hw.get("cores") or 4)
    if vram >= 10240:                 # 10GB+：全上 GPU，大上下文
        return {"ngl": 99, "ctx": 32768, "threads": 0, "tier": "gpu-high",
                "note": "显卡 %.1f GB，全量 GPU 加速" % (vram / 1024.0)}
    if vram >= 7168:                  # 7–10GB（8G 卡）
        return {"ngl": 99, "ctx": 16384, "threads": 0, "tier": "gpu",
                "note": "显卡 %.1f GB，全量 GPU 加速" % (vram / 1024.0)}
    if vram >= 5120:                  # 5–7GB
        return {"ngl": 99, "ctx": 8192, "threads": 0, "tier": "gpu",
                "note": "显卡 %.1f GB，全量 GPU 加速（上下文缩短到 8192）" % (vram / 1024.0)}
    if vram >= 3500:                  # 3.5–5GB：部分层上 GPU
        return {"ngl": 22, "ctx": 4096, "threads": 0, "tier": "gpu-lite",
                "note": "显卡 %.1f GB，部分层放 GPU，其余 CPU" % (vram / 1024.0)}
    thr = max(4, min(16, cores - 1))
    if ram and ram < 8000:
        return {"ngl": 0, "ctx": 2048, "threads": thr, "tier": "cpu-low",
                "note": "内存 %.1f GB，纯 CPU 跑，上下文 2048（较慢）" % (ram / 1024.0)}
    ctx = 8192 if ram >= 24000 else 4096
    return {"ngl": 0, "ctx": ctx, "threads": thr, "tier": "cpu",
            "note": "未检测到可用 NVIDIA 显卡，纯 CPU 跑（%d 线程，上下文 %d）" % (thr, ctx)}


# ---------------------------------------------------------------- 配置

def normalize(cfg: dict | None, tune: bool = True) -> dict:
    """合并默认值：先补发行目录自带的模型路径，再叠加用户配置，最后按硬件调参。"""
    out = dict(DEFAULT_LOCAL)
    bundled = bundled_paths()
    # 发行目录里带了模型就用自带的（拷贝到别的电脑也能跑）
    if os.path.isfile(bundled["model"]):
        out.update(bundled)
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            if k in out and v not in (None, ""):
                out[k] = v
    for k in ("port", "ctx", "ngl", "threads", "spec_n_max", "ready_timeout"):
        try:
            out[k] = int(out[k])
        except (TypeError, ValueError):
            out[k] = DEFAULT_LOCAL[k]
    out["auto"] = bool(out["auto"])
    out["auto_unload"] = bool(out["auto_unload"])
    out["use_mtp"] = bool(out["use_mtp"])
    out["enabled"] = bool(out["enabled"])
    if tune:
        hw = detect_hardware()
        t = auto_tune(hw)
        if int(out["ngl"]) < 0:
            out["ngl"] = t["ngl"]
        if int(out["ctx"]) <= 0:
            out["ctx"] = t["ctx"]
        if int(out["threads"]) <= 0 and t["threads"]:
            out["threads"] = t["threads"]
        out["_hw"] = hw
        out["_tier"] = t["tier"]
        out["_tune_note"] = t["note"]
    return out


# ---------------------------------------------------------------- 进程

def find_exe(llama_dir: str) -> str:
    # 1) 程序自带、按硬件装好的运行环境（runtime/<包 id>/llama-server.exe）
    try:
        import runtimes
        e = runtimes.any_installed_exe()
        if e:
            return e
    except Exception:
        pass
    cands = [
        os.path.join(llama_dir, "llama-server.exe"),
        os.path.join(llama_dir, "build", "bin", "Release", "llama-server.exe"),
        os.path.join(llama_dir, "build", "bin", "llama-server.exe"),
        os.path.join(llama_dir, "server-cublas", "llama-server.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    import shutil
    which = shutil.which("llama-server")
    if which:
        return which
    raise FileNotFoundError(
        "没找到 llama-server.exe。请把 llama.cpp 的 windows 版解压到 %s，"
        "或在设置页填写正确的目录。查找过：%s" % (llama_dir, "; ".join(cands)))


def find_exe_ok() -> bool:
    """运行环境是否已就绪（自带包已安装，或用户自己指定了目录）。"""
    try:
        import runtimes
        if runtimes.any_installed_exe():
            return True
    except Exception:
        pass
    try:
        cfg = settings.load_config()
        find_exe(str((cfg.get("local") or {}).get("llama_dir") or r"E:\llama"))
        return True
    except Exception:
        return False


def build_args(c: dict, with_mtp: bool | None = None) -> list[str]:
    if with_mtp is None:
        with_mtp = bool(c.get("use_mtp"))
    args = [
        "-m", c["model"],
        "-c", str(c["ctx"]),
        "-ngl", str(c["ngl"]),
        "--port", str(c["port"]),
        "--host", "127.0.0.1",
        "--alias", str(c["alias"]),
        "--no-ui",
    ]
    if int(c.get("threads") or 0) > 0:
        args += ["-t", str(int(c["threads"]))]
    mmproj = str(c.get("mmproj") or "")
    if mmproj and os.path.isfile(mmproj):
        args += ["-mm", mmproj]
    mtp = str(c.get("mtp") or "")
    if with_mtp and mtp and os.path.isfile(mtp):
        args += ["--spec-type", "draft-mtp", "--spec-draft-model", mtp,
                 "--spec-draft-n-max", str(int(c.get("spec_n_max") or 4))]
    return args


def probe(port: int, timeout: float = 1.5) -> dict | None:
    url = "http://127.0.0.1:%d/v1/models" % int(port)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_ready(port: int, proc=None, secs: int = 180) -> bool:
    end = time.time() + max(5, int(secs))
    while time.time() < end:
        if probe(port):
            return True
        if proc is not None and proc.poll() is not None:
            return False          # 进程已经退出，不用再等
        time.sleep(1.0)
    return False


def running_pid(port: int) -> int | None:
    """端口已在服务时，尽量找出对应 pid（找不到就返回 -1 表示在跑但 pid 未知）。"""
    info = probe(port, 2.0)
    if not info:
        return None
    try:
        # netstat 在中文 Windows 上是 GBK 输出：不能按 utf-8 解码，否则 reader 线程抛
        # UnicodeDecodeError 导致 stdout 变成 None。用 mbcs（系统 ANSI 代码页）并忽略错误。
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, timeout=10,
            encoding="mbcs", errors="ignore", creationflags=CREATE_NO_WINDOW).stdout or ""
    except Exception:
        return -1
    needle = "127.0.0.1:%d" % int(port)
    for line in out.splitlines():
        if needle in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    pass
    return -1


def start(c: dict, log_path: str, force_mtp: bool | None = None) -> dict:
    """启动（或复用已启动的）llama-server。返回 {ok, running, pid, port, log, exe, note}"""
    c = normalize(c)
    if not c.get("enabled", True):
        return {"ok": False, "error": "本地模型功能已在设置里关闭"}
    model = str(c.get("model") or "")
    if not os.path.isfile(model):
        return {"ok": False, "error": "找不到主模型文件：%s（请在设置页填写正确路径）" % model}
    port = int(c["port"])

    info = probe(port, 2.0)
    if info:
        return {"ok": True, "running": True, "pid": running_pid(port), "port": port,
                "note": "端口 %d 上已经有 llama-server 在跑，直接复用" % port,
                "models": info}

    exe = find_exe(str(c.get("llama_dir") or ""))
    os.makedirs(os.path.dirname(os.path.abspath(log_path)) or ".", exist_ok=True)
    log = open(log_path, "ab", buffering=0)
    log.write(("\n\n===== %s 启动 %s =====\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), exe)).encode("utf-8"))

    with_mtp = bool(c.get("use_mtp")) if force_mtp is None else bool(force_mtp)
    # 依次尝试：按配置 → （MTP 开着就先回退关 MTP）→ 最后若用了 GPU 再降级纯 CPU
    plans: list[tuple[bool, dict]] = [(with_mtp, {})]
    if with_mtp:
        plans.append((False, {}))
    if int(c.get("ngl") or 0) > 0:
        cpu = dict(c)
        cpu["ngl"] = 0
        cpu["ctx"] = min(int(c.get("ctx") or 4096), 4096)
        cpu["threads"] = int(c.get("threads") or 0) or max(4, min(16, (os.cpu_count() or 4) - 1))
        plans.append((False, cpu))

    last_err = ""
    for mtp, over in plans:
        cc = dict(c)
        cc.update(over)
        args = build_args(cc, with_mtp=mtp)
        log.write(("命令: %s %s\n" % (exe, " ".join(args))).encode("utf-8"))
        proc = subprocess.Popen(
            [exe] + args, cwd=(os.path.dirname(exe) or None), stdout=log, stderr=log,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
        ok = wait_ready(port, proc, int(c.get("ready_timeout") or 240))
        if ok:
            note = "已启动"
            if mtp:
                note += "（MTP 投机解码已开）"
            elif with_mtp:
                note += "（MTP 启动失败，已自动回退）"
            if over:
                note += "（GPU 模式未就绪，已自动降级为 CPU 运行，速度会明显变慢）"
            return {"ok": True, "running": True, "pid": proc.pid, "port": port,
                    "exe": exe, "mtp": mtp, "ngl": cc.get("ngl"), "ctx": cc.get("ctx"),
                    "log": log_path, "note": note}
        last_err = "进程 pid=%s 退出码=%s，%.0f 秒内端口 %d 未就绪" % (
            proc.pid, proc.poll(), float(c.get("ready_timeout") or 240), port)
        if proc.poll() is None:
            try:
                proc.terminate()
                time.sleep(1.0)
                if proc.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
    return {"ok": False, "error": "本地模型启动失败：%s。日志见 %s" % (last_err, log_path)}


def stop(port_or_pid=None) -> dict:
    pid = port_or_pid
    if pid is None:
        pid = running_pid(int(DEFAULT_LOCAL["port"]))
    try:
        if isinstance(pid, int) and pid > 0:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)
            return {"ok": True, "stopped": pid}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"ok": False, "error": "本地模型没有在运行（或拿不到 pid）"}


def _exe_hint(c: dict) -> str:
    try:
        return find_exe(str(c.get("llama_dir") or ""))
    except Exception:
        return os.path.join(str(c.get("llama_dir") or ""), "llama-server.exe")


def _pack_hint() -> str:
    """当前用的是哪个自带运行环境包（没有则空串）。"""
    try:
        import runtimes
        for pid in runtimes.installed():
            if runtimes.installed_exe(pid):
                return pid
    except Exception:
        pass
    return ""


def status(c: dict) -> dict:
    c = normalize(c)
    port = int(c["port"])
    info = probe(port, 1.5)
    hw = c.get("_hw") or detect_hardware()
    gpu = hw.get("gpu") if isinstance(hw, dict) else None
    return {
        "ok": True,
        "enabled": c["enabled"],
        "auto": c["auto"],
        "running": bool(info),
        "pid": running_pid(port) if info else None,
        "port": port,
        "exe": _exe_hint(c),
        "runtime_pack": _pack_hint(),
        "config": {k: v for k, v in c.items() if not k.startswith("_")},
        "bundled": os.path.isfile(bundled_paths()["model"]),
        "hardware": {
            "gpu": gpu,
            "ram_mb": hw.get("ram_mb"),
            "cores": hw.get("cores"),
            "mode": hw.get("mode"),
            "tier": c.get("_tier"),
            "note": c.get("_tune_note"),
        },
        "files": {
            "model": os.path.isfile(str(c["model"])),
            "mmproj": os.path.isfile(str(c["mmproj"])),
            "mtp": os.path.isfile(str(c["mtp"])),
        },
        "models": info.get("data") if isinstance(info, dict) else None,
    }
