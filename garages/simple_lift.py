"""简易升降（两层，2 列）。

每列一块上层车板，由立柱带动升降；下层就是普通地面车位。
上层车板降下来时会占住下层车位，所以：下层停着车，上层的车就下不来。
"""
from garages.base import Garage, move, spawn, remove, t_of, DRIVE_SPEED, DRIVE_DIST

W, H, D = 3.0, 2.1, 5.2
LIFT_SPEED = 6      # 升降 m/min（示意）
COLS = 2
AWAY = DRIVE_DIST + 5   # 下层车临时让开时停的位置（比新车出现的地方更远，免得重叠）


class SimpleLift(Garage):
    key = "simple"
    name = "简易升降（两层）"
    intro = ("每列只有一块能升降的上层车板，下层是普通车位。上层车板要降到地面，就会占住下层车位，"
             "所以<b>下层停着车时，上层的车取不出来</b>，必须先让下层车开走。升降横移正是为了解决这个问题。")
    camera = {"center": (0, 1.6, 2), "forward": (-0.4, -0.35, -1), "range": 6}
    footprint = COLS * W * D
    speed_note = f"升降 {LIFT_SPEED} m/min"

    def reset(self):
        self.upper = {c: None for c in range(COLS)}    # 上层车板上的车
        self.lower = {c: None for c in range(COLS)}    # 下层车位上的车
        for c in range(COLS):
            self.upper[c] = self.new_car()[0]
        self.lower[0] = self.new_car()[0]

    def slots(self):
        return [f"{c}{lv}" for c in range(COLS) for lv in ("上", "下")]

    def slot_label(self, sid):
        return f"第{int(sid[0]) + 1}列{sid[1]}层"

    def slot_short(self, sid):
        return f"{int(sid[0]) + 1}{sid[1]}"

    def _where(self, sid):
        return int(sid[0]), (self.upper if sid[1] == "上" else self.lower)

    def has_car(self, sid):
        c, d = self._where(sid)
        return d[c] is not None

    def car_in(self, sid):
        c, d = self._where(sid)
        return d[c]


    @staticmethod
    def x(c):
        return (c - (COLS - 1) / 2) * W

    def _move_lower_away(self, c, steps):
        car = self.lower[c]
        steps.add(f"第{c + 1}列下层停着车。上层车板一降下来就会压到它，所以必须先把下层的车开走"
                  "（真实情况下要等下层车主来挪车，这正是简易升降最大的缺点）。",
                  move([car], (0, 0, AWAY), t_of(AWAY, DRIVE_SPEED)))
        return car

    def _move_lower_back(self, c, car, steps):
        steps.add("上层的事办完了，下层的车再开回原位。", move([car], (0, 0, -AWAY), t_of(AWAY, DRIVE_SPEED)))

    def _lower_upper(self, c, steps, down):
        names = [f"P{c}"] + ([self.upper[c]] if self.upper[c] else [])
        t = t_of(H, LIFT_SPEED)
        if down:
            steps.add(f"第{c + 1}列上层车板降到地面。", move(names, (0, -H, 0), t))
        else:
            steps.add(f"车板升回上层。", move(names, (0, H, 0), t))

    def retrieve(self, sid, steps):
        c, d = self._where(sid)
        car = d[c]
        tdrive = t_of(DRIVE_DIST, DRIVE_SPEED)
        if d is self.lower:
            d[c] = None
            steps.add("下层车位就在地面上，车直接开走。", move([car], (0, 0, DRIVE_DIST), tdrive), remove(car))
            return
        moved = self._move_lower_away(c, steps) if self.lower[c] else None
        self._lower_upper(c, steps, True)
        self.upper[c] = None
        steps.add("车从上层车板上开走。", move([car], (0, 0, DRIVE_DIST), tdrive), remove(car))
        self._lower_upper(c, steps, False)
        if moved:
            self._move_lower_back(c, moved, steps)

    def park(self, sid, steps):
        c, d = self._where(sid)
        car, _ = self.new_car()
        tdrive = t_of(DRIVE_DIST, DRIVE_SPEED)
        if d is self.lower:
            d[c] = car
            steps.add("车直接开进下层车位。",
                      spawn(car, (self.x(c), 0, DRIVE_DIST), int(car[3:])), move([car], (0, 0, -DRIVE_DIST), tdrive))
            return
        moved = self._move_lower_away(c, steps) if self.lower[c] else None
        self._lower_upper(c, steps, True)
        self.upper[c] = car
        steps.add("车开上降到地面的上层车板。",
                  spawn(car, (self.x(c), 0.1, DRIVE_DIST), int(car[3:])), move([car], (0, 0, -DRIVE_DIST), tdrive))
        self._lower_upper(c, steps, False)
        if moved:
            self._move_lower_back(c, moved, steps)

    def ascii(self):
        f = lambda v: "[车]" if v else "[  ]"
        return ("上层  " + "  ".join(f(self.upper[c]) for c in range(COLS)) + "\n"
                "下层  " + "  ".join(f(self.lower[c]) for c in range(COLS)))

    def poses(self):
        p = {}
        for c in range(COLS):
            p[f"P{c}"] = ((self.x(c), H + 0.1, 0), 0)
            if self.upper[c]:
                p[self.upper[c]] = ((self.x(c), H + 0.1, 0), 0)
            if self.lower[c]:
                p[self.lower[c]] = ((self.x(c), 0, 0), 0)
        return p

    def build(self, ctx):
        ctx.ground(0, 4, 10, 16)
        for c in range(COLS):
            ctx.driveway(self.x(c), 0, DRIVE_DIST + 2)
            for sx in (-1, 1):
                ctx.box((self.x(c) + sx * W * 0.47, 1.4, -D / 2 + 0.2), (0.15, 2.8, 0.15))
            ctx.text((self.x(c), 3.3, -D / 2), f"第{c + 1}列")
        for name, (pos, h) in self.poses().items():
            if name.startswith("P"):
                ctx.pallet(name, pos, tag=f"{int(name[1]) + 1}上", heading=h)
            else:
                ctx.car(name, pos, int(name[3:]), h)
