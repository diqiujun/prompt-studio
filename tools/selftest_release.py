"""临时自测：验证 release_pack.split_file 切分与合并后字节完全一致。"""
import hashlib
import io
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import release_pack as R  # noqa: E402

tmp = ROOT / "data" / "_reltest"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

blob = os.urandom(3 * 1024 * 1024 + 12345)
src = tmp / "Fake.payload.zip"
src.write_bytes(blob)

R.OUT = tmp
parts = R.split_file(src, 1024 * 1024, "Fake.payload.zip")

merged = tmp / "merged.zip"
with io.open(merged, "wb") as g:
    for p in parts:
        g.write(p.read_bytes())

print("parts:", [p.name for p in parts])
print("orig  sha:", hashlib.sha256(blob).hexdigest()[:16])
print("merge sha:", hashlib.sha256(merged.read_bytes()).hexdigest()[:16])
print("MATCH:", merged.read_bytes() == blob)
shutil.rmtree(tmp, ignore_errors=True)
