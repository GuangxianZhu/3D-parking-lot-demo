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


# ---- 轿车外形（车库坐标：x 右、y 上、z 前；车头朝 -z）----
# 侧面轮廓 (z, y)：下车身（保险杠、引擎盖、后备箱）和车舱（玻璃）各是一个凸多边形
CAR_BODY = [(-1.90, 0.18), (1.90, 0.18), (2.04, 0.26), (2.05, 0.62), (1.95, 0.76), (1.40, 0.82),
            (-0.60, 0.82), (-1.85, 0.72), (-2.05, 0.60), (-2.06, 0.28)]
CAR_CABIN = [(-0.62, 0.81), (1.42, 0.81), (0.95, 1.27), (-0.10, 1.27)]
CAR_ROOF = [(-0.12, 1.25), (0.97, 1.25), (0.93, 1.31), (-0.08, 1.31)]
GLASS = (0.16, 0.22, 0.30)
TIRE = (0.07, 0.07, 0.08)
RIM = (0.78, 0.79, 0.82)
WHEEL_R, WHEEL_Z, WHEEL_X = 0.31, 1.32, 0.70


def car_shapes(color):
    dark = tuple(c * 0.55 for c in color)
    shapes = [("prism", CAR_BODY, (-0.86, 0.86), color),
              ("prism", CAR_CABIN, (-0.72, 0.72), GLASS),             # 整个车舱是玻璃色，看起来就是车窗
              ("prism", CAR_ROOF, (-0.70, 0.70), color),              # 车顶
              # 车窗之间的立柱（B 柱）和窗下沿的腰线
              ("box", (-0.725, 1.04, 0.42), (0.02, 0.46, 0.12), color),
              ("box", (0.725, 1.04, 0.42), (0.02, 0.46, 0.12), color),
              ("box", (-0.865, 0.62, 0), (0.02, 0.05, 3.7), dark),
              ("box", (0.865, 0.62, 0), (0.02, 0.05, 3.7), dark),
              # 车头：前大灯、进气格栅、车牌
              ("box", (-0.58, 0.56, -2.06), (0.38, 0.12, 0.04), (1, 0.97, 0.8)),
              ("box", (0.58, 0.56, -2.06), (0.38, 0.12, 0.04), (1, 0.97, 0.8)),
              ("box", (0, 0.47, -2.075), (0.62, 0.16, 0.03), (0.12, 0.12, 0.14)),
              ("box", (0, 0.30, -2.08), (0.44, 0.12, 0.02), (0.95, 0.95, 0.95)),
              # 车尾：尾灯、车牌
              ("box", (-0.60, 0.62, 2.05), (0.36, 0.11, 0.04), (0.85, 0.08, 0.08)),
              ("box", (0.60, 0.62, 2.05), (0.36, 0.11, 0.04), (0.85, 0.08, 0.08)),
              ("box", (0, 0.40, 2.06), (0.44, 0.12, 0.02), (0.95, 0.95, 0.95)),
              # 后视镜
              ("box", (-0.93, 0.92, -0.48), (0.14, 0.09, 0.14), color),
              ("box", (0.93, 0.92, -0.48), (0.14, 0.09, 0.14), color)]
    for z in (-WHEEL_Z, WHEEL_Z):
        for side in (-1, 1):
            x_in = side * WHEEL_X
            shapes.append(("cyl", (x_in, WHEEL_R, z), (side * 0.22, 0, 0), WHEEL_R, TIRE))
            shapes.append(("cyl", (x_in + side * 0.2, WHEEL_R, z), (side * 0.035, 0, 0), WHEEL_R * 0.58, RIM))
    return shapes


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


