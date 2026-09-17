#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build.py —— 把 Markdown 学习包编译成一个静态网站（输出到 ../docs/）

用法：
    .\\run.cmd ..\\site\\build.py

产出：
    docs/index.html          首页（hero + 卡片 + README 正文）
    docs/p1-01.html ...      每个文档一页
    docs/assets/             样式、脚本、搜索索引、代码高亮
    docs/search-index.js     全文搜索索引（内联成 JS，file:// 也能用）

为什么输出到 docs/：
    GitHub Pages 可以直接选 "main 分支 / docs 目录" 来发布，不用另外配置。

设计要点：
    · 自动把文档里 `.md` 的交叉引用改写成站内链接，并尽量跳转到对应小节
    · 搜索索引按「小节」切分，所以搜索结果能精确定位到某个 h2
    · 无需联网：字体、图标、脚本全部内联或本地
"""

import html
import os
import re
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    import markdown
    from markdown.extensions.toc import slugify
except ImportError:
    print('[错误] 缺少 markdown 库。装它：')
    print('       .\\run.cmd -m pip install markdown pygments')
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════
#  站点配置
# ══════════════════════════════════════════════════════════════════════════

SITE_TITLE = '羽毛球 AI 教练'
SITE_SUB = '多 agent 协作 · YOLO · 运动骨架分析'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
SITE = os.path.join(ROOT, 'site')
OUT = os.path.join(ROOT, 'docs')

# 分组：(id, 显示名, 说明)
GROUPS = [
    ('A', '路线 A · 多 agent 协作', '怎么指挥一支 AI 队伍'),
    ('B', '路线 B · YOLO 与骨架分析', '怎么做出羽毛球动作分析'),
    ('C', '代码与资料', '能跑的代码、调研笔记、agent 预设'),
]

# 页面清单：(slug, 源文件, 侧栏标题, 分组, 卡片简介)
PAGES = [
    # ── 路线 A ──────────────────────────────────────────────────────────
    ('p1-01', 'part1-多agent协作/01-为什么需要多agent.md',
     '为什么需要多 agent', 'A',
     '单 agent 的三面墙、五种协作模式，以及什么时候**不该**用多 agent。'),

    ('p1-02', 'part1-多agent协作/02-DSH多agent机制全解.md',
     'DSH 多 agent 机制全解', 'A',
     '宿主平面 vs 预设平面、subagent / fork / workflow / ralph 四种分身的取舍。'),

    ('p1-03', 'part1-多agent协作/03-手把手搭建preset.md',
     '手把手搭建 preset', 'A',
     '从零造一个只有你有的 agent：人格、工具裁剪、自定义 .mjs 插件、挂载校验。'),

    ('p1-04', 'part1-多agent协作/04-workflow脚本编写.md',
     'workflow 脚本编写', 'A',
     '用一段 JS 编排一支 agent 队伍：并行、流水线、结构化返回、失败项报告。'),

    ('p1-05', 'part1-多agent协作/05-实战复盘.md',
     '实战复盘：43 条错误', 'A',
     '7 个 agent 并行调研 + 交叉审校的真实数据，以及多 agent 的能力边界。'),

    # ── 路线 B ──────────────────────────────────────────────────────────
    ('p2-01', 'part2-YOLO与骨架/01-总览与技术路线.md',
     '总览与技术路线', 'B',
     '先看这篇：完整流水线图，以及**做得到 / 做不到**的现实校验。'),

    ('p2-02', 'part2-YOLO与骨架/02-YOLO从零到能用.md',
     'YOLO 从零到能用', 'B',
     '版本乱象、许可证、环境安装、第一个模型、标注格式、训练与读懂指标。'),

    ('p2-03', 'part2-YOLO与骨架/03-姿态估计与骨架提取.md',
     '姿态估计与骨架提取', 'B',
     '方案选型、羽毛球场景的四个困难、拿到关键点后必须做的四件事。'),

    ('p2-04', 'part2-YOLO与骨架/04-羽毛球运动表现分析实战.md',
     '羽毛球分析实战', 'B',
     '击球检测、投影角、场地标定、动作分类、评估协议、报告该写什么。'),

    ('p2-05', 'part2-YOLO与骨架/05-常见坑与调试.md',
     '常见坑与调试', 'B',
     '工具书：读报错、环境问题、视频读写、跟踪失败，以及怎么让 AI 帮你调试。'),

    # ── C ───────────────────────────────────────────────────────────────
    ('starter', 'starter/README.md',
     '可运行代码骨架', 'C',
     '视频 → 骨架 → 击球事件 → 报告，含 26 项算法自检和合成数据生成器。'),

    ('preset-coach', 'preset-coach/README.md',
     '示例 agent 预设', 'C',
     '一个可以直接装进 DSH 的预设：专属人格 + 自定义工具插件。'),

    ('research-00', 'research/00-审校报告.md',
     '审校报告（43 条纠错）', 'C',
     '6 份调研笔记的事实核查结果：12 处版本错误、3 条跑不通的命令、8 处矛盾。'),

    ('research-01', 'research/01-YOLO技术全景与硬件选型.md',
     '调研 01 · YOLO 全景', 'C', '版本序列、任务类型、8GB 显存下的选型。'),

    ('research-02', 'research/02-YOLO自定义数据集与训练全流程.md',
     '调研 02 · 数据集与训练', 'C', '抽帧、标注、data.yaml、训练参数、指标解读。'),

    ('research-03', 'research/03-姿态估计技术全景.md',
     '调研 03 · 姿态估计', 'C', '六种方案对比、COCO-17 索引、3D 值不值得学。'),

    ('research-04', 'research/04-骨架时序分析与动作识别.md',
     '调研 04 · 骨架时序', 'C', 'ST-GCN/PoseC3D 学术路线 vs 特征工程 + sklearn 工程路线。'),

    ('research-05', 'research/05-羽毛球专项研究与数据集.md',
     '调研 05 · 羽毛球专项', 'C', 'ShuttleSet、TrackNet、单目 2D 的硬边界。'),

    ('research-06', 'research/06-工程实现与可视化部署.md',
     '调研 06 · 工程与部署', 'C', '视频读写、骨架渲染、Gradio、项目结构。'),
]

# 源文件路径 → 输出 html（用于改写交叉引用）
SLUG_BY_SOURCE = {src: slug + '.html' for slug, src, _t, _g, _d in PAGES}


# ══════════════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════════════

def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def strip_tags(s):
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).strip()


def cn_slugify(value, separator):
    """中文标题也生成可读的锚点（默认的 slugify 会把中文全删掉）。"""
    value = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', value, flags=re.UNICODE)
    value = re.sub(r'[\s]+', separator, value.strip())
    return value or 'section'


# ══════════════════════════════════════════════════════════════════════════
#  交叉引用改写：把 `xxx.md` 和 [文字](xxx.md) 变成站内链接
# ══════════════════════════════════════════════════════════════════════════

BACKTICK_PATH = re.compile(r'(?<![\w/`])`([\w\-./\u4e00-\u9fff]+\.md)`')
MD_LINK = re.compile(r'\]\(([\w\-./\u4e00-\u9fff]+\.md)(#[^)]*)?\)')


def resolve_target(raw, source_path):
    """把文档里写的相对/仓库相对 .md 路径，解析成输出 html。"""
    raw = raw.replace('\\', '/').lstrip('./')

    # ① 直接命中仓库相对路径
    if raw in SLUG_BY_SOURCE:
        return SLUG_BY_SOURCE[raw]

    # ② 相对当前文档所在目录
    src_dir = os.path.dirname(source_path).replace('\\', '/')
    joined = os.path.normpath(os.path.join(src_dir, raw)).replace('\\', '/')
    if joined in SLUG_BY_SOURCE:
        return SLUG_BY_SOURCE[joined]

    # ③ 只在文件名层面匹配（例如正文写 `05-实战复盘.md`）
    base = os.path.basename(raw)
    hits = [v for k, v in SLUG_BY_SOURCE.items() if os.path.basename(k) == base]
    if len(hits) == 1:
        return hits[0]

    # ④ 根目录的 README
    if base.lower() == 'readme.md' and raw.count('/') == 0:
        return 'index.html'

    return None


def rewrite_cross_refs(md_text, source_path):
    """
    只改「代码块之外」的交叉引用。
    先按 ``` 切片，偶数下标是普通正文，奇数下标是代码块，跳过后者。
    """
    parts = re.split(r'(```.*?```|~~~.*?~~~)', md_text, flags=re.S)

    for i in range(0, len(parts), 2):
        seg = parts[i]

        # 已经写成 markdown 链接的：只换目标
        def fix_link(m):
            target = resolve_target(m.group(1), source_path)
            if not target:
                return m.group(0)
            anchor = m.group(2) or ''
            return '](%s%s)' % (target, anchor)
        seg = MD_LINK.sub(fix_link, seg)

        # 反引号里的裸路径：变成链接
        def fix_backtick(m):
            raw = m.group(1)
            target = resolve_target(raw, source_path)
            if not target:
                return m.group(0)
            return '[`%s`](%s)' % (raw, target)
        seg = BACKTICK_PATH.sub(fix_backtick, seg)

        parts[i] = seg

    return ''.join(parts)


# ══════════════════════════════════════════════════════════════════════════
#  Markdown → HTML
# ══════════════════════════════════════════════════════════════════════════

def make_converter():
    return markdown.Markdown(extensions=[
        'extra',            # 表格、围栏代码、属性列表、脚注…
        'sane_lists',
        'admonition',
        'toc',
        'codehilite',
    ], extension_configs={
        'toc': {
            'slugify': cn_slugify,
            'permalink': False,
            'toc_depth': '2-3',
        },
        'codehilite': {
            'css_class': 'codehilite',
            'guess_lang': False,
            'linenums': False,
        },
    }, output_format='html5')


def md_to_html(md_text, source_path):
    md_text = rewrite_cross_refs(md_text, source_path)
    conv = make_converter()
    body = conv.convert(md_text)
    body = tag_code_langs(body, md_text)
    toc = getattr(conv, 'toc_tokens', []) or []
    return body, toc


# 围栏的开头与结尾都长这样，靠"隔一个取一个"区分：
#   ```python     ← 开头（有语言）
#   ```
#   ```           ← 结尾（没有语言）
FENCE = re.compile(r'^(?:```|~~~)[ \t]*([A-Za-z0-9_+#.\-]*)', re.M)


