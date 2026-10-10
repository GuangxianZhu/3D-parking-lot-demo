"""垂直升降 / 塔库（8 层，每层左右各 1 个车位，载车板式）。

中央电梯井，电梯平台自带旋转盘，底层就是出入口。
所有车都要经过同一台电梯，电梯是唯一的瓶颈。
"""
from garages.base import Garage, move, turn, spawn, remove, t_of, DRIVE_SPEED, DRIVE_DIST

W, H, D = 2.9, 2.2, 5.2
LEVELS = 8                  # 存车层 1..8，0 层是出入口
LIFT_SPEED = 90             # 电梯 m/min（示意）
SHIFT_SPEED = 20            # 横向推拉车板 m/min（示意）
TURN_TIME = 8               # 旋转 180° 用时 s（示意）


class Tower(Garage):
    key = "tower"
    name = "垂直升降 / 塔库（8 层）"
    intro = ("中央是电梯井，每层左右各一个车位，<b>底层电梯就是出入口</b>，电梯平台自带旋转盘。"
             "存车：电梯先去取一块空板下来 → 车开上去 → 电梯升到目标层 → 把车板横推进车位。"
             "所有车都要经过<b>同一台电梯</b>，它是唯一的瓶颈。")
    camera = {"center": (0, 9.5, 3), "forward": (-0.5, -0.25, -1), "range": 13}
    footprint = 3 * W * D
    speed_note = f"电梯 {LIFT_SPEED}、横推 {SHIFT_SPEED} m/min，旋转 {TURN_TIME} s"

    def reset(self):
        self.slot_ids = [f"{lv}{s}" for lv in range(1, LEVELS + 1) for s in ("左", "右")]
        self.slot_pallet, self.home, self.car, self.heading = {}, {}, {}, {}
        for k, sid in enumerate(self.slot_ids, start=1):
            self.slot_pallet[sid] = k
            self.home[k] = sid
            self.heading[k] = 0
            self.car[k] = self.new_car()[0] if k % 4 != 0 else None
        self.lift_lv = 0
        self.lift_p = None

    def slots(self):
        return list(self.slot_ids)

    def slot_label(self, sid):
        return f"{sid[:-1]}层{sid[-1]}侧"

    def has_car(self, sid):
        p = self.slot_pallet[sid]
        return p is not None and self.car[p] is not None

    def lv_side(self, sid):
        return int(sid[:-1]), (-1 if sid[-1] == "左" else 1)

    def pos(self, sid):
        lv, side = self.lv_side(sid)
        return (side * W, lv * H + 0.1, 0)

    def names(self, pid):
        return [f"P{pid}"] + ([self.car[pid]] if self.car[pid] else [])

    def payload(self):
        return self.names(self.lift_p) if self.lift_p else []

    def _lift_to(self, lv, steps, why, rotate=False):
        if lv == self.lift_lv:
            if rotate:
                self._rotate(steps)
            return
        dy = (lv - self.lift_lv) * H
        t = t_of(dy, LIFT_SPEED)
        acts = [move(["lift"] + self.payload(), (0, dy, 0), t)]
        name = lambda k: f"{k} 层" if k else "底层"
        txt = f"电梯{why}，从{name(self.lift_lv)}{'升' if dy > 0 else '降'}到{name(lv)}，用时 {t:.1f}s"
        if rotate:
            self.heading[self.lift_p] = (self.heading[self.lift_p] + 180) % 360
            acts.append(turn(self.payload(), 180, TURN_TIME))
            txt += f"；下降的同时旋转盘把车转 180°（{TURN_TIME}s），让车头朝外"
        self.lift_lv = lv
        steps.add(txt + "。", *acts)

    def _rotate(self, steps):
        self.heading[self.lift_p] = (self.heading[self.lift_p] + 180) % 360
        steps.add("旋转盘把车转 180°，车头朝外。", turn(self.payload(), 180, TURN_TIME))

    def _pull(self, sid, steps):
        pid = self.slot_pallet[sid]
        self.slot_pallet[sid] = None
        self.lift_p = pid
        _, side = self.lv_side(sid)
        steps.add(f"把 {self.slot_label(sid)} 的 {pid} 号车板{'（连车）' if self.car[pid] else '（空板）'}横拉进电梯。",
                  move(self.names(pid), (-side * W, 0, 0), t_of(W, SHIFT_SPEED)))

    def _push(self, sid, steps):
        pid = self.lift_p
        self.slot_pallet[sid] = pid
        self.lift_p = None
        _, side = self.lv_side(sid)
        steps.add(f"把 {pid} 号车板横推进{self.slot_label(sid)}。",
                  move(self.names(pid), (side * W, 0, 0), t_of(W, SHIFT_SPEED)))

    def _return_lift_pallet(self, steps):
        h = self.home[self.lift_p]
        steps.add(f"电梯上还放着 {self.lift_p} 号空板（家在{self.slot_label(h)}），得先把它送回去，电梯才能干别的。")
        self._lift_to(self.lv_side(h)[0], steps, "带着空板")
        self._push(h, steps)

    def park(self, sid, steps):
        lv, _ = self.lv_side(sid)
        if self.lift_p and self.home[self.lift_p] != sid:
            self._return_lift_pallet(steps)
        if self.lift_p is None:
            steps.add(f"载车板式的代价：存车前电梯要先去{self.slot_label(sid)}把空板取下来。")
            self._lift_to(lv, steps, "去取空板")
            self._pull(sid, steps)
        else:
            steps.add(f"电梯上刚好就是{self.slot_label(sid)}的空板，省掉取板这一趟。")
        self._lift_to(0, steps, "带着空板")
        pid = self.lift_p
        car, idx = self.new_car()
        self.car[pid] = car
        steps.add("车从正面开上电梯里的空板，司机下车离开。",
                  spawn(car, (0, 0.1, DRIVE_DIST), idx), move([car], (0, 0, -DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)))
        self._lift_to(lv, steps, "载着车")
        self._push(sid, steps)

    def retrieve(self, sid, steps):
        lv, _ = self.lv_side(sid)
        if self.lift_p:
            self._return_lift_pallet(steps)
        self._lift_to(lv, steps, "去取车")
        self._pull(sid, steps)
        self._lift_to(0, steps, "载着车", rotate=True)
        pid = self.lift_p
        car, self.car[pid] = self.car[pid], None
        steps.add(f"车往前开走。{pid} 号空板留在电梯上，下一个人存车时如果正好分到它的车位，就能省一趟。",
                  move([car], (0, 0, DRIVE_DIST), t_of(DRIVE_DIST, DRIVE_SPEED)), remove(car))

    def ascii(self):
        cell = lambda sid: ("  --  " if self.slot_pallet[sid] is None else
                            ("[有车]" if self.car[self.slot_pallet[sid]] else "[空板]"))
        lines = []
        for lv in reversed(range(0, LEVELS + 1)):
            mid = "电梯" + ("+板" if self.lift_p else "  ") if self.lift_lv == lv else "  │   "
            if lv == 0:
                lines.append(f"底层 {'':6} {mid:^6} {'':6} ← 出入口")
            else:
                lines.append(f"{lv}层  {cell(f'{lv}左')} {mid:^6} {cell(f'{lv}右')}")
        return "\n".join(lines)

    def poses(self):
        p = {}
        for sid, pid in self.slot_pallet.items():
            if pid is not None:
                p[f"P{pid}"] = (self.pos(sid), self.heading[pid])
                if self.car[pid]:
                    p[self.car[pid]] = (self.pos(sid), 0)
        y = self.lift_lv * H
        p["lift"] = ((0, y, 0), 0)
        if self.lift_p:
            p[f"P{self.lift_p}"] = ((0, y + 0.1, 0), self.heading[self.lift_p])
        return p

    def check(self):
        missing = [s for s in self.slot_ids if self.slot_pallet[s] is None]
        if self.lift_p is None:
            assert not missing
        else:
            assert missing == [self.home[self.lift_p]] and self.car[self.lift_p] is None

    def build(self, ctx):
        ctx.ground(0, 4, 14, 18)
        ctx.driveway(0, D / 2, DRIVE_DIST + 2)
        top = (LEVELS + 1) * H
        for x in (-1.5 * W, -0.5 * W, 0.5 * W, 1.5 * W):
            for z in (-D / 2, D / 2):
                ctx.box((x, top / 2, z), (0.14, top, 0.14))
        for lv in range(1, LEVELS + 2):
            for z in (-D / 2, D / 2):
                ctx.box((0, lv * H - 0.05, z), (3 * W, 0.1, 0.1))
            if lv <= LEVELS:
                ctx.text((-1.5 * W - 0.8, lv * H + 0.6, D / 2), f"{lv}层", 13)
        ctx.text((0, 2.0, D / 2 + 1), "出入口", 14)
        for sid, pid in self.slot_pallet.items():
            ctx.pallet(f"P{pid}", self.pos(sid), w=2.5, tag=sid, heading=self.heading[pid])
            if self.car[pid]:
                ctx.car(self.car[pid], self.pos(sid), int(self.car[pid][3:]))
        ctx.part("lift", (0, self.lift_lv * H, 0), [
            ("box", (0, 0, 0), (2.8, 0.06, 5.0), (0.9, 0.6, 0.1)),
            ("cyl", (0, 0.03, 0), (0, 0.04, 0), 1.35, (0.5, 0.5, 0.55)),
            ("label", (0, 0.4, 2.6), "电梯")])
