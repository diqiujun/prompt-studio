# -*- coding: utf-8 -*-
"""把 ai-pose-gallery-zh 的姿势库导入 PromptStudio。

源：ai-pose-gallery-zh-main.zip（data/pose-zh.json + thumbs/<id>.jpg + img/<id>.png + img/depth/ + thumbs/depth/）
目标：<项目>/plugins/pose_gallery/data/（姿势库插件的自带数据目录）
    index.json          姿势索引（含中英提示词、筛选项）
    thumbs/<id>.jpg     列表缩略图（原样搬）
    refs/<id>.jpg       参考图（原图缩到长边 1024、JPEG q86）
    depth/thumbs/<id>.jpg
    depth/refs/<id>.jpg

用法：python tools\import_gallery.py [zip 路径]
"""
import io
import json
import os
import sys
import zipfile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "plugins", "pose_gallery", "data")
PREFIX = "ai-pose-gallery-zh-main/"
REF_MAX = 1024
REF_Q = 86
DEPTH_THUMB_MAX = 384

DEFAULT_ZIP = os.path.join(os.path.expanduser("~"), ".dsh", "attachments", "v1", "files",
                           "82", "826e5bab3270003bff1e15bbfb9711d261cad86d4460c030fcbeebaa0cf55eab",
                           "ai-pose-gallery-zh-main.zip")


def norm_name(p):
    return p[len(PREFIX):] if p.startswith(PREFIX) else p


def _first(names, stem, exts):
    """在 zip 里找第一个存在的 <stem><ext>，返回带 PREFIX 的完整条目名。"""
    for ext in exts:
        cand = PREFIX + stem + ext
        if cand in names:
            return cand
    return None


def to_jpeg(raw, max_side=REF_MAX, q=REF_Q):
    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_side:
        k = max_side / float(max(w, h))
        im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, optimize=True)
    return buf.getvalue()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ZIP
    if not os.path.isfile(src):
        print("找不到源包：", src)
        return 1
    for d in ("", "thumbs", "refs", "depth/thumbs", "depth/refs"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)

    z = zipfile.ZipFile(src)
    poses = json.loads(z.read(PREFIX + "data/pose-zh.json").decode("utf-8"))
    print("姿势条目：", len(poses))
    names = set(z.namelist())

    index = []
    ok = skip = 0
    for n, it in enumerate(poses, 1):
        pid = it.get("id") or ""
        thumb = norm_name(it.get("缩略图") or "")
        full = norm_name(it.get("原图") or "")
        rec = {
            "id": pid,
            "name": it.get("姿势名称") or "",
            "no": it.get("姿势编号") or "",
            "system": it.get("体系") or "",
            "cat": it.get("分类") or "",
            "angle": it.get("角度") or "",
            "sfw": "性感" not in (it.get("体系") or ""),
            "zh": "%s视角，动作：%s（%s·%s）" % (it.get("角度") or "正面", it.get("姿势名称") or "标准姿势",
                                          it.get("体系") or "", it.get("分类") or ""),
            "en": "%s view, pose: %s (%s)" % (it.get("角度") or "front", it.get("姿势名称") or "standard pose",
                                             it.get("分类") or ""),
            "has_depth": bool(_first(names, "thumbs/depth/" + pid, (".jpg", ".jpeg", ".webp", ".png"))
                              or _first(names, "img/depth/" + pid, (".webp", ".png", ".jpg", ".jpeg"))),
        }
        # 缩略图
        try:
            if thumb and PREFIX + thumb in names:
                data = z.read(PREFIX + thumb)
                with open(os.path.join(OUT, "thumbs", pid + os.path.splitext(thumb)[1].lower()), "wb") as f:
                    f.write(data)
                rec["thumb"] = "thumbs/" + pid + os.path.splitext(thumb)[1].lower()
        except Exception as e:
            print("缩略图失败", pid, e)

        # 参考图（缩到 1024 JPEG）
        try:
            if full and PREFIX + full in names:
                with open(os.path.join(OUT, "refs", pid + ".jpg"), "wb") as f:
                    f.write(to_jpeg(z.read(PREFIX + full)))
                rec["ref"] = "refs/" + pid + ".jpg"
        except Exception as e:
            print("参考图失败", pid, e)

        # 深度图（源包多为 webp：thumbs/depth/<id>.webp、img/depth/<id>.webp）
        try:
            dt = _first(names, "thumbs/depth/" + pid, (".jpg", ".jpeg", ".webp", ".png"))
            df = _first(names, "img/depth/" + pid, (".webp", ".png", ".jpg", ".jpeg"))
            if dt:
                with open(os.path.join(OUT, "depth", "thumbs", pid + ".jpg"), "wb") as f:
                    f.write(to_jpeg(z.read(dt), max_side=DEPTH_THUMB_MAX, q=REF_Q))
                rec["depth_thumb"] = "depth/thumbs/" + pid + ".jpg"
            if df:
                with open(os.path.join(OUT, "depth", "refs", pid + ".jpg"), "wb") as f:
                    f.write(to_jpeg(z.read(df), max_side=REF_MAX, q=REF_Q))
                rec["depth_ref"] = "depth/refs/" + pid + ".jpg"
            rec["has_depth"] = bool(dt or df)
        except Exception as e:
            print("深度图失败", pid, e)

        if rec.get("thumb") and rec.get("ref"):
            index.append(rec)
            ok += 1
        else:
            skip += 1
        if n % 100 == 0:
            print("... %d/%d" % (n, len(poses)))

    meta = {
        "source": "ai-pose-gallery-zh (Anhao) · 姿势库",
        "license": "仅供个人学习与合法创作；版权归原作者 ギア(@giaaibusi)",
        "count": len(index),
        "systems": sorted({r["system"] for r in index}),
        "cats": sorted({r["cat"] for r in index}),
        "angles": sorted({r["angle"] for r in index}),
        "default_hide_nsfw": True,
    }
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": index}, f, ensure_ascii=False, separators=(",", ":"))

    total = 0
    for base, _dirs, files in os.walk(OUT):
        for fn in files:
            total += os.path.getsize(os.path.join(base, fn))
    print("完成：%d 条（跳过 %d）· gallery/pose 共 %.1f MB" % (ok, skip, total / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
