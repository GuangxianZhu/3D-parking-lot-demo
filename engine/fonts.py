"""中文字体和简单富文本。

Panda3D 自带的默认字体只有英文字母，中文会显示成方块，所以要从系统里找一个中文字体。
等宽字体用来画状态图和对比表：状态图是用空格对齐的，比例字体会对不齐。
"""
import os
import re
import sys

from panda3d.core import DynamicTextFont, Filename, TextProperties, TextPropertiesManager

WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# (文件, TTC 里的第几个字体)。按顺序找，第一个存在的就用。
UI_FONTS = [
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
# 粗体：只用于标题和强调。Linux 上一般没有中文粗体，找不到就只用颜色强调
BOLD_FONTS = [
    (os.path.join(WIN_FONTS, "msyhbd.ttc"), 0),      # 微软雅黑 粗体
    (os.path.join(WIN_FONTS, "msyhbd.ttf"), 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
]
# 等宽：英文半角、汉字正好两个半角宽
MONO_FONTS = [
    (os.path.join(WIN_FONTS, "simsun.ttc"), 1),      # 新宋体 NSimSun
    (os.path.join(WIN_FONTS, "simhei.ttf"), 0),      # 黑体本身就是等宽的
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 7),   # Noto Sans Mono CJK SC
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 1),             # 文泉驿等宽正黑
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 1),
]


def _load(candidates):
    for path, idx in candidates:
        if os.path.exists(path):
            font = DynamicTextFont(Filename.fromOsSpecific(path), idx)
            if font.isValid():
                font.setPixelsPerUnit(48)
                font.setPageSize(1024, 1024)      # 汉字多，纹理页大一点
                return font
    return None


def load_fonts():
    """返回 (界面字体, 等宽字体, 粗体或 None)。找不到中文字体时打印提示，界面中文会显示成方块。"""
    ui = _load(UI_FONTS)
    mono = _load(MONO_FONTS) or ui
    bold = _load(BOLD_FONTS)
    if ui is None:
        print("[警告] 没找到中文字体，界面上的中文会显示成方块。", file=sys.stderr)
    return ui, mono, bold


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
