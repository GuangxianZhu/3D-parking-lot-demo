"""Panda3D 渲染层的两个容易出错的地方：
1. 坐标换算：车库模块用"y 朝上"的坐标，Panda3D 是"z 朝上"，转向角也要对得上；
2. 中文折行。
不开窗口，只用场景图节点计算，所以没有显示器也能跑。
运行：python -m tests.test_scene
"""
from panda3d.core import NodePath, TextNode

import re

from engine.fonts import color_grid, load_fonts, wrap
from garages import ALL
from engine.motion import rot_y
from engine.scene import Ctx, to_panda


def close(p, q):
    return all(abs(a - b) < 1e-4 for a, b in zip(p, q))


def test_part_pose_matches_rot_y():
    """车上一个点（偏移 off）在 Panda3D 里的世界坐标，应该等于车库坐标里 anchor + rot_y(off) 再换算。"""
    root = NodePath("root")
    ctx = Ctx(root)
    off = (0.55, 0.45, -2.0)                       # 车头灯
    ctx.part("car1", (0, 0, 0), [("box", off, (0.3, 0.15, 0.05), (1, 1, 0.7))])
    lamp = ctx.parts["car1"].node.getChild(0)
    for anchor, heading in [((0, 0, 0), 0), ((3, 2.2, -5.3), 90), ((-1, 0.1, 4), 180), ((2, 0, 1), -37)]:
        ctx.parts["car1"].set_pose(anchor, heading)
        want = to_panda(tuple(a + r for a, r in zip(anchor, rot_y(off, heading))))
        got = lamp.getPos(root)
        assert close(got, want), (anchor, heading, got, want)


def test_box_size_axes():
    """box 的尺寸 (x 宽, y 高, z 深) 要换到 Panda3D 的 (x, y 深, z 高)。"""
    root = NodePath("root")
    b = Ctx(root).box((1, 2, 3), (0.5, 4.0, 2.0))
    lo, hi = b.getTightBounds(root)
    assert close(hi - lo, (0.5, 2.0, 4.0)), hi - lo
    assert close((lo + hi) / 2, to_panda((1, 2, 3)))


def test_wrap_cjk():
    ui = load_fonts()[0]
    tn = TextNode("t")
    if ui:
        tn.setFont(ui)
    text = "2. 第1列下层停着车。上层车板一降下来就会压到它，所以必须先把下层的车开走。"
    lines = wrap(text, tn, 12).split("\n")
    assert lines[0].startswith("2. 第1列"), lines        # 不会在 "2." 后面的空格处整段折行
    assert all(tn.calcWidth(l) <= 12 + tn.calcWidth("。") for l in lines), lines
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")
    styled = wrap("\1b\1重点\2说明" * 5, tn, 6)
    assert styled.count("\1b\1") == 5 and styled.count("\2") == 5



def test_color_grid_only_adds_color():
    """状态图上色后，去掉样式标记应该和原文一字不差（除了把"│"换成"|"）。"""
    for cls in ALL:
        raw = cls().ascii()
        colored = color_grid(raw)
        assert re.sub("\x01[^\x01]*\x01|\x02", "", colored) == raw.replace("│", "|"), cls.name
        assert "\1car\1" in colored, cls.name


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK ", name)
