"""每种车库随机存取上千次，检查两件事：
1. 调度逻辑的不变量（比如升降横移每层空位数）一直成立；
2. 把动作原语"无动画地"执行到底，所有物体的最终位置和逻辑算出来的位置一致
   （这能抓住"逻辑说车板到了 A，动画却把它画到了 B"这类错误）。
运行：python -m tests.test_garages
"""
import math
import random

from engine.motion import apply_step
from garages import ALL


def close(p, q):
    return all(abs(a - b) < 1e-6 for a, b in zip(p, q))


def run(cls, n=1500, seed=0):
    rng = random.Random(seed)
    g = cls()
    poses = g.poses()
    times = {"park": [], "retrieve": []}
    from garages.base import total_time
    for _ in range(n):
        r = rng.random()
        if r < 0.25:
            steps = g.auto_park()
            kind = "park"
        else:
            sid = rng.choice(g.slots())
            kind = "retrieve" if g.has_car(sid) else "park"
            steps = g.request(sid)
        for st in steps:
            for a in st["actions"]:
                for nm in a.get("names", []):
                    assert nm in poses or any(x["op"] == "spawn" and x["name"] == nm for x in st["actions"]), (cls.name, nm)
            poses = apply_step(poses, st)
        times[kind].append(total_time(steps))
        g.check()
        want = g.poses()
        assert set(want) == set(poses), (cls.name, set(want) ^ set(poses))
        for k, (p, h) in want.items():
            assert close(p, poses[k][0]), (cls.name, k, p, poses[k][0])
            if not k.startswith("car"):
                assert abs((h - poses[k][1]) % 360) < 1e-6, (cls.name, k, h, poses[k][1])
            poses[k] = (p, poses[k][1])   # 消除浮点累积误差
    return times


if __name__ == "__main__":
    for cls in ALL:
        t = run(cls)
        avg = lambda xs: sum(xs) / len(xs) if xs else float("nan")
        print(f"OK  {cls.name:28s} 平均存车 {avg(t['park']):6.1f}s  平均取车 {avg(t['retrieve']):6.1f}s")
