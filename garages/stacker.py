"""巷道堆垛（巷道两侧各 4 列 × 3 层，载车板式）。

一台堆垛机在中间巷道里行走（X）和升降（Y），再向前或向后伸出取放车板。
入口是巷道左端前侧地面层的"交接区"，带旋转盘。
"""
from garages.base import Garage, move, turn, spawn, remove, t_of, DRIVE_SPEED, DRIVE_DIST

W, H = 3.0, 2.4
COLS, LEVELS = 4, 3
Z = 5.3                    # 车位中心离巷道中心的距离
TRAVEL_SPEED = 100         # 行走 m/min（示意）
LIFT_SPEED = 40            # 升降 m/min（示意）
FORK_SPEED = 30            # 伸叉/拉板 m/min（示意）
TURN_TIME = 8              # 旋转盘转 180° 的时间 s（示意）
BAY = "BAY"


def side_name(side):
    return "前" if side > 0 else "后"


class Stacker(Garage):
    key = "stacker"
    name = "巷道堆垛（2 × 4 列 × 3 层）"
    intro = ("中间巷道里有一台<b>堆垛机</b>：沿轨道行走（X）、载车台升降（Y），再向前/向后伸出取放车板。"
             "<b>行走和升降同时进行</b>，所以一次搬运的时间 = max(行走, 升降)。"
             "这是载车板式：交接区必须先有一块空板，车才能开进来。按钮编号 = 前/后排 + 列-层。")
    camera = {"center": (4, 2.5, 2), "forward": (-0.45, -0.45, -1), "range": 11}
    footprint = (COLS + 1) * W * (2 * Z + 5.2)
    speed_note = f"行走 {TRAVEL_SPEED}、升降 {LIFT_SPEED}、伸叉 {FORK_SPEED} m/min，旋转 {TURN_TIME} s"

    def reset(self):
        self.slot_ids = []
        self.loc = {}
        for side in (1, -1):
            for lv in range(LEVELS):
                for c in range(COLS):
                    sid = f"{side_name(side)}{c + 1}-{lv + 1}"
                    self.slot_ids.append(sid)
                    self.loc[sid] = (side, c, lv)
        self.loc[BAY] = (1, -1, 0)
        self.slot_pallet = {}
        self.home = {}
        self.car = {}
        self.heading = {}
        for k, sid in enumerate(self.slot_ids, start=1):
            self.slot_pallet[sid] = k
            self.home[k] = sid
            self.heading[k] = 0
            self.car[k] = self.new_car()[0] if k % 5 not in (0, 3) else None
        self.slot_pallet[BAY] = None
        self.crane = (0, 0)          # (列, 层)

    def slots(self):
        return list(self.slot_ids)

    def slot_label(self, sid):
        side, c, lv = self.loc[sid]
        return f"{side_name(side)}排第{c + 1}列第{lv + 1}层"

    def has_car(self, sid):
        p = self.slot_pallet[sid]
        return p is not None and self.car[p] is not None

    def car_in(self, sid):
        p = self.slot_pallet[sid]
        return self.car[p] if p is not None else None


    def pos(self, sid):
        side, c, lv = self.loc[sid]
        return (c * W, lv * H + 0.1, side * Z)

    def names(self, pid):
        return [f"P{pid}"] + ([self.car[pid]] if self.car[pid] else [])

    # ---- 堆垛机动作 ----
    def _travel(self, sid, payload, steps, why):
        _, c, lv = self.loc[sid]
        c0, lv0 = self.crane
        if (c, lv) == (c0, lv0):
            return
        dx, dy = (c - c0) * W, (lv - lv0) * H
        tx, ty = t_of(dx, TRAVEL_SPEED), t_of(dy, LIFT_SPEED)
        self.crane = (c, lv)
        acts = []
        if dx:
            acts.append(move(["mast", "carriage"] + payload, (dx, 0, 0), tx))
        if dy:
            acts.append(move(["carriage"] + payload, (0, dy, 0), ty))
        timing = f"行走 {tx:.1f}s、升降 {ty:.1f}s 同时进行，用时取大的 {max(tx, ty):.1f}s" if dx and dy else \
                 (f"只需行走 {tx:.1f}s" if dx else f"只需升降 {ty:.1f}s")
        target = "交接区" if sid == BAY else self.slot_label(sid)
        steps.add(f"堆垛机{why}，开到{target}：{timing}。", *acts)

    def _pull(self, sid, steps):
        pid = self.slot_pallet[sid]
        self.slot_pallet[sid] = None
        side = self.loc[sid][0]
        steps.add(f"货叉伸{'前' if side > 0 else '后'}，把 {pid} 号车板{'（连车）' if self.car[pid] else ''}拉到载车台上。",
                  move(self.names(pid), (0, 0, -side * Z), t_of(Z, FORK_SPEED)))
        return pid

    def _push(self, pid, sid, steps):
        self.slot_pallet[sid] = pid
        side = self.loc[sid][0]
        target = "交接区" if sid == BAY else self.slot_label(sid)
        steps.add(f"把 {pid} 号车板推进{target}。",
                  move(self.names(pid), (0, 0, side * Z), t_of(Z, FORK_SPEED)))

    def _return_bay_pallet(self, steps):
        pid = self.slot_pallet[BAY]
        h = self.home[pid]
        steps.add(f"交接区里停着 {pid} 号空板，它的家在{self.slot_label(h)}。它占着交接区，得先送回去。")
        self._travel(BAY, [], steps, "去交接区")
        self._pull(BAY, steps)
        self._travel(h, self.names(pid), steps, "带着空板")
        self._push(pid, h, steps)

    def park(self, sid, steps):
        bay = self.slot_pallet[BAY]
        if bay is not None and self.home[bay] != sid:
            self._return_bay_pallet(steps)
            bay = None
        if bay is None:
            steps.add(f"交接区没有空板。载车板式的代价：存车前要先把 {self.slot_label(sid)} 的空板取出来送到交接区。")
            self._travel(sid, [], steps, "去取空板")
            pid = self._pull(sid, steps)
            self._travel(BAY, self.names(pid), steps, "带着空板")
            self._push(pid, BAY, steps)
        else:
            steps.add(f"交接区里刚好是 {self.slot_label(sid)} 的空板，车可以直接开进来，省掉一趟。")
        pid = self.slot_pallet[BAY]
        car, idx = self.new_car()
        self.car[pid] = car
        x, y, z = self.pos(BAY)
        steps.add("车开进交接区，停在空板上，司机下车离开。",
                  spawn(car, (x, y, z + DRIVE_DIST), idx), move([car], (0, 0, -DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)))
        self._travel(BAY, [], steps, "回到交接区")
        self._pull(BAY, steps)
        self._travel(sid, self.names(pid), steps, "载着车")
        self._push(pid, sid, steps)

    def retrieve(self, sid, steps):
        if self.slot_pallet[BAY] is not None:
            self._return_bay_pallet(steps)
        self._travel(sid, [], steps, "去取车")
        pid = self._pull(sid, steps)
        self._travel(BAY, self.names(pid), steps, "载着车")
        self._push(pid, BAY, steps)
        self.heading[pid] = (self.heading[pid] + 180) % 360
        steps.add("交接区的旋转盘把车板转 180°，车头朝外，司机可以直接往前开走。",
                  turn(self.names(pid), 180, TURN_TIME))
        car, self.car[pid] = self.car[pid], None
        steps.add(f"车开走。{pid} 号空板留在交接区，下一个来存车的人如果正好分到它的车位，就能省一趟。",
                  move([car], (0, 0, DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)), remove(car))

    # ---- 显示与核对 ----
    def ascii(self):
        cell = lambda sid: ("  --  " if self.slot_pallet[sid] is None else
                            ("[有车]" if self.car[self.slot_pallet[sid]] else "[空板]"))
        lines = []
        for side in (-1, 1):
            lines.append(f"{side_name(side)}排：")
            for lv in reversed(range(LEVELS)):
                row = [cell(f"{side_name(side)}{c + 1}-{lv + 1}") for c in range(COLS)]
                lines.append(f"  {lv + 1}层 " + " ".join(row))
        b = self.slot_pallet[BAY]
        lines.append("交接区：" + ("空（没有车板）" if b is None else f"{b} 号空板（家在 {self.home[b]}）"))
        lines.append(f"堆垛机：第{self.crane[0] + 1 if self.crane[0] >= 0 else '交接'}列 第{self.crane[1] + 1}层")
        lines.append("（-- 表示车板不在，被拿到交接区了）")
        return "\n".join(lines)

    def poses(self):
        p = {}
        for sid, pid in self.slot_pallet.items():
            if pid is not None:
                p[f"P{pid}"] = (self.pos(sid), self.heading[pid])
                if self.car[pid]:
                    p[self.car[pid]] = (self.pos(sid), 0)
        c, lv = self.crane
        p["mast"] = ((c * W, 0, 0), 0)
        p["carriage"] = ((c * W, lv * H + 0.02, 0), 0)
        return p

    def check(self):
        b = self.slot_pallet[BAY]
        missing = [s for s in self.slot_ids if self.slot_pallet[s] is None]
        if b is None:
            assert not missing
        else:
            assert missing == [self.home[b]] and self.car[b] is None

    def build(self, ctx):
        ctx.ground(4, 3, 20, 26)
        bx, _, bz = self.pos(BAY)
        ctx.driveway(bx, bz + 2.5, bz + DRIVE_DIST + 2)
        ctx.box((bx, 0.03, bz), (2.8, 0.04, 2.8), (0.4, 0.4, 0.45))    # 旋转盘
        ctx.text((bx, 1.6, bz + 2.2), "交接区", 14)
        ctx.box((4.5, 0.02, 0), ((COLS + 1.5) * W, 0.04, 0.3), (0.2, 0.2, 0.2))   # 地轨
        top = LEVELS * H
        for side in (1, -1):
            zf, zb = side * (Z - 2.6), side * (Z + 2.6)
            for c in range(-1 if side > 0 else 0, COLS + 1):
                x = (c - 0.5) * W
                for z in (zf, zb):
                    ctx.box((x, top / 2, z), (0.14, top, 0.14))
            for lv in range(1, LEVELS + 1):
                for z in (zf, zb):
                    ctx.box(((COLS - 1) * W / 2, lv * H - 0.05, z), (COLS * W, 0.1, 0.1))
            ctx.text((-1.2 * W, top + 0.4, side * Z), f"{side_name(side)}排", 16)
        c, lv = self.crane
        ctx.part("mast", (c * W, 0, 0), [
            ("box", (-1.4, top / 2 + 0.3, 0), (0.18, top + 0.6, 0.4), (0.9, 0.6, 0.1)),
            ("box", (1.4, top / 2 + 0.3, 0), (0.18, top + 0.6, 0.4), (0.9, 0.6, 0.1)),
            ("box", (0, top + 0.6, 0), (3.0, 0.2, 0.4), (0.9, 0.6, 0.1)),
            ("box", (0, 0.1, 0), (3.0, 0.2, 0.6), (0.9, 0.6, 0.1))])
        ctx.part("carriage", (c * W, lv * H + 0.02, 0), [
            ("box", (0, -0.05, 0), (2.6, 0.08, 5.0), (0.95, 0.75, 0.2)),
            ("label", (0, 0.3, 2.6), "堆垛机")])
        for sid, pid in self.slot_pallet.items():
            if pid is not None:
                ctx.pallet(f"P{pid}", self.pos(sid), tag=self.home[pid].replace(BAY, ""), heading=self.heading[pid])
                if self.car[pid]:
                    ctx.car(self.car[pid], self.pos(sid), int(self.car[pid][3:]))
