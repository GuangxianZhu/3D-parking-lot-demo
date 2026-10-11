"""中文字体和简单富文本。

Panda3D 自带的默认字体只有英文字母，中文会显示成方块，所以必须给它一个中文字体。
优先用仓库 fonts/ 里自带的思源黑体（Noto Sans SC）子集，这样不依赖系统装了什么字体；
自带字体读不到时，才去系统里找。
等宽字体用来画状态图和对比表：状态图是用空格对齐的，比例字体会对不齐。
"""
import os
import re
import sys

from panda3d.core import (DynamicTextFont, Filename, TextNode, TextProperties, TextPropertiesManager,
                          VirtualFileMountRamdisk, VirtualFileSystem)

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(os.path.dirname(HERE), "fonts")
WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# (文件, TTC 里的第几个字体)。按顺序找，第一个能显示中文的就用。
UI_FONTS = [
    (os.path.join(BUNDLED, "NotoSansSC-Regular.otf"), 0),   # 随仓库自带
    (os.path.join(WIN_FONTS, "msyh.ttc"), 0),        # 微软雅黑
    (os.path.join(WIN_FONTS, "msyh.ttf"), 0),
    (os.path.join(WIN_FONTS, "simhei.ttf"), 0),      # 黑体
    (os.path.join(WIN_FONTS, "simsun.ttc"), 0),      # 宋体
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
]
# 粗体：只用于标题和强调。找不到就只用颜色强调
BOLD_FONTS = [
    (os.path.join(BUNDLED, "NotoSansSC-Bold.otf"), 0),
    (os.path.join(WIN_FONTS, "msyhbd.ttc"), 0),      # 微软雅黑 粗体
    (os.path.join(WIN_FONTS, "msyhbd.ttf"), 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
]
# 等宽：英文半角、汉字正好两个半角宽
MONO_FONTS = [
    (os.path.join(BUNDLED, "NotoSansMonoCJKsc-Regular.otf"), 0),
    (os.path.join(WIN_FONTS, "simsun.ttc"), 1),      # 新宋体 NSimSun
    (os.path.join(WIN_FONTS, "simhei.ttf"), 0),      # 黑体本身就是等宽的
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 7),   # Noto Sans Mono CJK SC
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 1),             # 文泉驿等宽正黑
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 1),
]

PROBE = "车库存取"      # 用这几个字检查字体里到底有没有中文
_RAM = "/_fonts"
_mounted = False


def _open(path, idx):
    """先用 Python 把字体文件读进内存，再放进 Panda3D 的内存盘里加载。
    这样绕开了 Panda3D 自己的路径处理：路径里有中文、空格、盘符时也不会读失败。"""
    global _mounted
    vfs = VirtualFileSystem.getGlobalPtr()
    if not _mounted:
        vfs.mount(VirtualFileMountRamdisk(), _RAM, 0)
        _mounted = True
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    name = "%s/%d_%s" % (_RAM, idx, os.path.basename(path))
    if not vfs.exists(Filename(name)):
        vfs.writeFile(Filename(name), data, False)
    font = DynamicTextFont(Filename(name), idx)
    if not font.isValid():
        return None
    font.setPixelsPerUnit(48)             # 必须在第一次画字之前设置
    font.setPageSize(1024, 1024)          # 汉字多，纹理页大一点
    return font


def has_chinese(font):
    tn = TextNode("probe")
    tn.setFont(font)
    return all(tn.hasCharacter(ch) for ch in PROBE)


def _load(candidates):
    """返回 (字体, 文件路径)；都不行时返回 (None, None)。"""
    for path, idx in candidates:
        if not os.path.exists(path):
            continue
        font = _open(path, idx)
        if font is None or not has_chinese(font):
            print("[字体] %s 读不出中文，跳过" % path, file=sys.stderr)
            continue
        return font, path
    return None, None


