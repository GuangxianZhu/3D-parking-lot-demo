"""立体车库原理演示：6 种车库，一个程序。

运行：
    pip install vpython
    python main.py
会自动打开浏览器页面。鼠标右键拖动旋转视角，滚轮缩放。
"""
import random

from vpython import canvas, vector, rate, button, slider, checkbox, wtext, menu

from engine.motion import step_duration
from engine.scene import Ctx, V
from garages import ALL
from garages.base import total_time

PLAYBACK_BASE = 10    # 速度 1x 时，1 秒真实时间播放 10 秒模拟时间

scene = canvas(title="", width=1000, height=580, background=vector(0.92, 0.94, 0.97))
ctx = Ctx(scene)


class Ctl:
    paused = False
    next = False
    busy = False


ctl = Ctl()
cmds = []
garage = None
garage_idx = 0
slot_buttons = []
history = {"park": [], "retrieve": []}


def submit(cmd):
    if ctl.busy:
        msg.text = "<b style='color:#c00'>正在执行上一个任务，请稍等。</b><br>" + msg.text.split("<br>", 1)[-1]
        return
    cmds.append(cmd)


def on_pause(b):
    ctl.paused = not ctl.paused
    b.text = "继续 ▶" if ctl.paused else "暂停 ⏸"


def on_next(_):
    ctl.next = True


def set_camera(kind):
    cam = garage.camera
    scene.center = V(cam["center"])
    scene.range = cam["range"]
    scene.forward = V({"默认": cam["forward"], "正面": (0, -0.12, -1),
                       "侧面": (-1, -0.15, -0.05), "俯视": (0, -1, -0.25)}[kind])


def on_speed(s):
    speed_txt.text = f" {s.value:g}x "


# ---------- 标题区：固定控件 ----------
# VPython 的标题/说明区默认 white-space:pre，不会自动换行；这里改成可换行
scene.append_to_title("<style>.glowscript > div {white-space: pre-wrap !important; max-width: 1000px;}</style>")
scene.append_to_title("<h2 style='margin:6px 0'>立体车库原理演示</h2>")
scene.append_to_title("车库类型 ")
def on_menu(m):
    if ctl.busy:
        m.index = garage_idx          # 正在执行时不允许切换，把菜单拨回去
    submit(("switch", m.index))


type_menu = menu(choices=[c.name for c in ALL], index=0, bind=on_menu, pos=scene.title_anchor)
scene.append_to_title("  ")
button(text="自动选位存车", bind=lambda b: submit(("auto",)), pos=scene.title_anchor)
button(text="随机取一辆", bind=lambda b: submit(("random_out",)), pos=scene.title_anchor)
button(text="重置", bind=lambda b: submit(("switch", garage_idx)), pos=scene.title_anchor)
button(text="对比 6 种车库", bind=lambda b: submit(("compare",)), pos=scene.title_anchor)
scene.append_to_title("<br>视角 ")
for k in ("默认", "正面", "侧面", "俯视"):
    button(text=k, bind=lambda b, k=k: set_camera(k), pos=scene.title_anchor)
scene.append_to_title("　速度")
speed = slider(min=0.25, max=4, value=1, step=0.25, length=150, bind=on_speed, pos=scene.title_anchor)
speed_txt = wtext(text=" 1x ", pos=scene.title_anchor)
step_box = checkbox(text="单步模式 ", checked=False, bind=lambda c: None, pos=scene.title_anchor)
button(text="下一步 ▶", bind=on_next, pos=scene.title_anchor)
button(text="暂停 ⏸", bind=on_pause, pos=scene.title_anchor)
scene.append_to_title("<br><b>车位</b>（● 表示有车。点一下：有车就取，没车就存到这里）<br>")

# ---------- 说明区 ----------
intro_txt = wtext(text="")
scene.append_to_caption("<br>")
grid_txt = wtext(text="")
msg = wtext(text="")
scene.append_to_caption("<br>")
stats_txt = wtext(text="")
scene.append_to_caption("<br>")
compare_txt = wtext(text="")


def refresh_buttons():
    for sid, b in slot_buttons:
        b.text = garage.slot_short(sid) + (" ●" if garage.has_car(sid) else " ○")


def show_grid(text):
    grid_txt.text = f"<pre style='font-size:14px;margin:4px 0'>{text}</pre>"


