"""升降横移（3 层 × 3 列）。

1F 只能横移，3F 只能升降，2F 两者都能；1F、2F 各留一个空位。
上层车板要降到地面，它正下方每一层的同一列都必须是空位，所以要先横移让位。
n 列的车库有 3n-2 个车板。
"""
from garages.base import Garage, move, spawn, remove, t_of, DRIVE_SPEED, DRIVE_DIST

W, H, D = 3.0, 2.4, 5.2
LEVELS, COLS = 3, 3
LIFT_SPEED = 6       # 升降 m/min（示意）
SLIDE_SPEED = 8      # 横移 m/min（示意）


class LiftSlide(Garage):
    key = "liftslide"
    name = "升降横移（3 层 × 3 列）"
    intro = ("1F 只能横移，3F 只能升降，2F 两者都能。1F、2F 各留一个<b>空位</b>。"
             "上层车板要降到地面，它正下方每一层的同一列都必须是空位，所以要先<b>横移让位</b>。"
             "注意：没停车的'空车板'不等于'空位'，它照样挡路。")
    camera = {"center": (0, 3.2, 1), "forward": (-0.35, -0.3, -1), "range": 7}
    footprint = COLS * W * D
    speed_note = f"升降 {LIFT_SPEED} m/min，横移 {SLIDE_SPEED} m/min"

    def reset(self):
        self.grid = [[1, None, 2], [3, 4, None], [5, 6, 7]]
        self.car = {}
        for p in range(1, 8):
            if p != 4:
                self.car[p] = self.new_car()[0]
            else:
                self.car[p] = None

    def slots(self):
        return [str(p) for p in range(1, 8)]

    def slot_label(self, sid):
        return f"{sid} 号车板"

    def has_car(self, sid):
        return self.car[int(sid)] is not None

    def locate(self, pid):
        for lv, row in enumerate(self.grid):
            if pid in row:
                return lv, row.index(pid)

    @staticmethod
    def pos(lv, col):
        return ((col - 1) * W, lv * H + 0.1, 0)

    def names(self, pid):
        return [f"P{pid}"] + ([self.car[pid]] if self.car[pid] else [])

    def _shift_gap(self, lv, target, pid, steps):
        row = self.grid[lv]
        gap = row.index(None)
        if gap == target:
            steps.add(f"{lv + 1}F 的空位刚好就在第 {target + 1} 列，这层不用动。")
            return
        if gap < target:
            movers, dx, direction = list(range(gap + 1, target + 1)), -W, "左"
        else:
            movers, dx, direction = list(range(target, gap)), W, "右"
        ids = [row[c] for c in movers]
        new_row = list(row)
        for c in movers:
            new_row[c + (-1 if dx < 0 else 1)] = row[c]
        new_row[target] = None
        self.grid[lv] = new_row
        who = f"车板 {'、'.join(map(str, ids))} 一起" if len(ids) > 1 else f"{ids[0]} 号车板"
        names = [n for p in ids for n in self.names(p)]
        steps.add(f"{lv + 1}F：空位原来在第 {gap + 1} 列。{who}向{direction}横移一格，"
                  f"把空位让到第 {target + 1} 列，给 {pid} 号车板腾出下降通道。",
                  move(names, (dx, 0, 0), t_of(W, SLIDE_SPEED)))

    def _go(self, pid, steps, retrieving):
        lv, col = self.locate(pid)
        tdrive = t_of(DRIVE_DIST, DRIVE_SPEED)
        if lv == 0:
            steps.add(f"{pid} 号车板就在 1F，车可以直接开出/开进，不需要任何车板让位。")
        else:
            below = "1F" if lv == 1 else f"1F 到 {lv}F"
            steps.add(f"{pid} 号车板在 {lv + 1}F 第 {col + 1} 列。要让它降到地面，它下面{below}的第 {col + 1} 列"
                      "都必须是空位。每层只有一个空位，所以逐层检查，必要时横移让位。")
            for k in range(lv):
                self._shift_gap(k, col, pid, steps)
            self.grid[lv][col] = None
            steps.add(f"下降通道已打通，{pid} 号车板从 {lv + 1}F 降到地面。",
                      move(self.names(pid), (0, -lv * H, 0), t_of(lv * H, LIFT_SPEED)))
        x, y, _ = self.pos(0, col)
        if retrieving:
            car, self.car[pid] = self.car[pid], None
            steps.add(f"车从 {pid} 号车板倒车开出。", move([car], (0, 0, DRIVE_DIST), tdrive), remove(car))
        else:
            car, idx = self.new_car()
            self.car[pid] = car
            steps.add(f"车开上 {pid} 号车板。", spawn(car, (x, y, DRIVE_DIST), idx), move([car], (0, 0, -DRIVE_DIST), tdrive))
        if lv > 0:
            self.grid[lv][col] = pid
            steps.add(f"{pid} 号车板升回 {lv + 1}F。下层被横移的车板不用复位，空位留在哪都行。",
                      move(self.names(pid), (0, lv * H, 0), t_of(lv * H, LIFT_SPEED)))

    def retrieve(self, sid, steps):
        self._go(int(sid), steps, True)

    def park(self, sid, steps):
        self._go(int(sid), steps, False)

    def ascii(self):
        lines = []
        for lv in reversed(range(LEVELS)):
            cells = ["  空位  " if p is None else f"[{p}{'车' if self.car[p] else '空'}]" for p in self.grid[lv]]
            lines.append(f"{lv + 1}F  " + " ".join(f"{c:^6}" for c in cells))
        return "\n".join(lines)

    def poses(self):
        p = {}
        for lv in range(LEVELS):
            for col, pid in enumerate(self.grid[lv]):
                if pid:
                    for n in self.names(pid):
                        p[n] = (self.pos(lv, col), 0)
        return p

    def check(self):
        assert self.grid[0].count(None) == 1 and self.grid[1].count(None) == 1
        assert None not in self.grid[2]

    def build(self, ctx):
        ctx.ground(0, 4, 16, 18)
        ctx.driveway(0, 2, 11, 3 * W * 0.95)
        for x in [-1.5 * W, -0.5 * W, 0.5 * W, 1.5 * W]:
            for z in [-D / 2, D / 2]:
                ctx.box((x, LEVELS * H / 2, z), (0.15, LEVELS * H, 0.15))
        for lv in range(1, LEVELS + 1):
            for z in [-D / 2, D / 2]:
                ctx.box((0, lv * H - 0.05, z), (3 * W, 0.12, 0.12))
            ctx.text((-1.5 * W - 1.0, (lv - 1) * H + 0.6, D / 2), f"{lv}F", 16)
        for lv in range(LEVELS):
            for col, pid in enumerate(self.grid[lv]):
                if pid:
                    ctx.pallet(f"P{pid}", self.pos(lv, col), tag=str(pid))
                    if self.car[pid]:
                        ctx.car(self.car[pid], self.pos(lv, col), int(self.car[pid][3:]))
