"""平面移动（3 层，每层一条通道 + 一台台车，左端一台升降机；夹轮式，没有载车板）。

升降机只管换层，台车只管本层水平搬运。即使只处理一个请求，两者也能"预定位"并行干活。
"""
from garages.base import Garage, move, turn, spawn, remove, t_of, DRIVE_SPEED, DRIVE_DIST

W, H = 3.0, 2.4
LEVELS, COLS = 3, 4          # 车位列 1..4；第 0 列是升降机
Z = 5.3
LIFT_SPEED = 60              # 升降机 m/min（示意）
SHUTTLE_SPEED = 80           # 台车 m/min（示意）
CLAMP_SPEED = 15             # 夹轮搬运器拖车 m/min（示意）
TURN_TIME = 8
SIDES = {"前": 1, "后": -1}


class PlaneMove(Garage):
    key = "plane"
    name = "平面移动（3 层 × 2 排 × 4 列）"
    intro = ("每层中间一条通道，两侧是车位，<b>每层一台台车</b>；左端一台<b>升降机</b>连接各层和地面入口。"
             "升降机只管换层，台车只管本层的水平搬运，两者能<b>同时干活</b>（预定位）。"
             "这里用的是<b>夹轮式</b>搬运器：钻到车底夹住轮胎，没有载车板，所以存车不用先取空板。")
    camera = {"center": (5, 3, 2), "forward": (-0.45, -0.45, -1), "range": 11}
    footprint = (COLS + 1) * W * (2 * Z + 5.2)
    speed_note = f"升降机 {LIFT_SPEED}、台车 {SHUTTLE_SPEED}、夹轮 {CLAMP_SPEED} m/min，旋转 {TURN_TIME} s"

    def reset(self):
        self.slot_ids = [f"{lv + 1}F{s}{c}" for lv in range(LEVELS) for s in SIDES for c in range(1, COLS + 1)]
        self.car = {sid: (self.new_car()[0] if k % 5 not in (1, 3) else None)
                    for k, sid in enumerate(self.slot_ids)}
        self.lift_lv = 0
        self.shuttle = {lv: 1 for lv in range(LEVELS)}     # 台车所在列

    def slots(self):
        return list(self.slot_ids)

    def slot_label(self, sid):
        return f"{sid[:2]} {sid[2]}排第{sid[3]}列"

    def parse(self, sid):
        return int(sid[0]) - 1, SIDES[sid[2]], int(sid[3])

    def has_car(self, sid):
        return self.car[sid] is not None

    def car_in(self, sid):
        return self.car[sid]


    def pos(self, sid):
        lv, side, c = self.parse(sid)
        return (c * W, lv * H + 0.1, side * Z)

    # ---- 设备动作（只生成动作，不加步骤） ----
    def _lift(self, lv, payload):
        if lv == self.lift_lv:
            return None, 0
        dy = (lv - self.lift_lv) * H
        self.lift_lv = lv
        t = t_of(dy, LIFT_SPEED)
        return move(["lift"] + payload, (0, dy, 0), t), t

    def _shuttle(self, lv, col, payload):
        c0 = self.shuttle[lv]
        if c0 == col:
            return None, 0
        dx = (col - c0) * W
        self.shuttle[lv] = col
        t = t_of(dx, SHUTTLE_SPEED)
        return move([f"S{lv}"] + payload, (dx, 0, 0), t), t

    def _prepare(self, lift_lv, lv, col, steps, why):
        a1, t1 = self._lift(lift_lv, [])
        a2, t2 = self._shuttle(lv, col, [])
        if not a1 and not a2:
            return
        parts = []
        if a1:
            parts.append(f"升降机{'到底层' if lift_lv == 0 else f'到 {lift_lv + 1}F'}（{t1:.1f}s）")
        if a2:
            parts.append(f"{lv + 1}F 的台车开到第 {col} 列（{t2:.1f}s）")
        txt = "预定位：" + "，同时".join(parts)
        if a1 and a2:
            txt += f"。两台设备并行，只花较长的 {max(t1, t2):.1f}s"
        steps.add(txt + f"，{why}。", a1, a2)

    def park(self, sid, steps):
        lv, side, c = self.parse(sid)
        self._prepare(0, lv, 1, steps, "准备接车")
        car, idx = self.new_car()
        steps.add("车从正面开上升降机，司机下车离开。",
                  spawn(car, (0, 0.1, DRIVE_DIST), idx), move([car], (0, 0, -DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)))
        a, t = self._lift(lv, [car])
        if a:
            steps.add(f"升降机载着车升到 {lv + 1}F（{t:.1f}s）。", a)
        steps.add(f"{lv + 1}F 的台车已经在升降机口等着，夹轮搬运器把车从升降机拖到台车上。",
                  move([car], (W, 0, 0), t_of(W, CLAMP_SPEED)))
        a, t = self._shuttle(lv, c, [car])
        if a:
            steps.add(f"台车载着车沿通道开到第 {c} 列（{t:.1f}s）。升降机这时已经空出来，可以去服务别人。", a)
        self.car[sid] = car
        steps.add(f"夹轮搬运器把车送进{self.slot_label(sid)}。",
                  move([car], (0, 0, side * Z), t_of(Z, CLAMP_SPEED)))

    def retrieve(self, sid, steps):
        lv, side, c = self.parse(sid)
        self._prepare(lv, lv, c, steps, "准备取车")
        car, self.car[sid] = self.car[sid], None
        steps.add("夹轮搬运器钻到车底，夹住轮胎，把车拖到台车上。",
                  move([car], (0, 0, -side * Z), t_of(Z, CLAMP_SPEED)))
        a, t = self._shuttle(lv, 1, [car])
        if a:
            steps.add(f"台车载着车开回升降机口（{t:.1f}s）。", a)
        steps.add("把车从台车拖上升降机。", move([car], (-W, 0, 0), t_of(W, CLAMP_SPEED)))
        a, t = self._lift(0, [car])
        acts = [a] if a else []
        acts.append(turn([car], 180, TURN_TIME))
        steps.add(("升降机降到底层" + (f"（{t:.1f}s）" if a else "") +
                   f"，同时转盘把车转 180°（{TURN_TIME}s），车头朝外。"), *acts)
        steps.add("车往前开走。", move([car], (0, 0, DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)), remove(car))

    def ascii(self):
        lines = []
        for lv in reversed(range(LEVELS)):
            for sname in ("后", "前"):
                row = " ".join("[车]" if self.car[f"{lv + 1}F{sname}{c}"] else "[  ]" for c in range(1, COLS + 1))
                lift = ("升降机" if self.lift_lv == lv else "  │   ") if sname == "后" else "      "
                lines.append(f"{lv + 1}F{sname}排 {lift} {row}")
            lines.append(f"     通道   台车在第 {self.shuttle[lv]} 列")
        return "\n".join(lines)

    def poses(self):
        p = {self.car[s]: (self.pos(s), 0) for s in self.slot_ids if self.car[s]}
        p["lift"] = ((0, self.lift_lv * H, 0), 0)
        for lv in range(LEVELS):
            p[f"S{lv}"] = ((self.shuttle[lv] * W, lv * H + 0.02, 0), 0)
        return p

    def build(self, ctx):
        ctx.ground(6, 3, 20, 26)
        ctx.driveway(0, 2.6, DRIVE_DIST + 2)
        top = LEVELS * H
        for c in range(0, COLS + 2):
            x = (c - 0.5) * W
            for z in (-Z - 2.6, -2.6, 2.6, Z + 2.6):
                if c == 0 and z > 0:
                    continue
                ctx.box((x, top / 2, z), (0.14, top, 0.14))
        for lv in range(LEVELS):
            y = lv * H
            for sname, side in SIDES.items():
                for c in range(1, COLS + 1):
                    ctx.box((c * W, y + 0.03, side * Z), (2.6, 0.06, 4.8), (0.62, 0.62, 0.6))
            for z in (-1.0, 1.0):
                ctx.box(((COLS + 1) * W / 2 + W / 2, y + 0.01, z), (COLS * W, 0.04, 0.12), (0.2, 0.2, 0.2))
            ctx.text((-1.4 * W, y + 0.8, 2.6), f"{lv + 1}F", 15)
            ctx.part(f"S{lv}", (self.shuttle[lv] * W, y + 0.02, 0), [
                ("box", (0, 0, 0), (2.4, 0.1, 4.6), (0.2, 0.7, 0.4)),
                ("label", (0, 0.3, 2.4), f"{lv + 1}F台车")])
        ctx.part("lift", (0, self.lift_lv * H, 0), [
            ("box", (0, 0, 0), (2.8, 0.06, 5.0), (0.9, 0.6, 0.1)),
            ("cyl", (0, 0.03, 0), (0, 0.04, 0), 1.35, (0.5, 0.5, 0.55)),
            ("label", (0, 0.4, 2.6), "升降机")])
        for sid in self.slot_ids:
            if self.car[sid]:
                ctx.car(self.car[sid], self.pos(sid), int(self.car[sid][3:]))
