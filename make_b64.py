"""生成 data/probe_img_b64.txt：把参考图缩到 760px JPEG 并存成 data_url 文本。"""
import base64
import io
import os

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "..", "work", "storyboard_q", "R04_A5.png")
im = Image.open(SRC).convert("RGB")
im.thumbnail((760, 760))
buf = io.BytesIO()
im.save(buf, format="JPEG", quality=87)
b64 = base64.b64encode(buf.getvalue()).decode()
data_url = "data:image/jpeg;base64," + b64
open(os.path.join(ROOT, "data", "probe_img_b64.txt"), "w", encoding="utf-8").write(data_url)
print("src:", SRC, "size:", im.size, "b64 chars:", len(b64))
