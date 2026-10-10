"""垂直循环（10 个吊篮）。

吊篮挂在一条竖着的跑道形链条上，靠重力始终保持水平。出入口只有最底部一个。
存/取车 = 把目标吊篮转到最底部；系统会比较顺时针和逆时针哪边更近。
"""
from engine.motion import stadium_length, stadium_point
from garages.base import Garage, move, spawn, remove, loop, t_of, DRIVE_SPEED, DRIVE_DIST

N = 10
R, HANG = 1.6, 1.6
SP = 2.0                                  # 相邻吊篮在链条上的间距
P_LEN = N * SP
STRAIGHT = (P_LEN - 2 * 3.141592653589793 * R) / 2
PATH = {"r": R, "h": STRAIGHT, "cx": 0.0, "cy": 0.1 + HANG + R + STRAIGHT / 2, "z": 0.0, "hang": HANG}
CHAIN_SPEED = 10    # 链条 m/min（示意）


class VerticalCirc(Garage):
    key = "circ"
    name = "垂直循环（10 个吊篮）"
    intro = ("吊篮挂在一条竖着的环形链条上，像竖起来的摩天轮，靠重力保持水平。出入口只有<b>最底部</b>一个。"
             "存/取车就是把目标吊篮转到底部，系统会算<b>顺时针和逆时针哪边更近</b>。"
             "代价是：每次<b>所有吊篮都要跟着转</b>。")
    camera = {"center": (0, 4.5, 1), "forward": (-0.3, -0.2, -1), "range": 8}
    footprint = (2 * R + 2.6) * 6.0
    speed_note = f"链条 {CHAIN_SPEED} m/min"

    def reset(self):
        self.offset = 0.0
        self.car = {i: None for i in range(1, N + 1)}
        for i in range(1, N + 1):
            if i not in (1, 4, 7):
                self.car[i] = self.new_car()[0]

    def slots(self):
        return [str(i) for i in range(1, N + 1)]

    def slot_label(self, sid):
        return f"{sid} 号吊篮"

    def has_car(self, sid):
        return self.car[int(sid)] is not None

    def s_of(self, i):
        return ((i - 1) * SP + self.offset) % P_LEN

    def names(self, i):
        return [f"C{i}"] + ([self.car[i]] if self.car[i] else [])

    def _bring_down(self, i, steps):
        s = self.s_of(i)
        if s < 1e-6 or P_LEN - s < 1e-6:
            steps.add(f"{i} 号吊篮正好就在底部入口，链条不用转。")
            return
        cw, ccw = -s, P_LEN - s          # s 减小 = 从正面看顺时针
        ds = cw if abs(cw) <= abs(ccw) else ccw
        k = round(abs(ds) / SP)
        other = round(abs(ccw if ds == cw else cw) / SP)
        direction = "顺时针" if ds < 0 else "逆时针"
        items = [(self.names(j), self.s_of(j)) for j in range(1, N + 1)]
        self.offset = (self.offset + ds) % P_LEN
        steps.add(f"{i} 号吊篮离底部：{direction}要转 {k} 格，反方向要转 {other} 格。选近的，{direction}转 {k} 格。"
                  f"注意全部 {N} 个吊篮都跟着一起转。",
                  loop(items, PATH, ds, t_of(ds, CHAIN_SPEED)))

    def retrieve(self, sid, steps):
        i = int(sid)
        self._bring_down(i, steps)
        car, self.car[i] = self.car[i], None
        steps.add("车从底部吊篮倒车开出。吊篮不需要转回原位。",
                  move([car], (0, 0, DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)), remove(car))

    def park(self, sid, steps):
        i = int(sid)
        self._bring_down(i, steps)
        car, idx = self.new_car()
        self.car[i] = car
        steps.add("车开进底部的吊篮。", spawn(car, (0, 0.1, DRIVE_DIST), idx),
                  move([car], (0, 0, -DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)))

    def ascii(self):
        order = sorted(range(1, N + 1), key=self.s_of)
        cells = [f"{i}{'车' if self.car[i] else '空'}" for i in order]
        return ("从底部入口开始，逆时针方向依次是：\n" + " → ".join(cells) +
                f"\n底部入口现在是 {order[0]} 号吊篮")

    def poses(self):
        p = {}
        for i in range(1, N + 1):
            x, y, z = stadium_point(PATH, self.s_of(i))
            for n in self.names(i):
                p[n] = ((x, y - HANG, z), 0)
        return p

    def build(self, ctx):
        ctx.ground(0, 4, 12, 16)
        ctx.driveway(0, 2.4, DRIVE_DIST + 2)
        # 两侧的链条（用小方块画出路径）和立柱
        n = 80
        for zc in (-2.7, 2.7):
            for k in range(n):
                x, y, _ = stadium_point(PATH, k * P_LEN / n)
                ctx.box((x, y, zc), (0.12, 0.12, 0.08), (0.2, 0.2, 0.2))
            for sx in (-1, 1):
                ctx.box((sx * (R + 1.5), PATH["cy"], zc), (0.2, 2 * PATH["cy"], 0.2))
            ctx.box((0, 2 * PATH["cy"], zc), (2 * (R + 1.5), 0.2, 0.2))
        steel = (0.25, 0.35, 0.55)
        for i in range(1, N + 1):
            x, y, z = stadium_point(PATH, self.s_of(i))
            pos = (x, y - HANG, z)
            shapes = [("box", (0, 0, 0), (2.4, 0.1, 4.8), (0.72, 0.72, 0.68))]
            for zz in (-2.55, 2.55):            # 两端各一个门形吊架，车从中间穿过
                for xx in (-1.15, 1.15):
                    shapes.append(("box", (xx, HANG / 2, zz), (0.08, HANG, 0.08), steel))
                shapes.append(("box", (0, HANG, zz), (2.38, 0.1, 0.1), steel))
            shapes.append(("box", (0, HANG, 0), (0.1, 0.1, 5.4), steel))
            shapes.append(("label", (0, 0.15, 2.3), str(i)))
            ctx.part(f"C{i}", pos, shapes)
            if self.car[i]:
                ctx.car(self.car[i], pos, int(self.car[i][3:]))
