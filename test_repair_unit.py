# -*- coding: utf-8 -*-
"""直接测 app._repair_h3：喂一段故意缺 <d> 与 [Shot 1] 的 H3 文本，看能否补回来。

用法：python test_repair_unit.py（需要本地模型已在 8910 运行）
日志：data/repair_unit.log
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import app as A  # noqa: E402
import localsrv  # noqa: E402
import settings  # noqa: E402

LOG = os.path.join(ROOT, "data", "repair_unit.log")


def log(m):
    print(m, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(m) + "\n")


BAD = """【模式判定】T2VA
subject_definitions:
沈不违，青年刀客
summary:
沈不违站在雪夜山门前，最后他开口说“都让开”。
retention_analysis:
N/A
detailed_description:
镜头从靴子上摇到脸，他冷冷地说“都让开”。
overall_soundscape: 风雪声与刀刃轻响
"""


def main():
    open(LOG, "w", encoding="utf-8").close()
    cfg = settings.load_config()
    p = settings.get_provider(cfg, "local-gemma")
    if not p:
        log("[FAIL] 没有 local-gemma provider")
        return 1
    c = localsrv.normalize(cfg.get("local") or {})
    st = localsrv.start(c, os.path.join(ROOT, "data", "llama.log"))
    log("本地模型：ok=%s %s" % (st.get("ok"), st.get("note") or st.get("error")))
    if not st.get("ok"):
        return 1
    miss = A._h3_missing(BAD)
    log("修补前缺项：%s" % "、".join(miss))
    if not miss:
        log("[FAIL] 构造的样本没被判定为缺项")
        return 1
    fixed, note = A._repair_h3(p, BAD, True)
    if not fixed:
        raw = A.llm.chat(
            p,
            system="你是 MiniMax H3 提示词的格式校对器。只做格式修补，不改写内容，只输出修补后的完整提示词。",
            user_text="给下面这份 H3 提示词补上缺失的字段名与台词标签 <d>，只输出完整提示词：\n\n" + BAD,
            fast=True,
            temperature=0.2,
        )
        log("直连模型返回：ok=%s err=%s" % (raw.get("ok"), str(raw.get("error"))[:300]))
        log("模型原文：%s" % str(raw.get("content"))[:800])
        log("[FAIL] 修补失败（模型没返回有效修补）")
        return 1
    after = A._h3_missing(fixed)
    log("修补后缺项：%s" % ("、".join(after) or "无"))
    log("note=%r" % note)
    log("---- 修补结果 ----")
    log(fixed[:1200])
    ok = len(after) < len(miss) and "<d>" in fixed
    log("[%s] 修补判定" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