def load_fonts():
    """返回 (界面字体, 等宽字体, 粗体或 None)。"""
    ui, ui_path = _load(UI_FONTS)
    mono, _ = _load(MONO_FONTS)
    bold, _ = _load(BOLD_FONTS)
    if ui is None:
        print("\n[警告] 没找到能显示中文的字体，界面上的中文会显示成方块。\n"
              "       请确认 fonts 文件夹还在（应和 main.py 放在同一层），里面有 NotoSansSC-Regular.otf。\n",
              file=sys.stderr)
    else:
        print("[字体] 使用 %s" % ui_path)
    return ui, mono or ui, bold


def spaced(font, line_height):
    """同一个字体的副本，行距加大。中文段落行距太密时很难读，1.45 倍左右比较舒服。"""
    if font is None:
        return None
    f = font.makeCopy()
    f.setLineHeight(max(font.getLineHeight(), line_height))
    return f


ACCENT = (0.12, 0.33, 0.68, 1)    # 标题、强调用的蓝色
CAR = (0.1, 0.5, 0.2, 1)          # 状态图里"有车"
EMPTY = (0.6, 0.6, 0.6, 1)        # 状态图里"空"


def register_styles(bold=None):
    """登记文字样式。用法：\1名字\1……\2。"""
    mgr = TextPropertiesManager.getGlobalPtr()

    def style(name, color, use_bold=False):
        tp = TextProperties()
        tp.setTextColor(*color)
        if use_bold and bold is not None:
            tp.setFont(bold)
        mgr.setProperties(name, tp)

    style("b", ACCENT, True)                       # 正文里的强调（车库说明里的 <b>）
    style("cur", (0.05, 0.2, 0.5, 1), True)        # 正在执行的那一步
    style("done", (0.4, 0.4, 0.42, 1))             # 已经做完的步骤
    style("red", (0.8, 0, 0, 1), True)
    style("grey", (0.5, 0.5, 0.5, 1))
    style("car", CAR)                             # 状态图用等宽字体，这里不能换粗体，否则对不齐
    style("empty", EMPTY)


def color_grid(text):
    """给状态图上色：有车的格子绿色，空的格子灰色，一眼就能看出哪里有车。
    状态图是车库模块生成的纯文字，这里只加颜色，不改内容。"""
    def cell(m):
        tok = m.group(0)
        if "空" in tok or not tok.strip("[] "):
            return "\1empty\1" + tok + "\2"
        if "车" in tok:
            return "\1car\1" + tok + "\2"
        return tok
    text = text.replace("│", "|")      # 制表符"│"在不同字体里有的占半格有的占一格，换成 | 才对得齐
    text = re.sub(r"\[[^\]\n]*\]|\d+车|\d+空|空位", cell, text)
    return re.sub(r"(?<![\w\[])--(?![\w\]])", "\1empty\1--\2", text)


def rich(html):
    """车库说明里只用到了 <b>…</b>，换成 Panda3D 的样式标记；其它标签直接去掉。"""
    s = html.replace("<b>", "\1b\1").replace("</b>", "\2").replace("<br>", "\n")
    return re.sub(r"<[^>]+>", "", s)


NO_LINE_START = "，。、；：！？）》」』”’,.;:!?)]】"


def wrap(text, node, max_w):
    """按字符换行。Panda3D 自带的 wordwrap 只在空格处断行，
    一段中文里夹一个空格（比如"2. 第1列……"）就会在空格处整段折到下一行，很难看。
    node: 用来量字宽的 TextNode（决定字体）；max_w: 每行最多多宽（文字单位）。"""
    widths = {}

    def w(ch):
        if ch not in widths:
            widths[ch] = node.calcWidth(ch)
        return widths[ch]

    out = []
    for para in text.split("\n"):
        line, lw, i = "", 0.0, 0
        while i < len(para):
            ch = para[i]
            if ch == "\1":                       # \1样式名\1 …… \2：样式标记，不占宽度
                j = para.index("\1", i + 1)
                line += para[i:j + 1]
                i = j + 1
                continue
            if ch == "\2":
                line += ch
                i += 1
                continue
            cw = w(ch)
            if lw + cw > max_w and lw > 0 and ch not in NO_LINE_START:
                out.append(line)
                line, lw = "", 0.0
                if ch == " ":
                    i += 1
                    continue
            line += ch
            lw += cw
            i += 1
        out.append(line)
    return "\n".join(out)
