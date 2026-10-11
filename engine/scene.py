"""Panda3D 这一层：把车库模块描述的物体画出来，并按动作原语播放动画。

车库模块不直接 import panda3d，而是通过这里的 Ctx 搭场景，
这样调度逻辑可以脱离 3D 单独运行和测试。

坐标约定：车库模块沿用"y 朝上、z 朝向观众"的坐标（x 右、y 上、z 前），
Panda3D 是"z 朝上、y 朝屏幕里"。两者只差一个绕 x 轴的 90° 旋转，
换算统一在 to_panda() 里做，车库代码不用关心。
"""
import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, NodePath, TextNode, TransparencyAttrib, Vec3)

from engine.motion import poses_at, step_duration

CAR_COLORS = [(0.9, 0.15, 0.15), (1.0, 0.55, 0.0), (0.0, 0.75, 0.85), (0.2, 0.75, 0.2),
              (0.85, 0.2, 0.85), (0.95, 0.85, 0.1), (0.55, 0.4, 1.0), (0.3, 0.5, 0.95)]
PALLET = (0.72, 0.72, 0.68)
STEEL = (0.25, 0.35, 0.55)


def to_panda(t):
    """车库坐标 (x, y上, z前) → Panda3D 坐标 (x, y里, z上)。"""
    x, y, z = t
    return Vec3(x, -z, y)


