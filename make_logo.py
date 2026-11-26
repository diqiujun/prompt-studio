"""生成 PromptStudio 的 logo（黑底白字：左半大写 P，右半小写 m）。

用法：python make_logo.py
产出：
  static\\logo.png      512×512，界面与窗口图标用（随 static 目录一起打包）
  build\\app.png        1024×1024，母版
  build\\app.ico        16–256 多尺寸，exe 图标

设计约束（用户口径）：纯黑背景、纯白字形；大写 P 占画面左二分之一，小写 m 占右二分之一；
字形各自撑满所在半区（留 6% 边距），不描边、不投影、不加任何装饰。
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\seguibl.ttf",   # Segoe UI Black
    r"C:\Windows\Fonts\arialbd.ttf",   # Arial Bold
    r"C:\Windows\Fonts\segoeuib.ttf",  # Segoe UI Bold
]
SIZE = 1024
BG = (0, 0, 0, 255)
FG = (255, 255, 255, 255)
PAD_RATIO = 0.06       # 每半区的内边距比例


def pick_font():
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise SystemExit("找不到可用字体（seguibl.ttf / arialbd.ttf / segoeuib.ttf）")


def glyph_mask(ch, box_w, box_h, font_path):
    """把单个字形渲染成刚好填满 box_w×box_h 的白色蒙版（保持原始字形比例）。"""
    probe = 400
    font = ImageFont.truetype(font_path, probe)
    l, t, r, b = font.getbbox(ch)
    gw, gh = max(1, r - l), max(1, b - t)
    scale = min(box_w / gw, box_h / gh)
    size = max(8, int(round(probe * scale)))
    font = ImageFont.truetype(font_path, size)
    l, t, r, b = font.getbbox(ch)
    gw, gh = max(1, r - l), max(1, b - t)
    tile = Image.new("L", (gw, gh), 0)
    ImageDraw.Draw(tile).text((-l, -t), ch, font=font, fill=255)
    return tile


def build(size=SIZE):
    """P 与 m 共用基线，整组在画布中垂直居中：P 撑满左半宽，m 撑满右半宽。"""
    font_path = pick_font()
    half = size // 2
    pad = int(size * PAD_RATIO)
    bw = half - pad * 2          # 每半可用的横向宽度

    # 先按「半宽」把两个字各自放到最大（保持字形比例），再让 m 用 P 的基线
    mask_p = glyph_mask("P", bw, size, font_path)
    mask_m = glyph_mask("m", bw, size, font_path)
    group_h = mask_p.height                       # 以 P 的高度为整组高度
    top = (size - group_h) // 2                   # 整组垂直居中
    base = top + mask_p.height                    # 基线 = P 的底边

    img = Image.new("RGBA", (size, size), BG)
    for mask, x0 in ((mask_p, 0), (mask_m, half)):
        px = x0 + (half - mask.width) // 2
        py = base - mask.height                   # 与 P 共基线
        img.paste(Image.new("RGBA", mask.size, FG), (px, py), mask)
    return img


def main():
    master = build(SIZE)
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "static"), exist_ok=True)
    master.save(os.path.join(ROOT, "build", "app.png"))
    master.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "static", "logo.png"))
    # 窗口/界面上的小尺寸也放一份 256，避免高分屏下放大小图
    master.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "static", "logo-256.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master.resize((256, 256), Image.LANCZOS).save(
        os.path.join(ROOT, "build", "app.ico"), format="ICO", sizes=[(s, s) for s in sizes])
    for name in ("build/app.png", "build/app.ico", "static/logo.png", "static/logo-256.png"):
        p = os.path.join(ROOT, name.replace("/", os.sep))
        print("%-22s %8d B" % (name, os.path.getsize(p)))


if __name__ == "__main__":
    main()
