"""运行日志：每次启动在 logs/ 里写一个 txt，出了问题直接把这个文件发过来就行。

记的东西：
- 启动信息：系统、Python、Panda3D 版本、窗口大小、用了哪个字体；
- 每个操作：点了哪个按钮、切换了什么、终端上显示了什么、执行了哪些步骤；
- 所有打印到命令行的内容，包括报错的完整堆栈。
"""
import datetime
import glob
import os
import platform
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")
KEEP = 20            # 只保留最近 20 次的日志
path = None
_file = None


class _Tee:
    """写到命令行的同时也写进日志文件。"""
    def __init__(self, stream):
        self.stream = stream

    def write(self, s):
        if self.stream is not None:
            try:
                self.stream.write(s)
            except Exception:
                pass
        if _file is not None:
            _file.write(s)
            _file.flush()
        return len(s)

    def flush(self):
        if self.stream is not None:
            try:
                self.stream.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


def start():
    """打开日志文件，并把 stdout / stderr 接过来。写不了文件（比如文件夹只读）也不影响程序运行。"""
    global path, _file
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        for old in sorted(glob.glob(os.path.join(LOG_DIR, "run-*.txt")))[:-(KEEP - 1)]:
            os.remove(old)
        path = os.path.join(LOG_DIR, datetime.datetime.now().strftime("run-%Y%m%d-%H%M%S.txt"))
        _file = open(path, "w", encoding="utf-8")
    except OSError as e:
        print("[日志] 无法写日志文件：%s" % e, file=sys.stderr)
        path = _file = None
        return None
    sys.stdout, sys.stderr = _Tee(sys.stdout), _Tee(sys.stderr)
    note("启动  系统 %s | Python %s | 目录 %s" % (platform.platform(), sys.version.split()[0], ROOT))
    print("[日志] 本次运行记录在 %s" % path)
    return path


def note(msg):
    """记一行带时间的事件（只写文件，不打印到命令行）。"""
    if _file is not None:
        t = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        _file.write("%s  %s\n" % (t, re.sub("\1[^\1]*\1|\2", "", msg)))
        _file.flush()