def tag_code_langs(body, md_text):
    """
    给代码块贴上语言标签，用于右上角显示和「复制」按钮的定位。

    为什么需要这一步：Pygments 的 codehilite 输出里**不带语言信息**
    （只有 <div class="codehilite"><pre>），所以没法从 HTML 反推。

    做法：Markdown 源码里围栏出现的顺序，和渲染后 codehilite 块的顺序**一一对应**，
    所以按顺序对应贴标签就行。数量对不上就整体放弃，绝不乱贴。
    """
    fences = FENCE.findall(md_text)
    langs = fences[0::2]          # 取第 0、2、4… 个 = 每个代码块开头的那个围栏
    langs = [x.lower() for x in langs]

    counter = {'i': 0}
    pattern = re.compile(r'<div class="codehilite"><pre>')

    total = len(pattern.findall(body))
    if total != len(langs):
        # 对不上就宁可不要标签，也不贴错
        print(f'      [提示] 代码块数({total})与围栏数({len(langs)})不一致，跳过语言标签')
        return body

    def repl(m):
        i = counter['i']
        counter['i'] += 1
        lang = langs[i] if i < len(langs) else ''
        if not lang:
            return m.group(0)
        return '<div class="codehilite"><pre data-lang="%s">' % html.escape(lang)

    return pattern.sub(repl, body)


