# -*- coding: utf-8 -*-
"""把 ComfyUI 的「UI 格式」工作流（nodes/links/widgets_values）转成 API 格式（id -> {class_type, inputs}）。

只用于本地回归测试：官方 example_workflows 只有 UI 格式，而插件要吃 API 格式。
节点 widget 顺序来自节点源码（ComfyUI_MiniMaxH3_Director-main/nodes/director_common.py），
覆盖不到的节点类型只保留连线输入，widget 值按位置存成 w0..wn（detect 不依赖它们）。
"""
import json
import os
import sys

# 各节点 widgets_values 的顺序（按源码 INPUT_TYPES 的 required 字段顺序，含 control_after_generate）
WIDGET_MAP = {
    "MiniMaxH3Director": [
        "task_type", "global_prompt", "bd_grp_sample", "cfg", "seed",
        "control_after_generate", "frame_rate", "width", "height",
        "ref_max_size", "total_frames", "timeline_data",
        "bd_grp_advanced", "steps", "sampler", "scheduler", "shift_video", "shift_audio",
        "bd_grp_perf", "clear_vram_between_segments", "clear_vram_before_refine",
        "clear_vram_before_face_refine", "cache_frames_codec", "export_source_images",
        "export_pre_face_refine", "cache_name",
    ],
    "MiniMaxH3DirectorGroupImageToVideo": ["prompt", "duration_sec"],
    "MiniMaxH3DirectorGroupReferenceToVideo": ["prompt", "duration_sec"],
    "MiniMaxH3DirectorGroupsCombine": [],
    "LoadImage": ["image", "upload"],
    "VHS_LoadVideo": ["video", "force_rate", "custom_width", "custom_height",
                      "frame_load_cap", "skip_first_frames", "select_every_nth",
                      "format", "videopreview"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CLIPLoader": ["clip_name", "type", "device"],
    "VAELoader": ["vae_name"],
    "LoraLoaderModelOnly": ["lora_name", "strength_model"],
    "CreateVideo": ["fps"],
    "SaveVideo": ["filename_prefix", "format", "codec"],
    "PreviewAny": ["preview"],
    "BasicScheduler": ["scheduler", "steps", "denoise"],
    "MiniMaxH3DirectorRefine": ["enabled", "scale"],
}


def _links_map(doc):
    out = {}
    for ln in doc.get("links") or []:
        if isinstance(ln, list) and len(ln) >= 5:
            out[ln[0]] = (str(ln[1]), ln[2])
        elif isinstance(ln, dict):
            out[ln.get("id")] = (str(ln.get("origin_id")), ln.get("origin_slot"))
    return out


def convert(doc):
    """UI 格式 doc -> API 格式 dict。"""
    nodes = doc.get("nodes") or []
    links = _links_map(doc)
    api = {}
    for n in nodes:
        nid = str(n.get("id"))
        cls = n.get("type") or ""
        if cls in ("MarkdownNote", "Note"):
            continue
        inputs = {}
        for slot, idx in enumerate(n.get("inputs") or []):
            lid = (n.get("inputs") or [])[slot].get("link")
            if lid is None or lid not in links:
                continue
            src = links[lid]
            name = (n.get("inputs") or [])[slot].get("name") or "in%d" % slot
            inputs[name] = [src[0], src[1]]
        wv = n.get("widgets_values")
        names = WIDGET_MAP.get(cls)
        if isinstance(wv, list) and names:
            for i, v in enumerate(wv[:len(names)]):
                if names[i] and names[i] not in inputs:
                    inputs[names[i]] = v
        elif isinstance(wv, list):
            for i, v in enumerate(wv):
                inputs["w%d" % i] = v
        elif isinstance(wv, dict):
            # 有些节点（如 Director 的某些版本）widgets_values 是 dict
            for k, v in wv.items():
                inputs.setdefault(k, v)
        api[nid] = {"class_type": cls, "inputs": inputs, "_meta": {"title": n.get("title") or cls}}
    return api


def main(argv):
    if len(argv) < 2:
        print("用法: python tools\\ui2api.py <ui.json|目录> [输出目录]")
        return 2
    src = argv[1]
    out_dir = argv[2] if len(argv) > 2 else os.path.join("work", "workflows", "dir_api")
    os.makedirs(out_dir, exist_ok=True)
    files = []
    if os.path.isdir(src):
        files = [os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".json")]
    else:
        files = [src]
    for p in files:
        doc = json.load(open(p, encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("nodes"):
            api = convert(doc)
        else:
            print("[跳过] 已经是 API 格式：%s" % os.path.basename(p))
            continue
        name = os.path.splitext(os.path.basename(p))[0] + "_api.json"
        dst = os.path.join(out_dir, name)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(api, f, ensure_ascii=False, indent=1)
        print("[OK] %s -> %s（%d 节点）" % (os.path.basename(p), dst, len(api)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
