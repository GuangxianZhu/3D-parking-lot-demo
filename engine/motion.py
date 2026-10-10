"""动作原语的纯数学部分（不依赖 VPython，可单独测试）。

每个"步骤"是一个 dict：
    {"text": 讲解文字, "actions": [动作, ...], "state": 文字版状态图}
同一步里的动作同时开始；每个动作有自己的模拟时长 t（秒），
所以"堆垛机横行 7 秒、升降 5 秒"会真实地体现为升降先结束。

动作种类：
    move  : names 里的物体一起平移 d=(dx,dy,dz)
    turn  : names 里的物体各自绕竖直轴转 deg 度
    loop  : 一组物体沿"跑道形"闭合路径前进 ds（垂直循环的链条）
    spawn : 新建一辆车（瞬间）
    remove: 移除一辆车（瞬间）
"""
import math


def rot_y(v, deg):
    a = math.radians(deg)
    x, y, z = v
    return (x * math.cos(a) + z * math.sin(a), y, -x * math.sin(a) + z * math.cos(a))


def smooth(u):
    """先加速后减速的插值曲线，比匀速看起来更像机械。"""
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def stadium_length(p):
    return 2 * p["h"] + 2 * math.pi * p["r"]


def stadium_point(p, s):
    """跑道形路径上弧长 s 处的点。s=0 在最底部正中，s 增大 = 从正面看逆时针。"""
    r, h, cx, cy, z = p["r"], p["h"], p["cx"], p["cy"], p["z"]
    s %= stadium_length(p)
    q = math.pi * r / 2
    if s < q:
        th = -math.pi / 2 + s / r
        return (cx + r * math.cos(th), cy - h / 2 + r * math.sin(th), z)
    s -= q
    if s < h:
        return (cx + r, cy - h / 2 + s, z)
    s -= h
    if s < math.pi * r:
        th = s / r
        return (cx + r * math.cos(th), cy + h / 2 + r * math.sin(th), z)
    s -= math.pi * r
    if s < h:
        return (cx - r, cy + h / 2 - s, z)
    s -= h
    th = math.pi + s / r
    return (cx + r * math.cos(th), cy - h / 2 + r * math.sin(th), z)


def step_duration(step):
    return max([a.get("t", 0) for a in step["actions"]] + [0])


def poses_at(poses, step, tau):
    """poses: {名字: ((x,y,z), 朝向角)}，为步骤开始时的位姿。返回 tau 秒时的位姿。"""
    out = dict(poses)
    for a in step["actions"]:
        t = a.get("t", 0)
        k = 1.0 if t <= 0 else smooth(tau / t)
        op = a["op"]
        if op == "move":
            dx, dy, dz = a["d"]
            for n in a["names"]:
                (x, y, z), h = out[n]
                out[n] = ((x + dx * k, y + dy * k, z + dz * k), h)
        elif op == "turn":
            for n in a["names"]:
                p, h = out[n]
                out[n] = (p, h + a["deg"] * k)
        elif op == "loop":
            path = a["path"]
            for names, s0 in a["items"]:
                x, y, z = stadium_point(path, s0 + a["ds"] * k)
                for n in names:
                    out[n] = ((x, y - path["hang"], z), out[n][1])
    return out


def apply_step(poses, step):
    """无动画地把一步执行到底（测试用）。"""
    poses = dict(poses)
    for a in step["actions"]:
        if a["op"] == "spawn":
            poses[a["name"]] = (tuple(a["pos"]), a.get("heading", 0))
    poses = poses_at(poses, step, step_duration(step))
    for a in step["actions"]:
        if a["op"] == "remove":
            poses.pop(a["name"], None)
    return poses
