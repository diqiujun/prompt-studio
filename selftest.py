"""自检：模块导入、模板拼装体积、JSON 抽取。运行 python selftest.py"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import llm
import registry
import settings

print("config:", settings.CONFIG_PATH)
print("resource_root:", settings.resource_root())
print("templates:", len(registry.catalog()))

cases = {
    "h3_video": {"mode": "Ref2VA", "duration": 6, "aspect": "16:9", "subject_kind": "人物特写",
                 "lang": "中文", "content": "沈不违提刀立于雪夜山门，镜头从靴子上摇到脸，台词「都让开」。"},
    "qwen_i2i": {"ratio": "9:16", "content": "把钟改成完整无缺，只留一道竖直长裂缝，其余不变。"},
    "moss_t2i": {"canvas": "864x1536", "style_pref": "3D 仙侠渲染", "scene_tags": "古风室内, 带文字海报",
                 "lang": "中文", "content": "女修立于丹殿废墟，手捧发光丹炉残件。"},
    "zt_t2i": {"canvas": "1024x1536", "style_pref": "新中式时尚", "content": "墨绿缎面旗袍，月下回廊，提纸灯笼。"},
    "zi_i2i": {"intent": "洗图提质", "content": "构图人物不动，只提升光影质感，加冷青色调。"},
    "tr_general": {"direction": "zh2en", "register": "正式书面", "glossary": "沈不违=Shen Buwei", "content": "他胸口有把剑。"},
    "tr_prompt": {"direction": "zh2en", "content": "subject_definitions:\n<Subject 1> 青年男子\nsummary:\n[reference generation] 他走进山门。"},
}
for tid, params in cases.items():
    for fast in (True, False):
        imgs = [{"data_url": "data:image/png;base64,AAA", "role": "人物身份图"}] if tid in ("h3_video", "qwen_i2i", "zi_i2i") else []
        out = registry.build(tid, params, imgs, fast)
        miss = [p for p in ("system", "user") if not out.get(p)]
        print(f"{tid:12s} fast={fast!s:5s} sys={len(out['system']):6d} user={len(out['user']):5d} json={out['expect_json']}{'  MISS:'+str(miss) if miss else ''}")

# 规范文件是否都读到了（空文件=复制失败）
stats = registry.template_stats()
empty = [s["name"] for s in stats if s["bytes"] < 40]
print("spec files:", len(stats), "empty/too-small:", empty)

# llm 工具函数
print("normalize:", llm.normalize_base("https://api.deepseek.com"), llm.normalize_base("http://127.0.0.1:1234/v1/"))
print("extract_json:", bool(llm.extract_json('```json\n{"rewritten_prompt":"x","wh_ratio":"","ratio_follow":"<image1>"}\n```')))
print("extract_json raw:", bool(llm.extract_json('前置说明\n{"positive_prompt":"a","slots":{"subject":"x"}}\n尾注')))
print("content with images:", json.dumps(llm.build_user_content("hi", [{"data_url": "data:image/png;base64,AAA"}]))[:90])
print("OK selftest")
