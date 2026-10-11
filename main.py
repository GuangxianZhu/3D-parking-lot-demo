"""立体车库原理演示：6 种车库，一个程序（Panda3D 窗口版）。

运行：
    pip install -r requirements.txt
    python main.py
会打开一个独立窗口。鼠标左键或右键拖动旋转视角，滚轮缩放，中键拖动平移。
快捷键：空格 = 暂停/继续，N = 下一步（单步模式）。
"""
import math
import random
import traceback
import unicodedata

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import (DirectButton, DirectCheckButton, DirectFrame, DirectOptionMenu,
                                  DirectSlider)
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (AmbientLight, AntialiasAttrib, ClockObject, DirectionalLight,
                          GraphicsPipeSelection, TextNode, Vec3, WindowProperties, loadPrcFileData)

from engine.fonts import ACCENT, color_grid, load_fonts, register_styles, rich, spaced, wrap
from engine.motion import step_duration
from engine.scene import Ctx, to_panda
from garages import ALL
from garages.base import total_time

PLAYBACK_BASE = 10    # 速度 1x 时，1 秒真实时间播放 10 秒模拟时间

loadPrcFileData("", """
framebuffer-multisample 1
multisamples 4
sync-video 1
show-frame-rate-meter 0
audio-library-name null
""")

# ---- 版面（单位是 aspect2d：窗口高度 = 2） ----
TOOLBAR_H = 0.25          # 顶部工具栏高度
PANEL_W = 1.40            # 右侧说明栏宽度
PAD = 0.035
LOG_H = 0.46              # 3D 画面下方"执行步骤"条的高度
GAP = 0.018               # 说明栏里卡片之间的间距
CARD_PAD = 0.024          # 卡片内边距
STRIPE = 0.009            # 卡片左边那条蓝色竖线的宽度
CARD_BG = (1, 1, 1, 1)
GRID_BG = (0.955, 0.96, 0.97, 1)
BG = (0.92, 0.94, 0.97, 1)
BAR_BG = (0.83, 0.86, 0.91, 1)
PANEL_BG = (0.9, 0.915, 0.94, 1)
BTN = dict(relief=DGG.FLAT, frameColor=((0.97, 0.97, 0.98, 1), (0.75, 0.82, 0.95, 1),
                                        (0.88, 0.92, 1, 1), (0.8, 0.8, 0.8, 1)),
           pad=(0.35, 0.3), text_fg=(0.1, 0.1, 0.1, 1), pressEffect=1)
SLOT_FULL = ((0.75, 0.9, 0.75, 1), (0.55, 0.8, 0.55, 1), (0.82, 0.95, 0.82, 1), (0.8, 0.8, 0.8, 1))
SLOT_EMPTY = ((0.95, 0.95, 0.95, 1), (0.75, 0.82, 0.95, 1), (0.88, 0.92, 1, 1), (0.8, 0.8, 0.8, 1))
INNER_W = PANEL_W - 2 * GAP - STRIPE - 2 * CARD_PAD    # 卡片里文字的可用宽度
SLOT_COLS = 6
VIEWS = {"正面": (0, -0.12, -1), "侧面": (-1, -0.15, -0.05), "俯视": (0, -1, -0.25)}
FOV = 50


