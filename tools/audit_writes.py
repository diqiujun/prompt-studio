# -*- coding: utf-8 -*-
r"""审计「插件写回点是否真的生效」：对每个工作流，检查 detect 认出的槽
（提示词 / 负向 / 分辨率 / 时长 / 参考图 / 模型 / LoRA）是否位于采样器实际会走的上游链上。

判断方法：从采样器（KSampler / SamplerCustom / MiniMaxH3Director …）的关键输入出发做上游闭包；
遇到 ComfySwitchNode 只走 switch 当前值对应的分支（on_true 或 on_false）。
落不在闭包里的槽 = 写了也不生效（被开关旁路 / 断链 / 未被任何节点消费）。

用法：python tools\audit_writes.py [样本.json ...]
      不带参数时扫 work\workflows\ 与 work\workflows\dir_api\ 下的全部样本。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugins", "comfy_runner"))

try:
    import plugin  # noqa: E402
except Exception as exc:  # pragma: no cover
    print("导入插件失败：%s" % exc)
    raise SystemExit(2)

SAMPLERS = (
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
    "FluxGuidance", "BasicGuider",
)
# 导演台这类「自带采样」的执行器节点：槽就写在它身上，本身就是生效点
EXECUTORS = ("MiniMaxH3Director",)
OUTPUTS = (
    "SaveImage", "SaveImageAdvanced", "SaveVideo", "SaveAnimatedWEBP", "SaveWEBM",
    "PreviewImage", "PreviewAny", "VHS_VideoCombine", "CreateVideo",
)
# 采样器上「上游链」的入口字段
CHAIN_INPUTS = (
    "positive", "negative", "latent_image", "model", "samples", "pixels",
    "vae", "clip", "guider", "images", "image", "text", "prompt", "timeline_data",
)


def is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], (int, float))


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return False


def switch_pick(node):
    """ComfySwitchNode：按 switch 当前值返回唯一可走的那条引用。"""
    ins = node.get("inputs", {})
    on = ins.get("switch")
    t = ins.get("on_true")
    f = ins.get("on_false")
    if on is None:
        return [t, f]
    return [t] if truthy(on) else [f]


def upstream(graph, starts):
    """从若干 [id, slot] 出发，返回可达节点 id 集合（含 switch 的分支裁剪）。"""
    seen_nodes, seen_slots, stack = set(), set(), list(starts)
    while stack:
        cur = stack.pop()
        if not is_link(cur):
            continue
        nid, slot = cur[0], int(cur[1])
        key = (nid, slot)
        if key in seen_slots:
            continue
        seen_slots.add(key)
        node = graph.get(nid)
        if not node:
            continue
        seen_nodes.add(nid)
        cls = str(node.get("class_type", ""))
        ins = node.get("inputs", {})
        if "Switch" in cls or "switch" in cls:
            refs = switch_pick(node)
            for r in refs:
                if is_link(r):
                    stack.append(r)
            continue
        for k, v in ins.items():
            if is_link(v):
                stack.append(v)
    return seen_nodes


def collect(graph):
    """返回 {角色: set(节点id)}，角色 = 该槽写到哪个节点上才算「在链上」。"""
    chains = {"positive": set(), "negative": set(), "latent": set(), "model": set(),
              "any": set(), "exec": set()}
    for nid, node in graph.items():
        cls = str(node.get("class_type", ""))
        if any(cls.startswith(s) for s in EXECUTORS):
            chains["exec"].add(nid)
        if any(cls.startswith(s) for s in OUTPUTS):
            ins = node.get("inputs", {})
            chains["any"] |= upstream(graph, [v for v in ins.values() if is_link(v)])
        if not any(cls.startswith(s) for s in SAMPLERS):
            continue
        ins = node.get("inputs", {})
        for field, role in (
            ("positive", "positive"), ("negative", "negative"),
            ("latent_image", "latent"), ("samples", "latent"), ("pixels", "latent"),
            ("model", "model"),
        ):
            v = ins.get(field)
            if is_link(v):
                chains[role] |= upstream(graph, [v])
        # 整体闭包（用于「只要被任何生效节点消费就算在用」这类软判据）
        allrefs = [v for v in ins.values() if is_link(v)]
        chains["any"] |= upstream(graph, allrefs)
    chains["all"] = chains["positive"] | chains["negative"] | chains["latent"] | chains["model"] | chains["any"]
    return chains


def audit(path):
    graph = json.loads(io.open(path, encoding="utf-8-sig").read())
    if not isinstance(graph, dict) or "nodes" in graph:
        return None
    d = plugin.detect(graph)
    ch = collect(graph)
    rows = []

    def mark(label, nid, roles, sw=None):
        if not nid:
            return
        nid = str(nid)
        hit = nid in ch.get("exec", set()) or any(nid in ch.get(r, set()) for r in roles)
        if not hit and isinstance(sw, dict) and sw.get("on") is False:
            # 被开关旁路，但生成时插件会自动打开 → 视为生效
            label = label + "（生成时自动开开关 %s）" % sw.get("node")
            hit = True
        rows.append((label, nid, hit))

    p = d.get("prompt") or {}
    mark("提示词", p.get("node"), ("positive", "all"), p.get("switch"))
    n = d.get("negative") or {}
    mark("负向", n.get("node") if isinstance(n, dict) else None, ("negative", "all"))
    sz = d.get("size") or {}
    if sz.get("node"):
        mark("分辨率", sz.get("node"), ("latent", "all"), sz.get("switch"))
    ln = d.get("length") or {}
    if ln.get("node"):
        mark("时长", ln.get("node"), ("all",))
    for i, r in enumerate(d.get("refs") or []):
        if r.get("node"):
            mark("参考图%d" % (i + 1), r.get("node"), ("all",))
    for m in d.get("models") or []:
        # PE 模型这类只挂在被旁路文本链上的节点：提示词开关打开后就会用到
        mark("模型·%s" % m.get("field"), m.get("node"), ("model", "all"), p.get("switch"))
    for l in d.get("loras") or []:
        mark("LoRA", l.get("node"), ("model", "all"))

    sw = (d.get("prompt") or {}).get("switch") or {}
    sw_hint = ("（生成时插件会自动打开开关 %s）" % sw.get("node")) if sw.get("on") is False else ""
    if sw_hint:
        rows = [(lb + sw_hint if lb == "提示词" else lb, nid, hit) for lb, nid, hit in rows]
    return d, rows


def main(argv):
    if argv:
        files = [os.path.abspath(a) for a in argv]
    else:
        files = []
        for sub in ("workflows", os.path.join("workflows", "dir_api")):
            base = os.path.join(ROOT, "..", "work", sub) if False else os.path.join(
                os.path.dirname(ROOT), "work", sub)
            if os.path.isdir(base):
                for fn in sorted(os.listdir(base)):
                    if fn.lower().endswith(".json"):
                        files.append(os.path.join(base, fn))
    bad_total = 0
    for f in files:
        try:
            got = audit(f)
        except Exception as exc:
            print("[跳过] %s：%s" % (os.path.basename(f), exc))
            continue
        if not got:
            print("[跳过] %s：不是 API 格式" % os.path.basename(f))
            continue
        d, rows = got
        bad = [r for r in rows if not r[2]]
        bad_total += len(bad)
        print("\n=== %s" % os.path.basename(f))
        print("    类型 %s / 模式 %s / 节点 %s" % (d.get("kind"), d.get("mode"), d.get("nodes")))
        if not rows:
            print("    （没有可写槽）")
            continue
        for label, nid, hit in rows:
            print("    %s %-14s → 节点 %-8s" % ("OK " if hit else "！ ", label, nid))
        if bad:
            print("    ⚠ 有 %d 个槽不在生效链上：%s" % (len(bad), "、".join("%s(%s)" % (b[0], b[1]) for b in bad)))
    print("\n合计不在链上的槽：%d" % bad_total)
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
