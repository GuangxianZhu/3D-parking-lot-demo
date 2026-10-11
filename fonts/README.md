# 自带字体

Panda3D 自带的字体没有汉字。为了不依赖电脑上装了哪些中文字体，这里放了思源黑体（Noto Sans CJK SC）的子集：

| 文件 | 用途 |
|---|---|
| NotoSansSC-Regular.otf | 界面文字 |
| NotoSansSC-Bold.otf | 标题、强调 |
| NotoSansMonoCJKsc-Regular.otf | 状态图、对比表（等宽，才能对齐） |

子集只保留了 ASCII、中文标点符号、GB2312 一级常用汉字（3755 个），以及本仓库代码里出现过的所有字符，所以每个文件只有 1~2 MB。
如果以后加的文字里有生僻字，`tests/test_scene.py` 里的 `test_bundled_font_covers_repo_text` 会报出来。

来源：https://github.com/notofonts/noto-cjk ，SIL Open Font License 1.1，见 OFL.txt。
