"""出入口终端：司机视角下，司机唯一能看到、能操作的东西。

画成一块深色"屏幕"，上面是：标题栏（车库名 + 模拟时钟）、提示文字、进度条、
一排大按钮，以及可选的按钮网格（取车时列出车牌，相当于刷卡）。
这个类只管画，不管流程；流程在 main.py 的 driver_* 生成器里。
"""
from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from engine import logbook
from engine.fonts import wrap

SCREEN = (0.09, 0.14, 0.25, 1)
SCREEN_FG = (0.93, 0.95, 1, 1)
DIM_FG = (0.62, 0.68, 0.8, 1)
BAR_BG = (0.22, 0.27, 0.38, 1)
BAR_FG = (0.3, 0.78, 0.45, 1)
PRIMARY = ((0.2, 0.55, 0.95, 1), (0.12, 0.4, 0.8, 1), (0.32, 0.64, 1, 1), (0.4, 0.4, 0.4, 1))
SECOND = ((0.3, 0.36, 0.48, 1), (0.22, 0.27, 0.38, 1), (0.38, 0.45, 0.6, 1), (0.4, 0.4, 0.4, 1))
CHIP = ((0.93, 0.95, 1, 1), (0.75, 0.82, 0.95, 1), (1, 1, 0.85, 1), (0.6, 0.6, 0.6, 1))
MINE = ((1, 0.92, 0.45, 1), (0.9, 0.78, 0.3, 1), (1, 0.96, 0.65, 1), (0.6, 0.6, 0.6, 1))   # 和车顶"您的车"标签同色


def _logged(text, cb):
    def run():
        logbook.note("点击终端按钮 %s" % text)
        cb()
    return run
INSET = 0.03


class Kiosk:
    def __init__(self, parent, font, bold):
        self.font, self.bold = font, bold or font
        self.frame = DirectFrame(parent=parent, frameColor=SCREEN)
        self.title = OnscreenText(parent=self.frame, text="", scale=0.032, align=TextNode.ALeft,
                                  fg=DIM_FG, font=font, mayChange=True)
        self.clock = OnscreenText(parent=self.frame, text="", scale=0.032, align=TextNode.ARight,
                                  fg=DIM_FG, font=font, mayChange=True)
        self.heading = OnscreenText(parent=self.frame, text="", scale=0.048, align=TextNode.ALeft,
                                    fg=SCREEN_FG, font=self.bold, mayChange=True)
        self.body = OnscreenText(parent=self.frame, text="", scale=0.037, align=TextNode.ALeft,
                                 fg=SCREEN_FG, font=font, mayChange=True)
        self.bar_bg = DirectFrame(parent=self.frame, frameColor=BAR_BG)
        self.bar_fg = DirectFrame(parent=self.frame, frameColor=BAR_FG)
        self.bar_txt = OnscreenText(parent=self.frame, text="", scale=0.03, align=TextNode.ALeft,
                                    fg=DIM_FG, font=font, mayChange=True)
        self.buttons = []
        self.chips = []
        self.progress = None
        self.width = 1.0
        self._heading_text = self._body_text = ""

    # ---- 内容 ----
    def show(self, heading, body="", buttons=(), chips=(), progress=None):
        """buttons: [(文字, 回调, 是否主按钮)]；chips: [(文字, 回调[, 是否标黄])]，排成网格；
        progress: None 或 (0~1, 说明)。"""
        self._heading_text, self._body_text = heading, body
        for b in self.buttons + self.chips:
            b.destroy()
        self.buttons = [DirectButton(parent=self.frame, text=t, command=_logged(t, cb), scale=0.042, relief=DGG.FLAT,
                                     frameColor=PRIMARY if main else SECOND, text_fg=(1, 1, 1, 1),
                                     text_font=self.bold if main else self.font, pad=(0.6, 0.38))
                        for t, cb, main in buttons]
        self.chips = [DirectButton(parent=self.frame, text=c[0], command=_logged(c[0], c[1]), scale=0.034,
                                   relief=DGG.FLAT, frameColor=MINE if c[2:] and c[2] else CHIP,
                                   text_fg=(0.1, 0.12, 0.2, 1), text_font=self.font)
                      for c in chips]
        self.set_progress(progress)

    def set_progress(self, progress):
        self.progress = progress
        if progress is None:
            for w in (self.bar_bg, self.bar_fg, self.bar_txt):
                w.hide()
            return
        for w in (self.bar_bg, self.bar_fg, self.bar_txt):
            w.show()
        self.bar_txt.setText(progress[1])
        self._draw_bar()

    def set_header(self, title, clock):
        self.title.setText(title)
        self.clock.setText(clock)

    def _draw_bar(self):
        if self.progress is None or not hasattr(self, "_bar_y"):
            return
        x0, w, y = INSET, self.width - 2 * INSET, self._bar_y
        f = max(0.0, min(1.0, self.progress[0]))
        self.bar_bg["frameSize"] = (x0, x0 + w, y - 0.022, y)
        self.bar_fg["frameSize"] = (x0, x0 + max(0.002, w * f), y - 0.022, y)

    # ---- 排版：屏幕左上角在 (x, top)，宽 width；返回屏幕底边 ----
    def layout(self, x, top, width):
        self.width = width
        self.frame.setPos(x, 0, top)
        inner = width - 2 * INSET
        y = -INSET
        self.title.setPos(INSET, y - 0.032 * 0.9)
        self.clock.setPos(width - INSET, y - 0.032 * 0.9)
        y -= 0.032 * 1.6
        self.heading.setText(wrap(self._heading_text, self.heading.textNode, inner * 0.97 / 0.048))
        self.heading.setPos(INSET, y - 0.048 * 0.95)
        y -= self._height(self.heading) + 0.01
        if self._body_text:
            self.body.setText(wrap(self._body_text, self.body.textNode, inner * 0.97 / 0.037))
            self.body.setPos(INSET, y - 0.037 * 0.95)
            y -= self._height(self.body) + 0.01
        else:
            self.body.setText("")
        if self.progress is not None:
            y -= 0.012
            self._bar_y = y
            self._draw_bar()
            self.bar_txt.setPos(INSET, y - 0.022 - 0.032 * 0.95)
            y -= 0.022 + 0.032 * 1.5
        if self.chips:
            cols = 5
            cw, ch = inner / cols, 0.07
            for i, b in enumerate(self.chips):
                r, c = divmod(i, cols)
                b["frameSize"] = (-cw / 0.034 / 2 + 0.1, cw / 0.034 / 2 - 0.1, -0.62, 1.15)
                b.setPos(INSET + c * cw + cw / 2, 0, y - 0.012 - r * ch - ch / 2)
            y -= ((len(self.chips) + cols - 1) // cols) * ch + 0.02
        if self.buttons:
            bx = INSET
            y -= 0.01
            for b in self.buttons:
                l, r, bot, t = b.getBounds()
                b.setPos(bx - l * 0.042, 0, y - t * 0.042)
                bx += (r - l) * 0.042 + 0.025
            y -= (self.buttons[0].getBounds()[3] - self.buttons[0].getBounds()[2]) * 0.042 + 0.005
        y -= INSET
        self.frame["frameSize"] = (0, width, y, 0)
        return top + y

    @staticmethod
    def _height(ost):
        tn = ost.textNode
        return tn.getNumRows() * tn.getLineHeight() * ost.getScale()[0]
