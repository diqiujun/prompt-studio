# -*- coding: utf-8 -*-
"""运行环境（llama.cpp 二进制）自适应安装。

发行包自带多套 llama.cpp 预编译包（runtime/packs/*.zip），首次启动时：
1. 检测系统（只支持 Windows；Linux / macOS 直接提示不支持）；
2. 检测架构（x64 / arm64）与显卡（NVIDIA 驱动 CUDA 版本 / AMD ROCm / 无独显）；
3. 按检测结果挑一个最合适的包，解压到 runtime/<包 id>/，之后所有本地推理都用它。

包 id 命名：<加速器>-<架构>，例如 cuda-13.5-x64 / cpu-arm64 / rocm-10.0-x64。
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import settings

# --------------------------------------------------------------------------- 包清单
# 与 runtime/packs/ 下的 zip 一一对应；bytes 只用于界面展示。
PACKS = {
    "cuda-13.5-x64": {
        "file": "llama-b12606-bin-win-cuda-13.5-x64.zip",
        "accel": "cuda", "arch": "x64", "cuda_min": 13.5, "version": "b12606",
        "label": "NVIDIA · CUDA 13.5（x64）",
        "note": "最新 CUDA，驱动 ≥ 580 时用",
        "bytes": 225600753,
    },
    "cuda-12.4-x64": {
        "file": "llama-b12671-bin-win-cuda-12.4-x64.zip",
        "accel": "cuda", "arch": "x64", "cuda_min": 12.4, "version": "b12671",
        "label": "NVIDIA · CUDA 12.4（x64）",
        "note": "主流 NVIDIA 驱动（CUDA ≥ 12.4）",
        "bytes": 358130711,
    },
    "cuda-13.5-arm64": {
        "file": "llama-b12671-bin-win-cuda-13.5-arm64.zip",
        "accel": "cuda", "arch": "arm64", "cuda_min": 13.5, "version": "b12671",
        "label": "NVIDIA · CUDA 13.5（arm64）",
        "note": "ARM 版 Windows（如骁龙 X + 独显/虚拟 GPU）",
        "bytes": 213117916,
    },
    "rocm-10.0-x64": {
        "file": "llama-b12671-bin-win-rocm-10.0-x64.zip",
        "accel": "rocm", "arch": "x64", "cuda_min": None, "version": "b12671",
        "label": "AMD · ROCm 10.0（x64）",
        "note": "AMD Radeon 显卡",
        "bytes": 284563704,
    },
    "cpu-x64": {
        "file": "llama-b12671-bin-win-cpu-x64.zip",
        "accel": "cpu", "arch": "x64", "cuda_min": None, "version": "b12671",
        "label": "CPU 通用（x64）",
        "note": "没有可用独显 / 驱动过旧时的兜底，速度较慢",
        "bytes": 25196724,
    },
    "cpu-arm64": {
        "file": "llama-b12671-bin-win-cpu-arm64.zip",
        "accel": "cpu", "arch": "arm64", "cuda_min": None, "version": "b12671",
        "label": "CPU 通用（arm64）",
        "note": "ARM 版 Windows 兜底",
        "bytes": 13278307,
    },
}

EXE_NAME = "llama-server.exe"
_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------- 路径
def app_root() -> Path:
    return settings.app_root()


def runtime_dir() -> Path:
    """解压后的运行环境根目录：<程序目录>/runtime/<包 id>/。"""
    d = app_root() / "runtime"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = settings.data_dir() / "runtime"
        d.mkdir(parents=True, exist_ok=True)
    return d


def packs_dir() -> Path:
    """随发行包分发的 zip 目录。"""
    return app_root() / "runtime" / "packs"


def pack_zip(pid: str) -> Path:
    p = PACKS.get(pid)
    return packs_dir() / p["file"] if p else Path("")


def installed_dir(pid: str) -> Path:
    return runtime_dir() / pid


def installed_exe(pid: str) -> str:
    exe = installed_dir(pid) / EXE_NAME
    return str(exe) if exe.is_file() else ""


def installed() -> list:
    out = []
    for pid in PACKS:
        exe = installed_exe(pid)
        if exe:
            out.append(pid)
    return out


def any_installed_exe(prefer: str = "") -> str:
    if prefer:
        e = installed_exe(prefer)
        if e:
            return e
    for pid in installed():
        return installed_exe(pid)
    return ""


# --------------------------------------------------------------------------- 硬件检测
def _ps(cmd: str, timeout: int = 12) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, timeout=timeout,
                           creationflags=_NO_WINDOW,
                           encoding="mbcs", errors="ignore")
        return (r.stdout or "").strip()
    except Exception:
        return ""


def detect_arch() -> str:
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


def detect_nvidia() -> dict:
    """返回 {present, name, vram_mb, cuda}；cuda 是驱动支持的最高 CUDA 版本。"""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, timeout=12, creationflags=_NO_WINDOW,
                           encoding="mbcs", errors="ignore")
        txt = (r.stdout or "").strip()
        if r.returncode != 0 or not txt:
            return {"present": False}
        first = txt.splitlines()[0]
        parts = [x.strip() for x in first.split(",")]
        cuda = 0.0
        try:
            r2 = subprocess.run(["nvidia-smi"], capture_output=True, timeout=12,
                                creationflags=_NO_WINDOW, encoding="mbcs", errors="ignore")
            m = re.search(r"CUDA\s+(?:UMD\s+)?Version:\s*([\d.]+)", r2.stdout or "")
            if not m:
                m = re.search(r"CUDA\s+Version:\s*([\d.]+)", r2.stdout or "")
            if m:
                cuda = float(m.group(1))
        except Exception:
            pass
        return {"present": True, "name": parts[0], "vram_mb": int(float(parts[1])) if len(parts) > 1 and parts[1].isdigit() else 0,
                "cuda": cuda}
    except Exception:
        return {"present": False}


def detect_amd() -> dict:
    names = _ps("(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ';'")
    low = names.lower()
    present = ("amd" in low or "radeon" in low) and "nvidia" not in low
    rocm = False
    if present:
        cands = [Path(r"C:\Program Files\AMD\ROCm"), Path(r"C:\Program Files\AMD\ROCm\bin")]
        rocm = any(c.exists() for c in cands) or bool(list(Path(r"C:\Windows\System32").glob("amdhip64*.dll")))
    return {"present": present, "name": names[:120], "rocm": rocm}


def detect() -> dict:
    is_win = (os.name == "nt")
    arch = detect_arch()
    nv = detect_nvidia()
    amd = detect_amd() if is_win else {"present": False}
    return {
        "os": "windows" if is_win else ("linux" if sys.platform.startswith("linux") else
                                        ("macos" if sys.platform == "darwin" else sys.platform)),
        "windows": is_win,
        "arch": arch,
        "nvidia": nv,
        "amd": amd,
        "cuda": float(nv.get("cuda") or 0.0),
        "cpus": os.cpu_count() or 0,
    }


def choose(det: dict | None = None) -> list:
    """按硬件给出候选包 id（按优先级）。空列表 = 该环境无法适配。"""
    det = det or detect()
    if not det.get("windows"):
        return []
    arch = det.get("arch") or "x64"
    out = []
    nv = det.get("nvidia") or {}
    amd = det.get("amd") or {}
    if nv.get("present"):
        for pid, p in PACKS.items():
            if p["accel"] == "cuda" and p["arch"] == arch and det.get("cuda", 0) >= (p["cuda_min"] or 0):
                out.append(pid)
        # 版本新的优先（b12606 / b12671 等按 cuda_min 降序）
        out.sort(key=lambda i: PACKS[i]["cuda_min"] or 0, reverse=True)
    if amd.get("present") and arch == "x64":
        out.append("rocm-10.0-x64")
    out.append("cpu-" + arch)
    # 去重保序
    seen, res = set(), []
    for i in out:
        if i in PACKS and i not in seen:
            seen.add(i)
            res.append(i)
    return res


# --------------------------------------------------------------------------- 安装
def install(pid: str) -> dict:
    """解压指定包到 runtime/<pid>/，返回 {ok, exe, error}。"""
    p = PACKS.get(pid)
    if not p:
        return {"ok": False, "error": "未知的运行环境包：%s" % pid}
    z = pack_zip(pid)
    if not z.is_file():
        return {"ok": False, "error": "发行包里缺少 %s（应位于 runtime\\packs\\）" % p["file"]}
    target = installed_dir(pid)
    tmp = target.with_name(pid + ".tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(tmp)
        if not (tmp / EXE_NAME).is_file():
            sub = [x for x in tmp.rglob(EXE_NAME)]
            if not sub:
                shutil.rmtree(tmp, ignore_errors=True)
                return {"ok": False, "error": "包里没有 %s" % EXE_NAME}
            src = sub[0].parent
            for item in src.iterdir():
                shutil.move(str(item), str(tmp / item.name))
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        exe = installed_exe(pid)
        if not exe:
            return {"ok": False, "error": "解压后仍找不到 %s" % EXE_NAME}
        return {"ok": True, "exe": exe, "dir": str(target), "pack": pid}
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def ensure(prefer: str = "") -> dict:
    """首次启动用：已装就直接用；没装就按硬件装最合适的那个。"""
    det = detect()
    if not det["windows"]:
        return {"ok": False, "unsupported": True,
                "error": "本软件只支持 Windows（当前系统：%s）。Linux / macOS 无法适配。" % det["os"],
                "detect": det}
    if prefer and installed_exe(prefer):
        return {"ok": True, "pack": prefer, "exe": installed_exe(prefer), "detect": det, "reused": True}
    cands = choose(det)
    for pid in cands:
        if installed_exe(pid):
            return {"ok": True, "pack": pid, "exe": installed_exe(pid), "detect": det, "reused": True}
    errs = []
    for pid in cands:
        r = install(pid)
        if r.get("ok"):
            r["detect"] = det
            r["candidates"] = cands
            return r
        errs.append("%s：%s" % (pid, r.get("error")))
    return {"ok": False, "detect": det, "candidates": cands,
            "error": "没有可用的运行环境包。\n" + "\n".join(errs)}


def status() -> dict:
    det = detect()
    cands = choose(det)
    packs = []
    for pid, p in PACKS.items():
        packs.append({
            "id": pid, "label": p["label"], "note": p["note"], "version": p["version"],
            "bytes": p["bytes"], "arch": p["arch"], "accel": p["accel"],
            "hidden": pid not in cands, "installed": bool(installed_exe(pid)),
            "zip_ok": pack_zip(pid).is_file(),
        })
    return {
        "ok": True, "detect": det, "candidates": cands,
        "preferred": cands[0] if cands else "",
        "installed": installed(),
        "dir": str(runtime_dir()), "packs_dir": str(packs_dir()),
        "supported": bool(cands),
        "packs": packs,
        "message": "" if cands else "本软件只支持 Windows（当前系统：%s）。" % det["os"],
    }


def verify(pid: str) -> dict:
    """跑 llama-server --version，确认这套二进制在本机能起来。"""
    exe = installed_exe(pid)
    if not exe:
        return {"ok": False, "error": "还没安装 %s" % pid}
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=40,
                           creationflags=_NO_WINDOW, encoding="mbcs", errors="ignore")
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return {"ok": r.returncode == 0, "code": r.returncode, "output": out[-500:]}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


if __name__ == "__main__":
    import json
    print(json.dumps(status(), ensure_ascii=False, indent=2))
    print("choose:", choose())
