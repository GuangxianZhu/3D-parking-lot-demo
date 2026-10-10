"""VPython 这一层：把车库模块描述的物体画出来，并按动作原语播放动画。

车库模块不直接 import vpython，而是通过这里的 Ctx 搭场景，
这样调度逻辑可以脱离 3D 单独运行和测试。
"""
from vpython import box, cylinder, label, vector, rate

from engine.motion import poses_at, rot_y, step_duration

CAR_COLORS = [(0.9, 0.15, 0.15), (1.0, 0.55, 0.0), (0.0, 0.75, 0.85), (0.2, 0.75, 0.2),
              (0.85, 0.2, 0.85), (0.95, 0.85, 0.1), (0.55, 0.4, 1.0), (0.3, 0.5, 0.95)]
PALLET = (0.72, 0.72, 0.68)
STEEL = (0.25, 0.35, 0.55)


def V(t):
    return vector(*t)


class Part:
    """一组一起运动的 3D 物体。偏移量按朝向 0° 记录，转动时整体旋转。"""

    def __init__(self, anchor, objs, heading=0):
        self.anchor = tuple(anchor)
        self.heading = 0
        self.items = []
        for o in objs:
            d = o.pos - V(anchor)
            off = (d.x, d.y, d.z)
            ax = None if isinstance(o, label) else (o.axis.x, o.axis.y, o.axis.z)
            self.items.append((o, off, ax))
        self.set_pose(anchor, heading)

    def set_pose(self, anchor, heading):
        self.anchor, self.heading = tuple(anchor), heading
        a = V(anchor)
        for o, off, ax in self.items:
            o.pos = a + V(rot_y(off, heading))
            if ax is not None and heading % 360:
                o.axis = V(rot_y(ax, heading))
                o.up = vector(0, 1, 0)
            elif ax is not None:
                o.axis = V(ax)
                o.up = vector(0, 1, 0)

    def destroy(self):
        for o, _, _ in self.items:
            o.visible = False
            try:
                o.delete()
            except Exception:
                pass


class Ctx:
    def __init__(self, canvas):
        self.canvas = canvas
        self.parts = {}
        self.static = []

    # ---- 静态物体 ----
    def box(self, pos, size, color=STEEL, opacity=1.0):
        b = box(canvas=self.canvas, pos=V(pos), size=V(size), color=V(color), opacity=opacity)
        self.static.append(b)
        return b

    def cyl(self, pos, axis, radius, color=STEEL):
        c = cylinder(canvas=self.canvas, pos=V(pos), axis=V(axis), radius=radius, color=V(color))
        self.static.append(c)
        return c

    def text(self, pos, txt, height=13):
        lb = label(canvas=self.canvas, pos=V(pos), text=txt, height=height, box=False,
                   color=vector(0, 0, 0), opacity=0)
        self.static.append(lb)
        return lb

    def ground(self, cx, cz, sx, sz):
        self.box((cx, -0.06, cz), (sx, 0.1, sz), (0.55, 0.55, 0.55))

    def driveway(self, x, z0, z1, w=2.6):
        self.box((x, -0.005, (z0 + z1) / 2), (w, 0.02, abs(z1 - z0)), (0.33, 0.33, 0.36))

    # ---- 可动物体 ----
    def part(self, name, pos, shapes, heading=0):
        """shapes: [("box", 偏移, 尺寸, 颜色) | ("cyl", 偏移, 轴, 半径, 颜色) | ("label", 偏移, 文字)]"""
        p = V(pos)
        objs = []
        for s in shapes:
            if s[0] == "box":
                objs.append(box(canvas=self.canvas, pos=p + V(s[1]), size=V(s[2]), color=V(s[3])))
            elif s[0] == "cyl":
                objs.append(cylinder(canvas=self.canvas, pos=p + V(s[1]), axis=V(s[2]),
                                     radius=s[3], color=V(s[4])))
            elif s[0] == "label":
                objs.append(label(canvas=self.canvas, pos=p + V(s[1]), text=s[2], height=12,
                                  box=True, color=vector(0, 0, 0), background=vector(1, 1, 1),
                                  opacity=0.8))
        self.parts[name] = Part(pos, objs, heading)
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

    def clear(self):
        for p in list(self.parts.values()):
            p.destroy()
        self.parts = {}
        for o in self.static:
            o.visible = False
            try:
                o.delete()
            except Exception:
                pass
        self.static = []

    # ---- 播放一步 ----
    def play(self, step, playback, ctl):
        """playback(): 当前播放倍速（模拟秒/真实秒）；ctl: 有 paused 属性的控制对象。"""
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
            rate(60)
            if ctl.paused:
                continue
            tau = min(T, tau + playback() / 60.0)
            for n, (p, h) in poses_at(start, step, tau).items():
                self.parts[n].set_pose(p, h)
        for a in step["actions"]:
            if a["op"] == "remove":
                self.remove(a["name"])