def postprocess(body):
    """给以 ⚠️ / ⛔ 开头的引用块加警告色。"""
    def mark(m):
        inner = m.group(1)
        plain = strip_tags(inner)
        if plain.startswith(('⚠️', '⛔', '🚨')):
            return '<blockquote class="warn">%s</blockquote>' % inner
        return m.group(0)
    return re.sub(r'<blockquote>(.*?)</blockquote>', mark, body, flags=re.S)


# ══════════════════════════════════════════════════════════════════════════
#  页面模板
# ══════════════════════════════════════════════════════════════════════════

THEME_BOOT = (
    "<script>(function(){var t=null;try{t=localStorage.getItem('theme')}catch(e){}"
    "if(!t)t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches"
    "?'dark':'light';document.documentElement.setAttribute('data-theme',t)})()</script>"
)


def nav_html(current_slug):
    out = ['<nav class="sidebar" id="sidebar">']

    out.append('<div class="nav-group"><h3>开始</h3>')
    out.append('<a href="index.html"%s>🏸 首页与学习计划</a>'
               % (' class="current"' if current_slug == 'index' else ''))
    out.append('</div>')

    for gid, gname, gdesc in GROUPS:
        items = [(s, t) for (s, src, t, g, d) in PAGES if g == gid]
        if not items:
            continue
        out.append('<div class="nav-group"><h3>%s</h3>' % html.escape(gname))
        for n, (slug, title) in enumerate(items, 1):
            cls = ' class="current"' if slug == current_slug else ''
            num = '<span class="num">%d</span>' % n if gid != 'C' else ''
            out.append('<a href="%s.html"%s>%s%s</a>'
                       % (slug, cls, num, html.escape(title)))
        out.append('</div>')

    out.append('<div class="nav-group"><h3>外部</h3>')
    out.append('<a href="https://github.com/gxsri/learn-ai-coach" target="_blank" '
               'rel="noopener">GitHub 仓库 ↗</a>')
    out.append('</div>')

    out.append('</nav>')
    return '\n'.join(out)