def text_width(s):
    """等宽字体里的显示宽度：汉字等全角字符算 2，英文数字算 1。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s, w, right=False):
    gap = " " * max(0, w - text_width(s))
    return gap + s if right else s + gap


class Ctl:
    paused = False
    next = False


def pick_window_size(w=1360, h=820):
    """默认 1360×820；屏幕小（比如 1366×768 的笔记本）就缩小一点，免得窗口超出屏幕。"""
    try:
        pipe = GraphicsPipeSelection.getGlobalPtr().makeDefaultPipe()
        dw, dh = pipe.getDisplayWidth(), pipe.getDisplayHeight()
    except Exception:
        dw = dh = 0
    if dw > 0 and dh > 0:
        w, h = min(w, int(dw * 0.95)), min(h, int(dh * 0.85))
    return w, h


class App(ShowBase):
    def __init__(self):
        loadPrcFileData("", "win-size %d %d" % pick_window_size())
        ShowBase.__init__(self)
        props = WindowProperties()
        props.setTitle("立体车库原理演示")
        self.win.requestProperties(props)
        self.disableMouse()
        self.setBackgroundColor(*BG)
        self.render.setAntialias(AntialiasAttrib.MMultisample)

        self.ui_font, self.mono_font, self.bold_font = load_fonts()
        if self.ui_font:
            DGG.setDefaultFont(self.ui_font)
            TextNode.setDefaultFont(self.ui_font)
        self.body_font = spaced(self.ui_font, 1.5)      # 说明栏正文：行距加大
        self.grid_font = spaced(self.mono_font, 1.3)
        register_styles(self.bold_font)
        self._lights()

        self.ctx = Ctx(self.render, self.ui_font)
        self.ctl = Ctl()
        self.cmds = []
        self.job = None
        self.garage = None
        self.garage_idx = 0
        self.slot_buttons = []
        self.history = {"park": [], "retrieve": []}
        self.log = []
        self.notice = ""
        self.cam_state = None
        self.drag = None
        self.view_right, self.view_top, self.view_bottom, self.view_w = 0.6, 0.9, 0.2, 1.8

        self._build_toolbar()
        self._build_panel()
        self._build_compare()
        self._bind_mouse()
        self.accept("space", self.on_pause)
        self.accept("n", self.on_next)

        self.switch(0)
        self.windowEvent(self.win)
        self.taskMgr.add(self.tick, "tick")

    # ================= 场景外观 =================
    def _lights(self):
        amb = AmbientLight("amb")
        amb.setColor((0.5, 0.5, 0.52, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        for hpr, c in (((-35, -50, 0), 0.65), ((140, -30, 0), 0.25)):
            d = DirectionalLight("sun")
            d.setColor((c, c, c, 1))
            np = self.render.attachNewNode(d)
            np.setHpr(*hpr)
            self.render.setLight(np)

    def windowEvent(self, win):
        """窗口大小变了：3D 画面只占左下那一块，镜头宽高比要跟着改。"""
        ShowBase.windowEvent(self, win)
        if win != self.win or not self.win.hasSize():
            return
        w, h = self.win.getXSize(), self.win.getYSize()
        if h == 0:
            return
        aspect = w / h
        right = max(0.3, 1 - PANEL_W / (2 * aspect))
        top, bottom = 1 - TOOLBAR_H / 2, LOG_H / 2
        self.cam.node().getDisplayRegion(0).setDimensions(0, right, bottom, top)
        self.camLens.setAspectRatio((w * right) / (h * (top - bottom)))
        self.camLens.setMinFov(FOV)
        self.view_right, self.view_top, self.view_bottom = right, top, bottom
        self.view_w = 2 * aspect - PANEL_W          # 3D 画面的宽度（aspect2d 单位）
        if getattr(self, "garage", None) is not None:
            self.relayout()                          # 宽度变了，步骤条要重新折行

    # ================= 顶部工具栏 =================
    def _flow(self, parent, x, y, widget, gap=0.02):
        """把控件从左往右排：放在 x 处，返回下一个控件的 x。"""
        s = widget.getScale()[0]
        if isinstance(widget, OnscreenText):
            widget.setPos(x, y)
            return x + widget.textNode.getWidth() * s + gap
        l, r, _, _ = widget.getBounds()
        widget.setPos(x - l * s, 0, y)
        return x + (r - l) * s + gap

    def _button(self, parent, text, cmd, scale=0.042, **kw):
        opts = dict(BTN)
        opts.update(kw)
        return DirectButton(parent=parent, text=text, command=cmd, scale=scale, **opts)

    def _build_toolbar(self):
        bar = DirectFrame(parent=self.a2dTopLeft, frameColor=BAR_BG,
                          frameSize=(0, 20, -TOOLBAR_H, 0))
        y1, y2 = -0.085, -0.195
        x = PAD
        x = self._flow(bar, x, y1, OnscreenText(parent=bar, text="立体车库原理演示", scale=0.055,
                                                  align=TextNode.ALeft, fg=(0.1, 0.15, 0.3, 1),
                                                  ), 0.06)
        x = self._flow(bar, x, y1, OnscreenText(parent=bar, text="车库类型", scale=0.042,
                                                  align=TextNode.ALeft))
        self.menu = DirectOptionMenu(parent=bar, items=[c.name for c in ALL], initialitem=0,
                                     command=self.on_menu, scale=0.042, relief=DGG.FLAT,
                                     frameColor=(1, 1, 1, 1), highlightColor=(0.75, 0.82, 0.95, 1),
                                     item_frameColor=(1, 1, 1, 1), popupMarker_scale=0.6,
                                     pad=(0.35, 0.3))
        # 下拉框的边框要到第一帧之后才按最长的选项撑开，这里直接按最长选项算宽度
        self.menu.setPos(x + 0.015, 0, y1)
        x += (self.menu.maxWidth + 1.6) * 0.042 + 0.05
        for text, cmd in (("自动选位存车", lambda: self.submit(("auto",))),
                          ("随机取一辆", lambda: self.submit(("random_out",))),
                          ("重置", lambda: self.submit(("switch", self.garage_idx))),
                          ("对比 6 种车库", lambda: self.submit(("compare",)))):
            x = self._flow(bar, x, y1, self._button(bar, text, cmd))

        x = PAD
        x = self._flow(bar, x, y2, OnscreenText(parent=bar, text="视角", scale=0.042,
                                                  align=TextNode.ALeft))
        for k in ("默认", "正面", "侧面", "俯视"):
            x = self._flow(bar, x, y2, self._button(bar, k, self.set_camera, extraArgs=[k]))
        x = self._flow(bar, x + 0.04, y2, OnscreenText(parent=bar, text="速度", scale=0.042,
                                                         align=TextNode.ALeft))
        self.speed = DirectSlider(parent=bar, range=(0.25, 4), value=1, pageSize=0.25, scale=0.22,
                                  frameSize=(-1, 1, -0.08, 0.08), frameColor=(0.7, 0.72, 0.78, 1),
                                  thumb_relief=DGG.FLAT, thumb_frameColor=(0.2, 0.4, 0.75, 1),
                                  thumb_frameSize=(-0.05, 0.05, -0.12, 0.12),
                                  command=self.on_speed)
        self.speed.setPos(x + 0.24, 0, y2 + 0.014)       # 滑块的边界框算不准，手动摆
        x += 0.5
        self.speed_txt = OnscreenText(parent=bar, text="1x", scale=0.042, align=TextNode.ALeft,
                                      mayChange=True)
        x = self._flow(bar, x, y2, self.speed_txt, 0.07)
        self.step_box = DirectCheckButton(parent=bar, text="单步模式", scale=0.042, relief=DGG.FLAT,
                                          frameColor=(0, 0, 0, 0), boxPlacement="left",
                                          boxRelief=DGG.SUNKEN, pad=(0.2, 0.2))
        x = self._flow(bar, x, y2, self.step_box)
        x = self._flow(bar, x, y2, self._button(bar, "下一步 ▶", self.on_next))
        self.pause_btn = self._button(bar, "暂停 ‖", self.on_pause)
        self._flow(bar, x, y2, self.pause_btn)

    # ================= 右侧说明栏 =================
    def _text(self, scale, font=None, fg=(0.12, 0.12, 0.14, 1)):
        return OnscreenText(parent=self.panel, text="", scale=scale, align=TextNode.ALeft,
                            fg=fg, font=font or self.body_font, mayChange=True)

    def _header(self, text):
        return OnscreenText(parent=self.panel, text=text, scale=0.042, align=TextNode.ALeft, fg=ACCENT,
                            font=self.bold_font or self.ui_font, mayChange=True)

    @staticmethod
    def _set_wrapped(ost, text, width=INNER_W):
        """按卡片宽度自动折行后再显示（留 3% 余量给粗体字）。"""
        ost.setText(wrap(text, ost.textNode, width * 0.97 / ost.getScale()[0]))

    def _build_panel(self):
        """右侧说明栏：几张白色卡片从上往下排——说明、车位、当前状态、执行步骤，最下面是统计。"""
        self.panel = DirectFrame(parent=self.a2dTopRight, frameColor=PANEL_BG,
                                 frameSize=(-PANEL_W, 0, -2, -TOOLBAR_H))
        self.cards = {}
        # 执行步骤放在 3D 画面正下方：看动画时眼睛不用跑到右边去找说明，而且横向更宽、折行更少
        self.log_strip = DirectFrame(parent=self.a2dBottomLeft, frameColor=PANEL_BG)
        for name in ("intro", "slots", "grid", "stats", "log"):
            parent = self.log_strip if name == "log" else self.panel
            card = DirectFrame(parent=parent, frameColor=CARD_BG)
            stripe = DirectFrame(parent=parent, frameColor=ACCENT)
            self.cards[name] = (card, stripe)
        self.grid_bg = DirectFrame(parent=self.panel, frameColor=GRID_BG)
        self.x0 = -PANEL_W + GAP + STRIPE + CARD_PAD
        self.title_txt = OnscreenText(parent=self.panel, text="", scale=0.05, align=TextNode.ALeft,
                                      fg=(0.08, 0.12, 0.25, 1), font=self.bold_font or self.ui_font,
                                      mayChange=True)
        self.intro_txt = self._text(0.037)
        self.slot_hdr = self._header("车位")
        self.slot_hint = self._text(0.032, fg=(0.42, 0.42, 0.45, 1))
        self.slot_hint.setText("绿色 = 有车。点一下：有车就取，没车就存到这里")
        self.grid_hdr = self._header("当前状态")
        self.grid_hint = self._text(0.032, fg=(0.42, 0.42, 0.45, 1))
        self.grid_hint.setText("\1car\1■\2 有车　\1empty\1■\2 空")
        self.grid_txt = self._text(0.037, font=self.grid_font, fg=(0.2, 0.2, 0.22, 1))
        self.log_hdr = self._header("执行步骤")
        self.log_hint = self._text(0.032, fg=(0.42, 0.42, 0.45, 1))
        self.log_txt = self._text(0.036)
        for ost in (self.log_hdr, self.log_hint, self.log_txt):
            ost.reparentTo(self.log_strip)
        self.stats_txt = self._text(0.035)

    @staticmethod
    def _height(ost):
        tn = ost.textNode
        return tn.getNumRows() * tn.getLineHeight() * ost.getScale()[0]

    def _place_card(self, name, top, bottom, left=-PANEL_W + GAP, right=-GAP):
        card, stripe = self.cards[name]
        card["frameSize"] = (left, right, bottom, top)
        stripe["frameSize"] = (left, left + STRIPE, bottom, top)

    def _put(self, ost, y, x=None):
        """把一段文字的第一行顶边放在 y，返回这段文字的底边。"""
        sc = ost.getScale()[0]
        ost.setPos(self.x0 if x is None else x, y - sc * 0.95)
        return y - self._height(ost) + sc * 0.25

    def _put_header(self, hdr, hint, y, x=None):
        x = self.x0 if x is None else x
        hdr.setPos(x, y - 0.042 * 0.95)
        hint.setPos(x + hdr.textNode.getWidth() * 0.042 + 0.03, y - 0.042 * 0.95)
        return y - 0.042 * 1.35

    def relayout(self):
        """按各段文字的实际行数从上往下排，日志卡片占用剩下的空间。"""
        x0 = self.x0
        # 说明
        top = y = -TOOLBAR_H - GAP
        y = self._put(self.title_txt, y - CARD_PAD) - 0.024
        y = self._put(self.intro_txt, y) - CARD_PAD
        self._place_card("intro", top, y)
        # 车位按钮
        top = y = y - GAP
        y = self._put_header(self.slot_hdr, self.slot_hint, y - CARD_PAD) - 0.01
        bw, bh = INNER_W / SLOT_COLS, 0.072
        for i, (_, b) in enumerate(self.slot_buttons):
            r, c = divmod(i, SLOT_COLS)
            b.setPos(x0 + c * bw + bw / 2, 0, y - r * bh - bh / 2 - 0.012)
        y -= math.ceil(len(self.slot_buttons) / SLOT_COLS) * bh + CARD_PAD
        self._place_card("slots", top, y)
        # 当前状态
        top = y = y - GAP
        y = self._put_header(self.grid_hdr, self.grid_hint, y - CARD_PAD) - 0.012
        gtop = y
        y = self._put(self.grid_txt, y - 0.018) - 0.012
        self.grid_bg["frameSize"] = (x0 - 0.012, -GAP - CARD_PAD + 0.012, y, gtop)
        # 统计（贴底）；状态卡片往下撑到统计卡片上面，不留空白
        bottom = -2 + GAP
        stats_top = bottom + self._height(self.stats_txt) - 0.035 * 0.25 + 2 * CARD_PAD
        self._put(self.stats_txt, stats_top - CARD_PAD)
        self._place_card("stats", stats_top, bottom)
        self._place_card("grid", top, min(y - CARD_PAD, stats_top - GAP))
        # 执行步骤：3D 画面下方的横条
        self.log_strip["frameSize"] = (0, self.view_w, 0, LOG_H)
        lx = GAP + STRIPE + CARD_PAD
        self._place_card("log", LOG_H - GAP * 0.5, GAP, GAP, self.view_w - GAP * 0.5)
        y = self._put_header(self.log_hdr, self.log_hint, LOG_H - GAP * 0.5 - CARD_PAD, lx) - 0.008
        self.log_top, self.log_bottom = y, GAP + CARD_PAD * 0.6
        self.log_txt.setPos(lx, y - 0.036 * 0.95)
        self.log_w = self.view_w - lx - GAP - CARD_PAD
        self.render_log()

    def render_log(self, extra=""):
        """日志放不下时，从最早的一条开始省略，保证最新的几步总能看到。
        正在执行的那一步用深蓝粗体，做完的步骤变灰，眼睛一下就能找到"现在到哪了"。"""
        tn = self.log_txt.textNode
        rows_fit = max(1, int((self.log_top - self.log_bottom) / (tn.getLineHeight() * 0.036)))
        n = len(self.log)
        styled = []
        for i, line in enumerate(self.log):
            if self.job is not None and i == n - 1:
                styled.append("\1cur\1▶ " + line + "\2")
            elif self.job is not None:
                styled.append("\1done\1" + line + "\2")
            else:
                styled.append(line)
        lines = ([self.notice] if self.notice else []) + styled + ([extra] if extra else [])
        skip = 0
        while True:
            shown = lines[skip:]
            text = ("\1grey\1（前 %d 步已省略）\2\n" % skip if skip else "") + "\n".join(shown)
            self._set_wrapped(self.log_txt, text, self.log_w)
            if tn.getNumRows() <= rows_fit or len(shown) <= 1:
                break
            skip += 1

    # ================= 对比表（盖在画面上的弹出框） =================
    def _build_compare(self):
        self.cmp_frame = DirectFrame(parent=self.aspect2d, frameColor=(1, 1, 1, 1), relief=DGG.RIDGE, borderWidth=(0.01, 0.01),
                                     frameSize=(-1.5, 1.5, -0.62, 0.62), pos=(0, 0, -0.05))
        self.cmp_txt = OnscreenText(parent=self.cmp_frame, text="", scale=0.04, align=TextNode.ALeft,
                                    font=self.mono_font, fg=(0.1, 0.1, 0.1, 1), pos=(-1.42, 0.5),
                                    mayChange=True)
        self._button(self.cmp_frame, "关闭", self.cmp_frame.hide, pos=(1.38, 0, 0.53))
        self.cmp_frame.hide()

    # ================= 相机：轨道式，绕一个中心点转 =================
    def _bind_mouse(self):
        for btn, mode in (("mouse1", "orbit"), ("mouse3", "orbit"), ("mouse2", "pan")):
            self.accept(btn, self._drag_start, [mode])
            self.accept(btn + "-up", self._drag_end)
        self.accept("wheel_up", self._zoom, [0.9])
        self.accept("wheel_down", self._zoom, [1 / 0.9])

    def _in_view(self):
        if not self.mouseWatcherNode.hasMouse():
            return False
        m = self.mouseWatcherNode.getMouse()
        return (m.x + 1) / 2 < self.view_right and self.view_bottom < (m.y + 1) / 2 < self.view_top

    def _drag_start(self, mode):
        if self._in_view() and self.cmp_frame.isHidden():
            m = self.mouseWatcherNode.getMouse()
            self.drag = (mode, m.x, m.y)

    def _drag_end(self):
        self.drag = None

    def _zoom(self, k):
        if self._in_view() and self.cam_state:
            self.cam_state["dist"] = min(200, max(2, self.cam_state["dist"] * k))
            self._apply_camera()

    def _update_drag(self):
        if not self.drag or not self.mouseWatcherNode.hasMouse():
            return
        mode, x0, y0 = self.drag
        m = self.mouseWatcherNode.getMouse()
        dx, dy = m.x - x0, m.y - y0
        self.drag = (mode, m.x, m.y)
        cs = self.cam_state
        if mode == "orbit":
            cs["h"] -= dx * 120
            cs["p"] = max(-89, min(5, cs["p"] + dy * 80))
        else:
            q = self.camera.getQuat()
            k = cs["dist"] * 0.5
            cs["center"] -= q.getRight() * dx * k + q.getUp() * dy * k
        self._apply_camera()

    def _apply_camera(self):
        cs = self.cam_state
        h, p = math.radians(cs["h"]), math.radians(cs["p"])
        fwd = Vec3(-math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p))
        self.camera.setPos(cs["center"] - fwd * cs["dist"])
        self.camera.setHpr(cs["h"], cs["p"], 0)

    def set_camera(self, kind):
        cam = self.garage.camera
        f = to_panda(VIEWS.get(kind, cam["forward"])).normalized()
        self.cam_state = {
            "center": to_panda(cam["center"]),
            # VPython 的 range 是中心到画面边缘的距离，换成相机离中心多远
            "dist": cam["range"] / math.tan(math.radians(FOV / 2)) * 1.0,
            "h": math.degrees(math.atan2(-f.x, f.y)),
            "p": math.degrees(math.asin(max(-1, min(1, f.z)))),
        }
        self._apply_camera()

    # ================= 控件回调 =================
    def submit(self, cmd):
        if self.job is not None:
            self.notice = "\1red\1正在执行上一个任务，请稍等。\2"
            self.render_log()
            return
        self.cmds.append(cmd)

    def on_menu(self, _item):
        idx = self.menu.selectedIndex
        if self.job is not None:
            self.menu.set(self.garage_idx, fCommand=0)    # 正在执行时不允许切换，把菜单拨回去
        self.submit(("switch", idx))

    def on_pause(self):
        self.ctl.paused = not self.ctl.paused
        self.pause_btn["text"] = "继续 ▶" if self.ctl.paused else "暂停 ‖"

    def on_next(self):
        self.ctl.next = True

    def speed_value(self):
        return round(self.speed["value"] * 4) / 4

    def on_speed(self):
        self.speed_txt.setText(f"{self.speed_value():g}x")

    # ================= 显示 =================
    def refresh_buttons(self):
        for sid, b in self.slot_buttons:
            full = self.garage.has_car(sid)
            b["text"] = self.garage.slot_short(sid) + (" ●" if full else " ○")
            b["frameColor"] = SLOT_FULL if full else SLOT_EMPTY

    def show_grid(self, text):
        self.grid_txt.setText(color_grid(text))
        self.relayout()

    def show_stats(self, last=None):
        h = self.history
        avg = lambda xs: f"{sum(xs) / len(xs):.1f}s" if xs else "—"
        cars = sum(self.garage.has_car(s) for s in self.garage.slots())
        s = f"在库 \1b\1{cars}/{len(self.garage.slots())}\2 辆"
        if last is not None:
            s += f"　　本次耗时 \1b\1{last:.1f}s\2"
        s += f"　　平均存车 \1b\1{avg(h['park'])}\2　平均取车 \1b\1{avg(h['retrieve'])}\2"
        s += f"\n\1grey\1速度是示意值：{self.garage.speed_note}\2"
        self._set_wrapped(self.stats_txt, s)
        self.relayout()

    # ================= 命令（都是生成器：每帧推进一点，不阻塞窗口） =================
    def switch(self, i):
        self.garage_idx = i
        self.menu.set(i, fCommand=0)
        self.cmp_frame.hide()
        self.ctx.clear()
        for _, b in self.slot_buttons:
            b.destroy()
        g = self.garage = ALL[i]()
        g.build(self.ctx)
        self.ctx.finish()
        self.set_camera("默认")
        self.slot_buttons = []
        bw = INNER_W / SLOT_COLS
        for sid in g.slots():
            b = DirectButton(parent=self.panel, text=sid, scale=0.036, relief=DGG.FLAT,
                             frameSize=(-bw / 0.036 / 2 + 0.08, bw / 0.036 / 2 - 0.08, -0.62, 1.15),
                             text_fg=(0.1, 0.1, 0.1, 1), command=self.submit,
                             extraArgs=[("slot", sid)])
            self.slot_buttons.append((sid, b))
        self.refresh_buttons()
        self.history = {"park": [], "retrieve": []}
        self.title_txt.setText(g.name)
        self._set_wrapped(self.intro_txt, rich(g.intro))
        self.log = ["点车位按钮或“自动选位存车”开始。"]
        self.log_hint.setText("")
        self.notice = ""
        self.grid_txt.setText(color_grid(g.ascii()))
        self.show_stats()

    def run_steps(self, steps, kind):
        self.log = []
        for i, s in enumerate(steps, 1):
            self.log_hint.setText(f"第 {i}/{len(steps)} 步")
            d = step_duration(s)
            self.log.append(f"{len(self.log) + 1}. {s['text']}" + (f" \1grey\1[{d:.1f}s]\2" if d else ""))
            self.render_log()
            if self.step_box["indicatorValue"] and s["actions"]:
                self.ctl.next = False
                self.render_log("\1b\1（单步模式：点“下一步”或按 N 执行这一步）\2")
                while not self.ctl.next:
                    yield
                self.render_log()
            yield from self.ctx.play(s, lambda: PLAYBACK_BASE * self.speed_value(), self.ctl)
            self.show_grid(s["state"])
        t = total_time(steps)
        if kind:
            self.history[kind].append(t)
        self.refresh_buttons()
        self.show_stats(t)

    def compare(self):
        self.cmp_txt.setText("正在计算……")
        self.cmp_frame.show()
        yield                      # 先让"正在计算"显示出来
        head = ["类型", "车位数", "占地m²", "每100m²车位", "平均存车s", "平均取车s", "最慢取车s"]
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
            rows.append([cls.name, str(cap), f"{g.footprint:.0f}", f"{cap / g.footprint * 100:.1f}",
                         f"{avg(times['park']):.1f}", f"{avg(times['retrieve']):.1f}",
                         f"{max(times['retrieve']):.1f}"])
            yield                  # 每算完一种让窗口刷新一下，不会卡住
        widths = [max(text_width(r[i]) for r in rows + [head]) for i in range(len(head))]
        fmt = lambda r: "  ".join(pad(c, widths[i], right=i > 0) for i, c in enumerate(r))
        lines = ["\1b\1" "6 种车库对比（各随机存取 200 次）\2", "", fmt(head),
                 "-" * (sum(widths) + 2 * (len(widths) - 1))] + [fmt(r) for r in rows]
        lines += ["", "\1grey\1注意：各类型规模不同（2 到 24 个车位），速度和占地都是示意值，",
                  "只适合看趋势，不代表真实产品。占地没算车道和坡道。\2"]
        self.cmp_txt.setText("\n".join(lines))

    def make_job(self, cmd):
        g = self.garage
        if cmd[0] == "switch":
            self.switch(cmd[1])
        elif cmd[0] == "slot":
            kind = "retrieve" if g.has_car(cmd[1]) else "park"
            yield from self.run_steps(g.request(cmd[1]), kind)
        elif cmd[0] == "auto":
            has_empty = any(not g.has_car(s) for s in g.slots())
            yield from self.run_steps(g.auto_park(), "park" if has_empty else None)
        elif cmd[0] == "random_out":
            full = [s for s in g.slots() if g.has_car(s)]
            if full:
                yield from self.run_steps(g.request(random.choice(full)), "retrieve")
            else:
                self.log = ["车库是空的。"]
                self.render_log()
        elif cmd[0] == "compare":
            yield from self.compare()

    def tick(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.1)    # 拖动窗口等造成的长卡顿不要让动画一下跳过去
        self._update_drag()
        if self.win.hasSize():
            px_h = self.win.getYSize() * self.view_top
            self.ctx.update_labels(self.camera, 2 * math.tan(math.radians(self.camLens.getFov()[1] / 2)) / px_h)
        try:
            if self.job is None and self.cmds:
                self.notice = ""
                self.job = self.make_job(self.cmds.pop(0))
                next(self.job)
            elif self.job is not None:
                self.job.send(dt)
        except StopIteration:
            self.job = None
            self.render_log()          # 任务结束：取消"当前步骤"的高亮
        except Exception:
            traceback.print_exc()
            self.job = None
        return task.cont


if __name__ == "__main__":
    App().run()