def _make_prism(profile, x0, x1):
    """侧面轮廓（车库坐标里的 (z, y) 点，凸多边形）沿 x 从 x0 拉伸到 x1 得到的柱体。
    用来做车身、车窗这种侧面看是梯形/多边形的形状。每个面单独法线，棱角分明。"""
    vdata = GeomVertexData("prism", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vw, nw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    k = [0]

    def face(pts, n):
        """pts: 车库坐标的凸多边形顶点；n: 外法线。按法线方向自动决定三角形绕向。"""
        P = [to_panda(q) for q in pts]
        N = to_panda(n)
        for q in P:
            vw.addData3(q)
            nw.addData3(N)
        for i in range(1, len(P) - 1):
            a, b, c = 0, i, i + 1
            if (P[b] - P[a]).cross(P[c] - P[a]).dot(N) < 0:
                b, c = c, b
            tris.addVertices(k[0] + a, k[0] + b, k[0] + c)
        k[0] += len(P)

    face([(x0, y, z) for z, y in profile], (-1, 0, 0))
    face([(x1, y, z) for z, y in profile], (1, 0, 0))
    cz = sum(z for z, _ in profile) / len(profile)
    cy = sum(y for _, y in profile) / len(profile)
    for i, (z0, y0) in enumerate(profile):
        z1, y1 = profile[(i + 1) % len(profile)]
        nz, ny = (y1 - y0), -(z1 - z0)                      # 边的法线，再翻成朝外
        if nz * ((z0 + z1) / 2 - cz) + ny * ((y0 + y1) / 2 - cy) < 0:
            nz, ny = -nz, -ny
        L = math.hypot(nz, ny) or 1
        face([(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)], (0, ny / L, nz / L))
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("prism")
    node.addGeom(geom)
    return NodePath(node)


_CUBE = None
_CYL = None
_PRISMS = {}


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
        self.tags = {}            # 车名 → 车顶标签节点

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

    def _prism(self, parent, profile, x0, x1, color):
        key = (tuple(profile), x0, x1)
        if key not in _PRISMS:
            _PRISMS[key] = _make_prism(profile, x0, x1)
        np = _PRISMS[key].copyTo(parent)
        np.setColor(*color, 1)
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
        """shapes: [("box", 偏移, 尺寸, 颜色) | ("cyl", 偏移, 轴, 半径, 颜色) | ("label", 偏移, 文字)
                    | ("prism", 侧面轮廓[(z, y)], (x0, x1), 颜色)]
        偏移量按朝向 0° 记录，转动时整体旋转。"""
        node = self.root.attachNewNode(name)
        for s in shapes:
            if s[0] == "box":
                self._box(node, s[1], s[2], s[3])
            elif s[0] == "cyl":
                self._cyl(node, s[1], s[2], s[3], s[4])
            elif s[0] == "label":
                self._label(node, s[1], s[2], 12, boxed=True)
            elif s[0] == "prism":
                self._prism(node, s[1], s[2][0], s[2][1], s[3])
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
        """一辆轿车：车头朝 -z，长约 4.1 m、宽 1.8 m（含轮子）、高 1.3 m。
        原点在车底中心的地面上，和原来的方块车占的空间差不多，所以车库里的尺寸不用改。"""
        return self.part(name, pos, car_shapes(CAR_COLORS[(idx - 1) % len(CAR_COLORS)]), heading)

    def spawn_car(self, a):
        if a["name"] in self.parts:      # 司机视角下车已经提前开到入口等着了，这里只校正位置
            self.parts[a["name"]].set_pose(a["pos"], a.get("heading", 0))
            return
        idx = int(a["name"][3:])
        self.car(a["name"], a["pos"], idx, a.get("heading", 0))

    # ---- 司机视角用：车牌标签、高亮框 ----
    def tag(self, name, text, replace=True):
        """给一个可动物体头顶加一个标签（比如"您的车 沪A·52731"），跟着它一起动。
        一个物体只有一个标签；replace=False 时已有标签就不动。"""
        old = self.tags.get(name)
        if old is not None and not old.isEmpty():
            if not replace:
                return old
            old.removeNode()
        if name in self.parts:
            np = self._label(self.parts[name].node, (0, 2.0, 0), text, 13, boxed=True)
            np.node().setCardColor(1, 0.92, 0.45, 0.95)
            self.tags[name] = np
            return np

    def highlight(self, pos=None, follow=None, size=(2.9, 2.0, 5.4)):
        """半透明的黄色框，标出目标车位（pos）或者跟着某辆车走（follow）。每帧由 pulse() 让它闪。"""
        self.clear_highlight()
        parent = self.parts[follow].node if follow in self.parts else self.root
        self.hl = self._box(parent, (0, size[1] / 2, 0) if follow else
                            (pos[0], pos[1] + size[1] / 2, pos[2]), size, (1, 0.8, 0.1), 0.35)
        self.hl.setLightOff()

    def clear_highlight(self):
        hl = getattr(self, "hl", None)
        if hl is not None and not hl.isEmpty():
            hl.removeNode()
        self.hl = None

    def pulse(self, t):
        hl = getattr(self, "hl", None)
        if hl is not None and not hl.isEmpty():
            hl.setAlphaScale(0.45 + 0.4 * math.sin(t * 5))

    def remove(self, name):
        self.tags.pop(name, None)
        p = self.parts.pop(name, None)
        if p:
            p.destroy()

    def finish(self):
        """场景搭完后调用：把几百个静止的柱子、横梁合并成少数几块，渲染更快。"""
        self.static_root.flattenStrong()

    def clear(self):
        self.hl = None
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
