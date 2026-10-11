"""所有车库类型共用的基类和动作构造函数（不依赖 VPython）。"""
import copy

from engine.motion import step_duration

DRIVE_SPEED = 60      # 车开进/开出的速度，m/min（约 3.6 km/h）
DRIVE_DIST = 9.0      # 车从车道外开到交接位的距离，m


def t_of(dist, speed_m_per_min):
    """按速度算移动时间（秒）。忽略加减速，是示意值。"""
    return abs(dist) / (speed_m_per_min / 60.0)


def move(names, d, t):
    return {"op": "move", "names": list(names), "d": tuple(d), "t": max(t, 0.05)}


def turn(names, deg, t):
    return {"op": "turn", "names": list(names), "deg": deg, "t": t}


def loop(items, path, ds, t):
    return {"op": "loop", "items": items, "path": path, "ds": ds, "t": max(t, 0.05)}


def spawn(name, pos, color, heading=0):
    return {"op": "spawn", "name": name, "pos": tuple(pos), "color": color, "heading": heading, "t": 0}


def remove(name):
    return {"op": "remove", "name": name, "t": 0}


class Steps(list):
    """收集步骤。调用 add 前先改好状态，这样记下的状态图就是"这一步做完之后"的样子。"""

    def __init__(self, garage):
        super().__init__()
        self.g = garage

    def add(self, text, *actions):
        self.append({"text": text, "actions": [a for a in actions if a], "state": self.g.ascii()})


def total_time(steps):
    return sum(step_duration(s) for s in steps)


class Garage:
    key = ""
    name = ""
    intro = ""
    camera = {"center": (0, 3, 0), "forward": (-0.35, -0.3, -1), "range": 8}
    footprint = 1.0          # 占地面积 m²（含必要的车道/交接区，示意）
    speed_note = ""

    def __init__(self):
        self.car_count = 0
        self.reset()

    # ---- 子类必须实现 ----
    def reset(self):
        raise NotImplementedError

    def slots(self):
        """所有车位的编号（按钮顺序）。"""
        raise NotImplementedError

    def has_car(self, sid):
        raise NotImplementedError

    def car_in(self, sid):
        """这个车位上停的是哪辆车（名字），没车返回 None。取车时按车牌找车位用，只读。"""
        raise NotImplementedError

    def park(self, sid, steps):
        raise NotImplementedError

    def retrieve(self, sid, steps):
        raise NotImplementedError

    def ascii(self):
        raise NotImplementedError

    def poses(self):
        """按当前状态，每个可动物体应该在哪：{名字: ((x,y,z), 朝向)}。测试用来核对动画。"""
        raise NotImplementedError

    def build(self, ctx):
        """用 ctx 提供的函数搭出 3D 场景。"""
        raise NotImplementedError

    def check(self):
        """不变量检查，出错时抛 AssertionError。"""

    # ---- 通用 ----
    def slot_label(self, sid):
        return str(sid)

    def slot_short(self, sid):
        """按钮上显示的短编号。"""
        return str(sid)

    def new_car(self):
        self.car_count += 1
        return f"car{self.car_count}", self.car_count

    def request(self, sid):
        steps = Steps(self)
        if self.has_car(sid):
            steps.add(f"任务：取 {self.slot_label(sid)} 的车。")
            self.retrieve(sid, steps)
        else:
            steps.add(f"任务：把一辆车存到 {self.slot_label(sid)}。")
            self.park(sid, steps)
        steps.add("完成。")
        return list(steps)

    def best_empty_slot(self):
        empty = [s for s in self.slots() if not self.has_car(s)]
        if not empty:
            return None
        return min(empty, key=lambda s: total_time(copy.deepcopy(self).request(s)))

    def auto_park(self):
        best = self.best_empty_slot()
        if best is None:
            return [{"text": "车库已满，没有空车位。", "actions": [], "state": self.ascii()}]
        steps = self.request(best)
        steps[0]["text"] = (f"自动选位：把每个空车位都试算一遍，{self.slot_label(best)} 的模拟耗时最短，"
                            f"就存到那里。（这就是最简单的'车位分配策略'）")
        return steps