def page(title, current_slug, main_html, desc='', is_home=False):
    full_title = (SITE_TITLE + ' · ' + SITE_SUB) if is_home else (title + ' · ' + SITE_TITLE)
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(desc or SITE_SUB)}">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏸</text></svg>">
{THEME_BOOT}
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="assets/pygments.css">
</head>
<body>

<header class="topbar">
  <button class="menu-btn" id="menu-btn" type="button" aria-label="菜单">☰</button>
  <a class="brand" href="index.html">🏸 {html.escape(SITE_TITLE)}<span>.</span></a>
  <div class="spacer"></div>
  <div class="search-wrap">
    <input id="search" type="search" placeholder="搜索（按 /）" autocomplete="off"
           spellcheck="false" aria-label="站内搜索">
    <div id="search-results" role="listbox"></div>
  </div>
  <button class="icon-btn" id="theme-btn" type="button" aria-label="切换主题">🌙</button>
  <div id="progress"></div>
</header>

<div class="layout">
{nav_html(current_slug)}
<main>
{main_html}
</main>
</div>

<script src="assets/search-index.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
"""


def doc_page(slug, title, body, prev_item, next_item, kicker):
    pager = ['<div class="pager">']
    if prev_item:
        pager.append('<a class="prev" href="%s.html"><span class="lbl">上一篇</span>'
                     '<span class="ttl">%s</span></a>' % (prev_item[0], html.escape(prev_item[1])))
    else:
        pager.append('<a class="prev disabled"></a>')
    if next_item:
        pager.append('<a class="next" href="%s.html"><span class="lbl">下一篇</span>'
                     '<span class="ttl">%s</span></a>' % (next_item[0], html.escape(next_item[1])))
    else:
        pager.append('<a class="next disabled"></a>')
    pager.append('</div>')

    main = (
        '<div class="content">\n'
        '<div class="doc-meta"><span class="crumb">%s</span></div>\n%s\n%s\n'
        '</div>' % (html.escape(kicker), body, '\n'.join(pager))
    )
    return main


def home_page(readme_html):
    cards = []
    for gid, gname, gdesc in GROUPS:
        items = [(s, src, t, g, d) for (s, src, t, g, d) in PAGES if g == gid]
        if not items:
            continue
        cards.append('<h2 class="section-title">%s</h2>' % html.escape(gname))
        cards.append('<p class="section-sub">%s</p>' % html.escape(gdesc))
        cards.append('<div class="cards">')
        for slug, src, title, _g, desc in items:
            desc_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(desc))
            cards.append(
                '<a class="card" href="%s.html">'
                '<div class="kicker">%s</div><h3>%s</h3><p>%s</p></a>'
                % (slug, html.escape(gname.split(' · ')[0]), html.escape(title), desc_html))
        cards.append('</div>')

    main = (
        '<section class="hero">'
        '<h1>把 AI 变成你的<em>羽毛球教练</em></h1>'
        '<p class="lede">一套从零开始的学习包：先用多 agent 把技术版图调研清楚，'
        '再用 YOLO 和骨架分析把手机拍的羽毛球视频变成可读的动作指标。'
        '所有代码都在真机上跑通过。</p>'
        '<div class="cta">'
        '<a class="btn primary" href="p2-01.html">从技术路线开始 →</a>'
        '<a class="btn ghost" href="p1-03.html">学搭自己的 agent</a>'
        '<a class="btn ghost" href="starter.html">看能跑的代码</a>'
        '</div></section>\n'
        + '\n'.join(cards)
        + '\n<footer class="site-footer">用 DSH 的 7 个 agent 调研 + 交叉审校产出 · '
          '代码在 RTX 4060 / torch 2.11 / ultralytics 8.4.153 上验证通过</footer>'
    )
    return main


# ══════════════════════════════════════════════════════════════════════════
#  搜索索引
# ══════════════════════════════════════════════════════════════════════════

def build_search_index(pages_rendered):
    """按 h2 小节切分，让搜索结果能定位到具体小节。"""
    items = []

    home_text = pages_rendered['index']['text']
    items.append({
        'title': '首页与学习计划',
        'heading': '',
        'anchor': '',
        'url': 'index.html',
        'text': home_text[:600],
    })

    for slug, title in pages_rendered['order']:
        html_body = pages_rendered[slug]['body']
        # 按 h2 切片
        chunks = re.split(r'<h2[^>]*id="([^"]*)"[^>]*>(.*?)</h2>', html_body, flags=re.S)
        # chunks = [前言, id1, 标题1, 正文1, id2, 标题2, 正文2, ...]
        intro = strip_tags(chunks[0]) if chunks else ''
        if intro:
            items.append({'title': title, 'heading': '', 'anchor': '',
                          'url': slug + '.html', 'text': intro[:500]})

        for i in range(1, len(chunks) - 2, 3):
            anchor = chunks[i]
            heading = strip_tags(chunks[i + 1])
            text = strip_tags(chunks[i + 2])
            if not text and not heading:
                continue
            items.append({
                'title': title,
                'heading': heading,
                'anchor': anchor,
                'url': slug + '.html',
                'text': text[:520],
            })

    return items


# ══════════════════════════════════════════════════════════════════════════
#  Pygments 样式（亮 / 暗两套）
# ══════════════════════════════════════════════════════════════════════════

def write_pygments_css(path):
    from pygments.formatters import HtmlFormatter
    try:
        light = HtmlFormatter(style='friendly')
    except Exception:
        light = HtmlFormatter(style='default')
    try:
        dark = HtmlFormatter(style='github-dark')
    except Exception:
        dark = HtmlFormatter(style='monokai')

    css = [
        '/* 由 build.py 生成 —— 不要手改 */',
        light.get_style_defs('.codehilite'),
        '[data-theme="dark"] .codehilite, [data-theme="dark"] .codehilite pre { background: #0d1117 !important; }',
        dark.get_style_defs('[data-theme="dark"] .codehilite'),
    ]
    write(path, '\n'.join(css))


# ══════════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════════

def main():
    print('=' * 68)
    print('构建学习站')
    print('=' * 68)
    print(f'  源目录  {ROOT}')
    print(f'  输出    {OUT}')
    print()

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    # ── 资源 ────────────────────────────────────────────────────────────
    os.makedirs(os.path.join(OUT, 'assets'), exist_ok=True)
    for name in ('style.css', 'app.js'):
        shutil.copy2(os.path.join(SITE, 'assets', name),
                     os.path.join(OUT, 'assets', name))
        print(f'  复制 assets/{name}')
    write_pygments_css(os.path.join(OUT, 'assets', 'pygments.css'))
    print('  生成 assets/pygments.css')

    rendered = {'order': [], 'index': {}}
    missing = []

    # ── 各文档页 ────────────────────────────────────────────────────────
    print()
    items = [(s, src, t, g, d) for (s, src, t, g, d) in PAGES]

    for i, (slug, src, title, gid, desc) in enumerate(items):
        src_path = os.path.join(ROOT, src)
        if not os.path.exists(src_path):
            missing.append(src)
            print(f'  [缺失] {src}')
            continue

        body, _toc = md_to_html(read(src_path), src)
        body = postprocess(body)

        prev_item = (items[i - 1][0], items[i - 1][2]) if i > 0 else None
        next_item = (items[i + 1][0], items[i + 1][2]) if i + 1 < len(items) else None
        gname = dict((g[0], g[1]) for g in GROUPS)[gid]

        main_html = doc_page(slug, title, body, prev_item, next_item, gname)
        write(os.path.join(OUT, slug + '.html'),
              page(title, slug, main_html, desc))

        rendered[slug] = {'body': body, 'text': strip_tags(body)}
        rendered['order'].append((slug, title))
        print(f'  [{i + 1:>2}/{len(items)}] {src}  →  {slug}.html  '
              f'({len(body) // 1024} KB)')

    # ── 首页 ────────────────────────────────────────────────────────────
    readme_path = os.path.join(ROOT, 'README.md')
    if os.path.exists(readme_path):
        body, _ = md_to_html(read(readme_path), 'README.md')
        body = postprocess(body)
        rendered['index'] = {'body': body, 'text': strip_tags(body)}
        main_html = home_page(body)
        write(os.path.join(OUT, 'index.html'),
              page('首页', 'index', main_html, SITE_SUB, is_home=True))
        print(f'\n  README.md  →  index.html')

    # ── 搜索索引 ────────────────────────────────────────────────────────
    index = build_search_index(rendered)
    js = ('/* 由 build.py 生成 —— 不要手改 */\n'
          'window.__SEARCH_INDEX__ = '
          + __import__('json').dumps(index, ensure_ascii=False, separators=(',', ':'))
          + ';\n')
    write(os.path.join(OUT, 'assets', 'search-index.js'), js)
    print(f'  搜索索引  {len(index)} 条  ({len(js) // 1024} KB)')

    # ── 收尾 ────────────────────────────────────────────────────────────
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _dn, fn in os.walk(OUT) for f in fn)
    print()
    print('=' * 68)
    print(f'完成。{len(rendered["order"])} 个页面，总大小 {total / 1024:.1f} KB')
    print(f'  本地打开：{os.path.join(OUT, "index.html")}')
    print('=' * 68)
    if missing:
        print(f'\n[警告] 有 {len(missing)} 个源文件不存在：')
        for m in missing:
            print(f'  {m}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