# ---------- 基本几何体（只建一次，之后都是共享同一份顶点数据的副本） ----------
def _make_cube():
    """以原点为中心、边长 1 的立方体，每个面单独的法线，方便打光。"""
    vdata = GeomVertexData("cube", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vw, nw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
             ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
             ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    for i, (n, u, v) in enumerate(faces):
        n, u, v = Vec3(*n), Vec3(*u), Vec3(*v)
        c = n * 0.5
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vw.addData3(c + u * (0.5 * su) + v * (0.5 * sv))
            nw.addData3(n)
        tris.addVertices(4 * i, 4 * i + 1, 4 * i + 2)
        tris.addVertices(4 * i, 4 * i + 2, 4 * i + 3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cube")
    node.addGeom(geom)
    return NodePath(node)


def _make_cylinder(seg=32):
    """半径 1、沿 +y 从 0 到 1 的圆柱（Panda3D 里 lookAt 让 +y 指向目标）。"""
    vdata = GeomVertexData("cyl", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vw, nw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    k = 0
    for i in range(seg):                    # 侧面
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        for a, y in ((a0, 0), (a1, 0), (a1, 1), (a0, 1)):
            vw.addData3(math.cos(a), y, math.sin(a))
            nw.addData3(math.cos(a), 0, math.sin(a))
        tris.addVertices(k, k + 3, k + 2)
        tris.addVertices(k, k + 2, k + 1)
        k += 4
    for y, ny in ((0, -1), (1, 1)):         # 两个端面
        center = k
        vw.addData3(0, y, 0)
        nw.addData3(0, ny, 0)
        k += 1
        for i in range(seg + 1):
            a = 2 * math.pi * i / seg
            vw.addData3(math.cos(a), y, math.sin(a))
            nw.addData3(0, ny, 0)
        for i in range(seg):
            if ny > 0:
                tris.addVertices(center, k + i + 1, k + i)
            else:
                tris.addVertices(center, k + i, k + i + 1)
        k += seg + 1
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cylinder")
    node.addGeom(geom)
    return NodePath(node)


_CUBE = None
_CYL = None


def _protos():
    global _CUBE, _CYL
    if _CUBE is None:
        _CUBE, _CYL = _make_cube(), _make_cylinder()
    return _CUBE, _CYL


class Part:
    """一组一起运动的 3D 物体：挂在同一个节点下，移动/转动只改这个节点。"""

    def __init__(self, node, anchor, heading=0):
        self.node = node
        self.set_pose(anchor, heading)

    def set_pose(self, anchor, heading):
        self.anchor, self.heading = tuple(anchor), heading
        self.node.setPos(to_panda(anchor))
        # 车库坐标里绕 y 轴转 deg，换到 Panda3D 正好是绕 z 轴转 deg，也就是 H
        self.node.setH(heading)

    def destroy(self):
        self.node.removeNode()


class Ctx:
    def __init__(self, parent, label_font=None):
        """parent: 场景挂在哪个节点下（一般是 render）。label_font: 3D 标签用的字体（要能显示中文）。"""
        self.parent = parent
        self.label_font = label_font
        self._new_root()

    def _new_root(self):
        self.root = self.parent.attachNewNode("garage")
        self.static_root = self.root.attachNewNode("static")
        self.label_root = self.root.attachNewNode("labels")
        self.parts = {}
        self.labels = []          # (节点, 字高像素)

    def update_labels(self, cam, px_to_world):
        """每帧调用：按离相机的距离缩放标签，让它在屏幕上的大小固定（和 VPython 的 label 一样）。
        px_to_world: 离相机 1 米处，1 个像素对应多少米。"""
        cam_pos = cam.getPos(self.root)
        alive = []
        for np, h in self.labels:
            if np.isEmpty():
                continue
            d = (np.getPos(self.root) - cam_pos).length()
            np.setScale(h * 1.2 * d * px_to_world)     # 1.2：比 VPython 的字号稍大一点，更好认
            alive.append((np, h))
        self.labels = alive

    # ---- 画单个形状 ----
    def _box(self, parent, pos, size, color, opacity=1.0):
        cube, _ = _protos()
        np = cube.copyTo(parent)
        np.setPos(to_panda(pos))
        sx, sy, sz = size
        np.setScale(max(sx, 1e-4), max(sz, 1e-4), max(sy, 1e-4))
        np.setColor(*color, opacity)
        if opacity < 1:
            np.setTransparency(TransparencyAttrib.MAlpha)
            np.setDepthWrite(False)
            np.setBin("transparent", 0)
        return np

    def _cyl(self, parent, pos, axis, radius, color):
        _, cyl = _protos()
        np = cyl.copyTo(parent)
        p, a = to_panda(pos), to_panda(axis)
        np.setPos(p)
        up = Vec3(0, 0, 1) if abs(a.normalized().z) < 0.99 else Vec3(1, 0, 0)
        np.lookAt(parent, p + a, up)
        np.setScale(radius, a.length(), radius)
        np.setColor(*color, 1)
        return np

    def _label(self, parent, pos, txt, height, boxed):
        tn = TextNode("label")
        tn.setText(txt)
        tn.setAlign(TextNode.ACenter)
        if self.label_font:
            tn.setFont(self.label_font)
        tn.setTextColor(0, 0, 0, 1)
        if boxed:
            tn.setCardColor(1, 1, 1, 0.8)
            tn.setCardAsMargin(0.25, 0.25, 0.15, 0.15)
            tn.setCardDecal(True)
        np = parent.attachNewNode(tn)
        np.setPos(to_panda(pos))
        np.setBillboardPointEye()
        self.labels.append((np, height))
        # 和 VPython 的 label 一样永远画在最上层，不会被柱子挡住
        np.setBin("fixed", 100)
        np.setDepthTest(False)
        np.setDepthWrite(False)
        np.setLightOff()
        np.setTransparency(TransparencyAttrib.MAlpha)
        return np

    # ---- 静态物体 ----
    def box(self, pos, size, color=STEEL, opacity=1.0):
        return self._box(self.static_root, pos, size, color, opacity)

    def cyl(self, pos, axis, radius, color=STEEL):
        return self._cyl(self.static_root, pos, axis, radius, color)

    def text(self, pos, txt, height=13):
        return self._label(self.label_root, pos, txt, height, boxed=False)

    def ground(self, cx, cz, sx, sz):
        self.box((cx, -0.06, cz), (sx, 0.1, sz), (0.55, 0.55, 0.55))

    def driveway(self, x, z0, z1, w=2.6):
        self.box((x, -0.005, (z0 + z1) / 2), (w, 0.02, abs(z1 - z0)), (0.33, 0.33, 0.36))

    # ---- 可动物体 ----
    def part(self, name, pos, shapes, heading=0):
        """shapes: [("box", 偏移, 尺寸, 颜色) | ("cyl", 偏移, 轴, 半径, 颜色) | ("label", 偏移, 文字)]
        偏移量按朝向 0° 记录，转动时整体旋转。"""
        node = self.root.attachNewNode(name)
        for s in shapes:
            if s[0] == "box":
                self._box(node, s[1], s[2], s[3])
            elif s[0] == "cyl":
                self._cyl(node, s[1], s[2], s[3], s[4])
            elif s[0] == "label":
                self._label(node, s[1], s[2], 12, boxed=True)
        self.parts[name] = Part(node, pos, heading)
        return self.parts[name]

    def pallet(self, name, pos, w=2.5, d=4.8, tag=None, heading=0):
        shapes = [("box", (0, 0, 0), (w, 0.1, d), PALLET),
                  ("box", (-w / 2 + 0.06, 0.08, 0), (0.08, 0.08, d), (0.5, 0.5, 0.48)),
                  ("box", (w / 2 - 0.06, 0.08, 0), (0.08, 0.08, d), (0.5, 0.5, 0.48))]
        if tag:
            shapes.append(("label", (0, 0.15, d / 2 - 0.2), tag))
        return self.part(name, pos, shapes, heading)

    def car(self, name, pos, idx, heading=0):
        c = CAR_COLORS[(idx - 1) % len(CAR_COLORS)]
        dark = tuple(x * 0.7 for x in c)
        shapes = [("box", (0, 0.42, 0), (1.7, 0.55, 4.0), c),
                  ("box", (0, 0.9, 0.25), (1.5, 0.45, 2.0), dark),
                  ("box", (-0.55, 0.45, -2.0), (0.3, 0.15, 0.05), (1, 1, 0.7)),   # 车头灯：车头朝 -z
                  ("box", (0.55, 0.45, -2.0), (0.3, 0.15, 0.05), (1, 1, 0.7))]
        return self.part(name, pos, shapes, heading)

    def spawn_car(self, a):
        idx = int(a["name"][3:])
        self.car(a["name"], a["pos"], idx, a.get("heading", 0))

    def remove(self, name):
        p = self.parts.pop(name, None)
        if p:
            p.destroy()

    def finish(self):
        """场景搭完后调用：把几百个静止的柱子、横梁合并成少数几块，渲染更快。"""
        self.static_root.flattenStrong()

    def clear(self):
        self.root.removeNode()
        self._new_root()

    # ---- 播放一步（生成器：每帧 send 进来这一帧的真实秒数） ----
    def play(self, step, playback, ctl):
        """playback(): 当前播放倍速（模拟秒/真实秒）；ctl: 有 paused 属性的控制对象。

        用法：gen = ctx.play(...); next(gen); 之后每帧 gen.send(dt)，直到 StopIteration。
        不能像 VPython 那样在函数里 while + rate() 阻塞，因为 Panda3D 的画面
        是由主循环一帧一帧画的，阻塞了窗口就卡死了。
        """
        for a in step["actions"]:
            if a["op"] == "spawn":
                self.spawn_car(a)
        names = set()
        for a in step["actions"]:
            names.update(a.get("names", []))
            for ns, _ in a.get("items", []):
                names.update(ns)
        start = {n: (self.parts[n].anchor, self.parts[n].heading) for n in names if n in self.parts}
        T = step_duration(step)
        tau = 0.0
        while tau < T:
            dt = yield
            if ctl.paused:
                continue
            tau = min(T, tau + playback() * (dt or 0.0))
            for n, (p, h) in poses_at(start, step, tau).items():
                self.parts[n].set_pose(p, h)
        for a in step["actions"]:
            if a["op"] == "remove":
                self.remove(a["name"])