def show_stats(last=None):
    avg = lambda xs: f"{sum(xs) / len(xs):.1f}s" if xs else "—"
    cars = sum(garage.has_car(s) for s in garage.slots())
    s = f"<b>在库</b> {cars}/{len(garage.slots())} 辆　"
    if last is not None:
        s += f"<b>本次模拟耗时</b> {last:.1f}s　"
    s += f"平均存车 {avg(history['park'])}，平均取车 {avg(history['retrieve'])}"
    s += f"<br><span style='color:#777'>速度是示意值：{garage.speed_note}</span>"
    stats_txt.text = s


def switch(i):
    global garage, garage_idx, slot_buttons, history
    garage_idx = i
    ctx.clear()
    for _, b in slot_buttons:
        b.delete()
    garage = ALL[i]()
    garage.build(ctx)
    set_camera("默认")
    slot_buttons = []
    for sid in garage.slots():
        b = button(text=sid, bind=lambda b, sid=sid: submit(("slot", sid)), pos=scene.title_anchor)
        slot_buttons.append((sid, b))
    refresh_buttons()
    history = {"park": [], "retrieve": []}
    intro_txt.text = (f"<div style='max-width:980px'><h3 style='margin:4px 0'>{garage.name}</h3>"
                      f"{garage.intro}</div>")
    show_grid(garage.ascii())
    msg.text = "点车位按钮或'自动选位存车'开始。"
    show_stats()


def run(steps, kind):
    log = []

    def render(extra=""):
        msg.text = "<div style='max-width:980px'>" + "<br>".join(log) + extra + "</div>"

    for s in steps:
        d = step_duration(s)
        log.append(f"{len(log) + 1}. {s['text']}" + (f" <span style='color:#888'>[{d:.1f}s]</span>" if d else ""))
        render()
        if step_box.checked and s["actions"]:
            ctl.next = False
            render("<br><i style='color:#06c'>（单步模式：点“下一步”执行这一步）</i>")
            while not ctl.next:
                rate(30)
            render()
        ctx.play(s, lambda: PLAYBACK_BASE * speed.value, ctl)
        show_grid(s["state"])
    t = total_time(steps)
    if kind:
        history[kind].append(t)
    refresh_buttons()
    show_stats(t)


def compare():
    compare_txt.text = "正在计算……"
    rows = []
    for cls in ALL:
        rng = random.Random(1)
        g = cls()
        times = {"park": [], "retrieve": []}
        for _ in range(200):
            full = [s for s in g.slots() if g.has_car(s)]
            if rng.random() < 0.5 and len(full) < len(g.slots()):
                times["park"].append(total_time(g.auto_park()))
            elif full:
                times["retrieve"].append(total_time(g.request(rng.choice(full))))
        cap = len(g.slots())
        avg = lambda xs: sum(xs) / len(xs)
        rows.append(f"<tr><td>{cls.name}</td><td>{cap}</td><td>{g.footprint:.0f}</td>"
                    f"<td>{cap / g.footprint * 100:.1f}</td><td>{avg(times['park']):.1f}</td>"
                    f"<td>{avg(times['retrieve']):.1f}</td><td>{max(times['retrieve']):.1f}</td></tr>")
    compare_txt.text = (
        "<h3 style='margin:6px 0'>6 种车库对比（各随机存取 200 次）</h3>"
        "<table border=1 cellpadding=4 style='border-collapse:collapse'>"
        "<tr><th>类型</th><th>车位数</th><th>占地 m²</th><th>每 100 m² 车位</th>"
        "<th>平均存车 s</th><th>平均取车 s</th><th>最慢取车 s</th></tr>" + "".join(rows) + "</table>"
        "<span style='color:#777'>注意：各类型规模不同（2 到 24 个车位），速度和占地都是示意值，"
        "只适合看趋势，不代表真实产品。占地没算车道和坡道。</span>")


switch(0)
while True:
    rate(30)
    if not cmds:
        continue
    cmd = cmds.pop(0)
    ctl.busy = True
    try:
        if cmd[0] == "switch":
            switch(cmd[1])
        elif cmd[0] == "slot":
            kind = "retrieve" if garage.has_car(cmd[1]) else "park"
            run(garage.request(cmd[1]), kind)
        elif cmd[0] == "auto":
            has_empty = any(not garage.has_car(s) for s in garage.slots())
            run(garage.auto_park(), "park" if has_empty else None)
        elif cmd[0] == "random_out":
            full = [s for s in garage.slots() if garage.has_car(s)]
            if full:
                run(garage.request(random.choice(full)), "retrieve")
            else:
                msg.text = "车库是空的。"
        elif cmd[0] == "compare":
            compare()
    finally:
        ctl.busy = False
