/* ══════════════════════════════════════════════════════════════════
   学习站交互脚本
   · 主题切换（localStorage 记忆）
   · 侧边栏（移动端抽屉）
   · 全文搜索（索引由 build.py 生成成 search-index.js，可直接 file:// 打开）
   · 代码块一键复制
   · 阅读进度条
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict'

  var $  = function (s, r) { return (r || document).querySelector(s) }
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)) }

  /* ── 主题 ─────────────────────────────────────────────────── */
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t)
    var btn = $('#theme-btn')
    if (btn) {
      btn.textContent = t === 'dark' ? '☀️' : '🌙'
      btn.title = t === 'dark' ? '切换到亮色' : '切换到暗色'
    }
  }
  function initTheme() {
    var saved = null
    try { saved = localStorage.getItem('theme') } catch (e) { /* 隐私模式 */ }
    if (!saved) {
      saved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark' : 'light'
    }
    applyTheme(saved)
  }
  initTheme()

  var themeBtn = $('#theme-btn')
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      try { localStorage.setItem('theme', next) } catch (e) { /* ignore */ }
    })
  }

  /* ── 侧边栏抽屉 ───────────────────────────────────────────── */
  var sidebar = $('#sidebar')
  var menuBtn = $('#menu-btn')
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', function (e) {
      e.stopPropagation()
      sidebar.classList.toggle('open')
    })
    document.addEventListener('click', function (e) {
      if (!sidebar.classList.contains('open')) return
      if (sidebar.contains(e.target) || e.target === menuBtn) return
      sidebar.classList.remove('open')
    })
    $$('a', sidebar).forEach(function (a) {
      a.addEventListener('click', function () { sidebar.classList.remove('open') })
    })
  }

  /* ── 代码块：复制 + 语言标签 ──────────────────────────────── */
  $$('.content pre').forEach(function (pre) {
    var code = $('code', pre)
    if (!code) return

    // Pygments 会写成 class="language-python" 之类
    var cls = code.className || ''
    var m = cls.match(/language-([a-z0-9+#]+)/i)
    if (!m) {
      m = cls.match(/highlight-([a-z0-9+#]+)/i)
    }
    if (m) pre.setAttribute('data-lang', m[1])

    var btn = document.createElement('button')
    btn.className = 'copy-btn'
    btn.type = 'button'
    btn.textContent = '复制'
    btn.addEventListener('click', function () {
      var text = code.innerText
      var done = function () {
        btn.textContent = '已复制 ✓'
        setTimeout(function () { btn.textContent = '复制' }, 1400)
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { fallback(text, done) })
      } else {
        fallback(text, done)
      }
    })
    pre.appendChild(btn)
  })

  function fallback(text, done) {
    // file:// 下 clipboard API 可能不可用，退回 textarea + execCommand
    var ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy'); done() } catch (e) { /* ignore */ }
    document.body.removeChild(ta)
  }

  /* ── 阅读进度条 ───────────────────────────────────────────── */
  var progress = $('#progress')
  if (progress) {
    var onScroll = function () {
      var h = document.documentElement.scrollHeight - window.innerHeight
      var pct = h > 0 ? Math.min(100, (window.scrollY / h) * 100) : 0
      progress.style.width = pct + '%'
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    onScroll()
  }

  /* ── 全文搜索 ─────────────────────────────────────────────── */
  var input = $('#search')
  var box = $('#search-results')
  var INDEX = window.__SEARCH_INDEX__ || []

  if (input && box && INDEX.length) {
    var cursor = -1
    var current = []

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
      })
    }

    function score(item, terms) {
      var t = item.title.toLowerCase()
      var h = (item.heading || '').toLowerCase()
      var b = (item.text || '').toLowerCase()
      var s = 0
      for (var i = 0; i < terms.length; i++) {
        var q = terms[i]
        if (t.indexOf(q) >= 0) s += 12
        if (h.indexOf(q) >= 0) s += 7
        var n = b.split(q).length - 1
        if (n > 0) s += Math.min(n, 6)
        if (s === 0) return 0          // 有一个词没命中就淘汰
      }
      return s
    }

    function snippet(text, terms) {
      var low = text.toLowerCase()
      var at = -1
      for (var i = 0; i < terms.length; i++) {
        var p = low.indexOf(terms[i])
        if (p >= 0 && (at < 0 || p < at)) at = p
      }
      if (at < 0) at = 0
      var start = Math.max(0, at - 34)
      var out = text.slice(start, start + 110)
      return (start > 0 ? '…' : '') + out + (start + 110 < text.length ? '…' : '')
    }

    function render(terms) {
      var hits = []
      for (var i = 0; i < INDEX.length; i++) {
        var sc = score(INDEX[i], terms)
        if (sc > 0) hits.push({ item: INDEX[i], sc: sc })
      }
      hits.sort(function (a, b) { return b.sc - a.sc })
      hits = hits.slice(0, 12)
      current = hits.map(function (h) { return h.item })

      if (!hits.length) {
        box.innerHTML = '<div class="empty">没有匹配的内容</div>'
      } else {
        box.innerHTML = hits.map(function (h, idx) {
          var it = h.item
          var url = it.url + (it.anchor ? '#' + it.anchor : '')
          return '<a href="' + url + '" data-idx="' + idx + '">'
            + '<div class="r-title">' + esc(it.title)
            + (it.heading ? ' <span style="color:var(--text-faint);font-weight:400">› '
                + esc(it.heading) + '</span>' : '') + '</div>'
            + '<div class="r-snip">' + esc(snippet(it.text || '', terms)) + '</div>'
            + '</a>'
        }).join('')
      }
      box.classList.add('on')
      cursor = -1
    }

    function close() { box.classList.remove('on'); cursor = -1 }

    function move(d) {
      var links = $$('a', box)
      if (!links.length) return
      cursor = (cursor + d + links.length) % links.length
      links.forEach(function (a, i) { a.classList.toggle('active', i === cursor) })
      links[cursor].scrollIntoView({ block: 'nearest' })
    }

    var timer = null
    input.addEventListener('input', function () {
      clearTimeout(timer)
      var q = input.value.trim().toLowerCase()
      if (q.length < 1) { close(); return }
      timer = setTimeout(function () {
        render(q.split(/\s+/).filter(Boolean))
      }, 90)
    })

    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
      else if (e.key === 'Enter') {
        var links = $$('a', box)
        if (links.length) { e.preventDefault(); links[cursor < 0 ? 0 : cursor].click() }
      } else if (e.key === 'Escape') { input.value = ''; close(); input.blur() }
    })

    document.addEventListener('click', function (e) {
      if (!box.contains(e.target) && e.target !== input) close()
    })

    // 快捷键：/ 或 Ctrl+K 聚焦搜索
    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea') return
      if (e.key === '/' || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault()
        input.focus()
        input.select()
      }
    })
  }

  /* ── 键盘左右方向键翻页 ───────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return
    var tag = (e.target.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'textarea') return
    if (e.key === 'ArrowLeft') {
      var p = $('.pager a.prev'); if (p && p.href) location.href = p.href
    } else if (e.key === 'ArrowRight') {
      var n = $('.pager a.next'); if (n && n.href) location.href = n.href
    }
  })
})()
