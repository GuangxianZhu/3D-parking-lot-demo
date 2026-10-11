"""立体车库原理演示：6 种车库，一个程序（Panda3D 窗口版）。

运行：
    pip install -r requirements.txt
    python main.py
会打开一个独立窗口。鼠标左键或右键拖动旋转视角，滚轮缩放，中键拖动平移。
快捷键：空格 = 暂停/继续，N = 下一步（单步模式）。
"""
import copy
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

from engine import logbook
from engine.fonts import ACCENT, color_grid, load_fonts, register_styles, rich, spaced, wrap
from engine.kiosk import Kiosk
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
MODE_ON = ((0.2, 0.45, 0.85, 1), (0.15, 0.38, 0.75, 1), (0.28, 0.52, 0.92, 1), (0.8, 0.8, 0.8, 1))
PROVINCES = "京沪粤苏浙川鄂湘鲁豫"
PLATE_CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"


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

        import panda3d
        logbook.note("Panda3D %s | 窗口 %dx%d" % (panda3d.__version__, self.win.getXSize(), self.win.getYSize()))
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
        self.mode = "driver"        # driver = 司机视角（出入口终端）；lab = 原理演示（直接点车位）
        self.choice = None          # 终端上按了哪个按钮
        self.plates = {}            # 车名 → 车牌
        self.parked_at = {}         # 车名 → 存入时刻（模拟时钟，分钟）
        self.mine = set()           # 司机（用户）自己存进来的车；其余是其他车主的
        self.clock_min = 8 * 60
        self.rng = random.Random()
        self.intro_open = False
        self.entrance_pos = None

        self._build_toolbar()
        self._build_panel()
        self._build_compare()
        self._bind_mouse()
        self.accept("space", self.on_pause)
        self.accept("n", self.on_next)

        self.switch(0)
        self.set_mode("driver")
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
        x = self._flow(bar, x, y1, OnscreenText(parent=bar, text="模式", scale=0.042,
                                                  align=TextNode.ALeft))
        self.mode_btns = {}
        for key, text in (("driver", "司机视角"), ("lab", "原理演示")):
            b = self._button(bar, text, self.set_mode, extraArgs=[key])
            self.mode_btns[key] = b
            x = self._flow(bar, x, y1, b, 0.008)
        x += 0.04
        for text, cmd in (("重置", lambda: self.submit(("switch", self.garage_idx))),
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
        x = self._flow(bar, x, y2, self.speed_txt, 0.04)
        self.pause_btn = self._button(bar, "暂停 ‖", self.on_pause)
        x = self._flow(bar, x, y2, self.pause_btn, 0.06)
        # 下面这些只在"原理演示"模式里出现
        self.lab_widgets = []
        for text, cmd in (("自动选位存车", lambda: self.submit(("auto",))),
                          ("随机取一辆", lambda: self.submit(("random_out",)))):
            b = self._button(bar, text, cmd)
            x = self._flow(bar, x, y2, b)
            self.lab_widgets.append(b)
        self.step_box = DirectCheckButton(parent=bar, text="单步模式", scale=0.042, relief=DGG.FLAT,
                                          frameColor=(0, 0, 0, 0), boxPlacement="left",
                                          boxRelief=DGG.SUNKEN, pad=(0.2, 0.2))
        x = self._flow(bar, x + 0.02, y2, self.step_box)
        nb = self._button(bar, "下一步 ▶", self.on_next)
        self._flow(bar, x, y2, nb)
        self.lab_widgets += [self.step_box, nb]

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
        self.intro_btn = DirectButton(parent=self.panel, text="", scale=0.032, relief=DGG.FLAT,
                                      frameColor=(0, 0, 0, 0), text_fg=ACCENT, text_align=TextNode.ARight,
                                      command=self.toggle_intro)
        self.kiosk = Kiosk(self.panel, self.body_font, self.bold_font)
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
        self.intro_btn["text"] = "收起说明 ▲" if self.intro_open else "看原理说明 ▼"
        self.intro_btn.setPos(-GAP - CARD_PAD, 0, y - CARD_PAD - 0.05 * 0.95)
        y = self._put(self.title_txt, y - CARD_PAD)
        if self.intro_open:
            self.intro_txt.show()
            y = self._put(self.intro_txt, y - 0.024)
        else:
            self.intro_txt.hide()
        y -= CARD_PAD
        self._place_card("intro", top, y)
        # 中间卡片：司机视角是出入口终端，原理演示是车位按钮
        top = y = y - GAP
        y = self._put_header(self.slot_hdr, self.slot_hint, y - CARD_PAD) - 0.01
        if self.mode == "driver":
            y = self.kiosk.layout(x0, y - 0.005, INNER_W) - CARD_PAD
        else:
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

    def entrance(self):
        """车从哪里开进来：在副本上试存一辆车，找 spawn 动作的位置。车库满了返回 None。"""
        g = self.garage
        empty = [s for s in g.slots() if not g.has_car(s)]
        if not empty:
            return None
        steps = copy.deepcopy(g).request(empty[0])
        return next(a["pos"] for st in steps for a in st["actions"] if a["op"] == "spawn")

    def set_camera(self, kind):
        cam = self.garage.camera
        f = to_panda(VIEWS.get(kind, cam["forward"])).normalized()
        center, dist = to_panda(cam["center"]), cam["range"] / math.tan(math.radians(FOV / 2))
        if self.mode == "driver" and self.entrance_pos is not None:
            # 司机视角：镜头往入口那边挪一点、拉远一点，让等在门口的车也在画面里
            e = to_panda(self.entrance_pos)
            gap = (Vec3(e.x, e.y, center.z) - center).length()
            center = center * 0.7 + Vec3(e.x, e.y, center.z) * 0.3
            dist += gap * 0.3
        self.cam_state = {
            "center": center,
            # VPython 的 range 是中心到画面边缘的距离，换成相机离中心多远
            "dist": dist,
            "h": math.degrees(math.atan2(-f.x, f.y)),
            "p": math.degrees(math.asin(max(-1, min(1, f.z)))),
        }
        self._apply_camera()

    # ================= 控件回调 =================
    def submit(self, cmd):
        logbook.note("操作 %s%s" % (cmd, "（忙，忽略）" if self.job is not None else ""))
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

    def toggle_intro(self):
        self.intro_open = not self.intro_open
        self.relayout()

    def set_mode(self, mode):
        logbook.note("切换模式 %s%s" % (mode, "（忙，忽略）" if self.job is not None else ""))
        if self.job is not None:
            self.notice = "\1red\1正在执行任务，做完再切换模式。\2"
            self.render_log()
            return
        self.mode = mode
        for key, b in self.mode_btns.items():
            b["frameColor"] = MODE_ON if key == mode else BTN["frameColor"]
            b["text_fg"] = (1, 1, 1, 1) if key == mode else BTN["text_fg"]
        lab = mode == "lab"
        for w in self.lab_widgets + [b for _, b in self.slot_buttons]:
            w.show() if lab else w.hide()
        self.kiosk.frame.hide() if lab else self.kiosk.frame.show()
        self.intro_open = lab
        self.set_camera("默认")
        if lab:
            self.slot_hdr.setText("车位")
            self.slot_hint.setText("绿色 = 有车。点一下：有车就取，没车就存到这里")
            self.log = ["点车位按钮或“自动选位存车”开始。"]
        else:
            self.slot_hdr.setText("出入口终端")
            self.slot_hint.setText("你是司机，按屏幕提示操作")
            self.log = ["在右边的出入口终端上点“我要存车”开始。"]
            self.kiosk_idle()
        self.log_hint.setText("")
        self.relayout()

    def choose(self, value):
        self.choice = value

    def wait_choice(self):
        """生成器：等用户在终端上按一个按钮，返回按钮对应的值。"""
        self.choice = None
        while self.choice is None:
            yield
        return self.choice

    def on_pause(self):
        self.ctl.paused = not self.ctl.paused
        logbook.note("暂停" if self.ctl.paused else "继续")
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
        logbook.note("切换车库 %s" % ALL[i].name)
        self.garage_idx = i
        self.menu.set(i, fCommand=0)
        self.cmp_frame.hide()
        self.ctx.clear()
        for _, b in self.slot_buttons:
            b.destroy()
        g = self.garage = ALL[i]()
        g.build(self.ctx)
        self.ctx.finish()
        self.entrance_pos = self.entrance()
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
        # 已经停在库里的车：随机给车牌和存入时刻
        self.rng = random.Random(i)
        self.clock_min = 8 * 60
        self.plates, self.parked_at, self.mine = {}, {}, set()
        for _, name in self.cars_in_garage():
            self.plates[name] = self.new_plate()
            self.parked_at[name] = self.clock_min - self.rng.randint(30, 600)
        if self.mode == "driver":
            for _, b in self.slot_buttons:
                b.hide()
        self.title_txt.setText(g.name)
        self._set_wrapped(self.intro_txt, rich(g.intro))
        self.log = (["点车位按钮或“自动选位存车”开始。"] if self.mode == "lab" else
                    ["在右边的出入口终端上点“我要存车”开始。"])
        self.log_hint.setText("")
        self.notice = ""
        self.grid_txt.setText(color_grid(g.ascii()))
        if self.mode == "driver":
            self.kiosk_idle()
        self.show_stats()

    def run_steps(self, steps, kind, driver=None):
        """播放一串步骤。driver=(park|pick, 车名, 车位) 时是司机视角：
        车开进来、开出去这两步是司机自己的动作，要等用户在终端上确认；其余是设备动作，自动播放。"""
        self.log = []
        total, done = total_time(steps), 0.0
        playback = lambda: PLAYBACK_BASE * self.speed_value()
        for i, s in enumerate(steps, 1):
            self.log_hint.setText(f"第 {i}/{len(steps)} 步")
            d = step_duration(s)
            logbook.note("  步骤 %d/%d [%.1fs] %s" % (i, len(steps), d, s["text"]))
            self.log.append(f"{len(self.log) + 1}. {s['text']}" + (f" \1grey\1[{d:.1f}s]\2" if d else ""))
            self.render_log()
            ops = {a["op"] for a in s["actions"]}
            if driver:
                what, name, sid = driver
                bar = (done / total if total else 1, f"已用 {done:.0f} 秒 / 预计 {total:.0f} 秒（模拟时间）")
                if what == "park" and "spawn" in ops:
                    self._kiosk("请把车开进交接区", "停稳、熄火、拉好手刹，带上随身物品下车。"
                                "确认车里没人后，设备才会开始动作。",
                                [("已停好，下车离开", lambda: self.choose(1), True)], progress=bar)
                    yield from self.wait_choice()
                elif what == "pick" and "remove" in ops:
                    self._kiosk("您的车已到出口", "车头已经朝外，请上车直接开走。",
                                [("上车驶离", lambda: self.choose(1), True)], progress=bar)
                    yield from self.wait_choice()
                elif s["actions"]:
                    parked = any(a["op"] == "spawn" for st in steps[:i - 1] for a in st["actions"])
                    head = ("正在为您取车" if what == "pick" else
                            "正在存车，请离开交接区" if parked else "设备准备中，请稍候")
                    self._kiosk(head, s["text"], progress=bar)
            elif self.step_box["indicatorValue"] and s["actions"]:
                self.ctl.next = False
                self.render_log("\1b\1（单步模式：点“下一步”或按 N 执行这一步）\2")
                while not self.ctl.next:
                    yield
                self.render_log()
            # 播放这一步，同时推进终端上的进度条
            gen, tau = self.ctx.play(s, playback, self.ctl), 0.0
            try:
                next(gen)
                while True:
                    dt = yield
                    if not self.ctl.paused:
                        tau = min(d, tau + playback() * (dt or 0))
                    if driver and self.kiosk.progress is not None and total:
                        self.kiosk.set_progress(((done + tau) / total,
                                                 f"已用 {done + tau:.0f} 秒 / 预计 {total:.0f} 秒（模拟时间）"))
                    gen.send(dt)
            except StopIteration:
                pass
            done += d
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

    # ================= 司机视角 =================
    def clock_text(self, minutes=None):
        m = int(self.clock_min if minutes is None else minutes) % (24 * 60)
        return f"{m // 60:02d}:{m % 60:02d}"

    def new_plate(self):
        used = set(self.plates.values())
        while True:
            p = (self.rng.choice(PROVINCES) + self.rng.choice("ABCDEFG") + "·"
                 + "".join(self.rng.choice(PLATE_CHARS) for _ in range(5)))
            if p not in used:
                return p

    def cars_in_garage(self):
        """[(车位, 车名)]，按车位顺序。"""
        g = self.garage
        return [(sid, g.car_in(sid)) for sid in g.slots() if g.has_car(sid)]

    def kiosk_header(self):
        self.kiosk.set_header(f"出入口终端 · {self.garage.name}", self.clock_text())

    def sync_plates(self):
        """原理演示模式里存取的车没有车牌，回到司机视角时补上；已经开走的车去掉。"""
        cars = {name for _, name in self.cars_in_garage()}
        for name in cars - set(self.plates):
            self.plates[name] = self.new_plate()
            self.parked_at.setdefault(name, self.clock_min - self.rng.randint(30, 600))
        for name in set(self.plates) - cars:
            self.plates.pop(name)
            self.parked_at.pop(name, None)
        self.mine &= cars
        for name in self.mine:          # 原理演示模式里车被搬过、标签丢了的话补回来
            self.ctx.tag(name, f"您的车 {self.plates[name]}", replace=False)

    def kiosk_idle(self):
        self.sync_plates()
        g = self.garage
        empty = sum(not g.has_car(s) for s in g.slots())
        self.kiosk_header()
        body = f"剩余空位 {empty}/{len(g.slots())}。存车时系统自动分配车位，取车时刷卡（这里选车牌）即可。"
        if self.mine:
            body += "\n您存的车：" + "、".join(self.my_cars_text())
        logbook.note("终端 欢迎使用立体车库 | " + body.replace("\n", " / "))
        self.kiosk.show("欢迎使用立体车库", body,
                        buttons=[("我要存车", lambda: self.submit(("drv_park",)), True),
                                 ("我要取车", lambda: self.submit(("drv_pick",)), True)])
        self.relayout()

    def my_cars_text(self):
        g = self.garage
        return [f"{self.plates[name]}（{g.slot_label(sid)}）" for sid, name in self.cars_in_garage()
                if name in self.mine]

    def _kiosk(self, heading, body="", buttons=(), chips=(), progress=None):
        if progress is None or not buttons:     # 进度条每一步都会刷新，不用每次都记
            logbook.note("终端 %s | %s" % (heading, body.replace("\n", " / ")))
        self.kiosk_header()
        self.kiosk.show(heading, body, buttons, chips, progress)
        self.relayout()

    def driver_park(self):
        g = self.garage
        if all(g.has_car(s) for s in g.slots()):
            self._kiosk("车位已满", "抱歉，现在没有空车位，请稍后再来。", [("返回", lambda: self.choose(1), True)])
            yield from self.wait_choice()
            self.kiosk_idle()
            return
        self.clock_min += self.rng.randint(3, 25)
        # 先在副本上试算：系统会分配哪个车位、车从哪里开进来。真正确认后才改车库状态
        sid = g.best_empty_slot()
        trial = copy.deepcopy(g)
        steps = trial.request(sid)
        arrive = next(a for st in steps for a in st["actions"] if a["op"] == "spawn")
        name, plate = arrive["name"], self.new_plate()
        self.plates[name] = plate
        x, y, z = arrive["pos"]
        self.ctx.car(name, (x, y, z), int(name[3:]), arrive.get("heading", 0))   # 停在入口车道上等候
        self.ctx.tag(name, f"您的车 {plate}")
        self.log = [f"一辆车开到入口，摄像头识别车牌 {plate}。"]
        self.render_log()
        self._kiosk("车辆已到达",
                    f"识别车牌：{plate}\n车型检测：长 4.0 m，宽 1.7 m，高 1.45 m，合格。\n要把车存进来吗？",
                    [("确认存车", lambda: self.choose("ok"), True), ("取消", lambda: self.choose("no"), False)])
        if (yield from self.wait_choice()) == "no":
            self.ctx.remove(name)
            self.plates.pop(name, None)
            self.log = ["司机取消了存车，车开走了。"]
            self.kiosk_idle()
            return
        steps = g.request(sid)
        self.parked_at[name] = self.clock_min
        self.ctx.highlight(pos=g.poses()[name][0])
        t = total_time(steps)
        self._kiosk(f"已为您分配：{g.slot_label(sid)}", f"预计用时 {t:.0f} 秒。目标车位已在画面里用黄色框标出。")
        yield from self.run_steps(steps, "park", driver=("park", name, sid))
        self.ctx.clear_highlight()
        self.mine.add(name)             # 车上的"您的车"标签留着，取车时一眼就能在画面里找到
        self.clock_min += t / 60
        self._kiosk("存车完成，请保管好凭证",
                    f"车牌　{plate}\n车位　{g.slot_label(sid)}\n存入　{self.clock_text(self.parked_at[name])}"
                    f"\n用时　{t:.0f} 秒（模拟）",
                    [("完成", lambda: self.choose(1), True)])
        yield from self.wait_choice()
        self.kiosk_idle()

    def driver_pick(self):
        g = self.garage
        cars = self.cars_in_garage()
        if not cars:
            self._kiosk("车库是空的", "现在库里没有车。", [("返回", lambda: self.choose(1), True)])
            yield from self.wait_choice()
            self.kiosk_idle()
            return
        self.clock_min += self.rng.randint(20, 240)       # 模拟：过了一段时间，车主回来取车
        # 自己的车排在前面、用黄色标出（和画面里车顶的"您的车"标签同色）；其余是其他车主的车
        cars.sort(key=lambda c: c[1] not in self.mine)
        chips = [(self.plates.get(name, name), (lambda s=sid: self.choose(s)), name in self.mine)
                 for sid, name in cars]
        if self.mine:
            body = ("您存的车：" + "、".join(self.my_cars_text()) + "\n黄色的是您的车，画面里车顶也有黄色标签。"
                    "白色的是其他车主的车，演示时也可以点。")
        else:
            body = ("您还没有存过车。下面是其他车主的车（启动时就在库里），演示时可以任选一辆，"
                    "相当于替那位车主刷卡。")
        self._kiosk("请刷卡取车", body, chips=chips,
                    buttons=[("返回", lambda: self.choose("back"), False)])
        sid = yield from self.wait_choice()
        if sid == "back":
            self.kiosk_idle()
            return
        name = g.car_in(sid)
        plate = self.plates.get(name, name)
        self.ctx.tag(name, f"您的车 {plate}" if name in self.mine else f"取车 {plate}")
        self.ctx.highlight(follow=name)
        steps = g.request(sid)
        t = total_time(steps)
        self._kiosk(f"正在为您取车：{plate}", f"车在{g.slot_label(sid)}，预计 {t:.0f} 秒后到出口。")
        yield from self.run_steps(steps, "retrieve", driver=("pick", name, sid))
        self.ctx.clear_highlight()
        self.clock_min += t / 60
        stay = self.clock_min - self.parked_at.pop(name, self.clock_min)
        self.plates.pop(name, None)
        self.mine.discard(name)
        self._kiosk("取车完成，一路顺风",
                    f"车牌　{plate}\n停车　{int(stay // 60)} 小时 {int(stay % 60)} 分（模拟）\n等车　{t:.0f} 秒",
                    [("完成", lambda: self.choose(1), True)])
        yield from self.wait_choice()
        self.kiosk_idle()

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
        elif cmd[0] == "drv_park":
            yield from self.driver_park()
        elif cmd[0] == "drv_pick":
            yield from self.driver_pick()

    def tick(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.1)    # 拖动窗口等造成的长卡顿不要让动画一下跳过去
        self._update_drag()
        self.ctx.pulse(task.time)
        if self.win.hasSize():
            # 标签的字号按窗口高度缩放（以 820 像素高为基准）：高分屏上界面变大了，标签也要跟着变大
            ys = self.win.getYSize()
            px_h = ys * (self.view_top - self.view_bottom)
            k = max(1.0, ys / 820)
            self.ctx.update_labels(self.camera, k * 2 * math.tan(math.radians(self.camLens.getFov()[1] / 2)) / px_h)
        try:
            if self.job is None and self.cmds:
                self.notice = ""
                logbook.note("开始 %s" % (self.cmds[0],))
                self.job = self.make_job(self.cmds.pop(0))
                next(self.job)
            elif self.job is not None:
                self.job.send(dt)
        except StopIteration:
            self.job = None
            self.render_log()          # 任务结束：取消"当前步骤"的高亮
            logbook.note("结束，车库状态：\n" + self.garage.ascii())
        except Exception:
            logbook.note("出错：")
            traceback.print_exc()
            self.job = None
        return task.cont


if __name__ == "__main__":
    logbook.start()
    try:
        App().run()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise
    finally:
        if logbook.path:
            print("[日志] 本次运行记录在 %s ，遇到问题把这个文件发过来。" % logbook.path)
