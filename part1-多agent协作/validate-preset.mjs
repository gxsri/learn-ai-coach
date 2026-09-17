#!/usr/bin/env node
/**
 * validate-preset.mjs —— 静态校验一个 agent preset 的组成文件。
 *
 * 它检查的是**能在不启动会话的情况下查出来的问题**：
 *   1. YAML 能不能解析（含 `!!js` 这种自定义标签）
 *   2. 每一行是不是都有 id 和 name，id 有没有重名
 *   3. 引用的包能不能在 DSH 的 node_modules 里找到
 *   4. 引用的本地 .mjs 文件存不存在、语法对不对
 *   5. 哪些行提供了服务、哪些行在 isolate 隔离域里（对照两条铁律）
 *   6. config 块有没有明显写错（比如把 config 写成数组）
 *
 * ⚠️ 它**不能**替代真正的挂载验证。下面这几种失败它查不出来：
 *   · invalid config: $.<字段> missing required value
 *   · N row(s) did not activate: <id>: waiting for <服务>
 *   · row(s) published process-global service(s) [<名字>]
 * 这三类只有真正挂载一次（启动一个用该 preset 的会话）才会暴露。
 *
 * 用法：
 *   node validate-preset.mjs <preset 目录或 agent.cordis.yml 的路径>
 *   node validate-preset.mjs --list-roots
 */

import { createRequire } from 'node:module'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve as resolvePath } from 'node:path'
import { spawnSync } from 'node:child_process'

// DSH 安装位置的可能根目录（用于解析 @deepseek-ai/* 和 yaml 库）。
// 优先用环境变量或 --root 指定；否则从常见的安装位置推断。
const ROOT_OVERRIDE = (() => {
  const idx = process.argv.indexOf('--root')
  return idx >= 0 ? process.argv[idx + 1] : undefined
})()

const CANDIDATE_ROOTS = [
  ROOT_OVERRIDE,
  process.env.DSH_APP_ROOT,
  process.env.DSH_ROOT,
  join(process.env.LOCALAPPDATA || '', 'Programs/DSH Desktop/resources/app.asar.unpacked'),
  join(process.env.PROGRAMFILES || '', 'DSH Desktop/resources/app.asar.unpacked'),
  join(process.env['PROGRAMFILES(X86)'] || '', 'DSH Desktop/resources/app.asar.unpacked'),
].filter((root) => typeof root === 'string' && root.length > 0)

const problems = []
const warnings = []
const notes = []

function fail(message) { problems.push(message) }
function warn(message) { warnings.push(message) }
function note(message) { notes.push(message) }


// ── 定位 DSH 的 node_modules ────────────────────────────────────────────────
function findRoot() {
  for (const root of CANDIDATE_ROOTS) {
    if (root && existsSync(join(root, 'node_modules'))) return root
  }
  return null
}

const dshRoot = findRoot()


// ── 载入 yaml 库 ────────────────────────────────────────────────────────────
function loadYaml() {
  const tries = [dshRoot, process.cwd()].filter(Boolean)
  for (const base of tries) {
    try {
      const req = createRequire(join(base, 'noop.js'))
      return req('yaml')
    } catch {
      // 换下一个根目录
    }
  }
  return null
}

const YAML = loadYaml()


// ── 主流程 ──────────────────────────────────────────────────────────────────
// 先把 --root <路径> 从参数里摘掉，剩下的第一个才是"要校验的预设"。
// （不摘掉的话 `--root X <预设>` 会被当成 target = "--root"）
const rawArgv = process.argv.slice(2)
const argv = []
for (let i = 0; i < rawArgv.length; i++) {
  if (rawArgv[i] === '--root') { i++; continue }   // 跳过 --root 和它的值
  argv.push(rawArgv[i])
}

if (rawArgv.includes('--list-roots')) {
  console.log('DSH 根目录候选：')
  for (const root of CANDIDATE_ROOTS) {
    if (!root) continue
    const ok = existsSync(join(root, 'node_modules'))
    console.log(`  ${ok ? '[OK]  ' : '[MISS]'} ${root}`)
  }
  console.log(`\nyaml 库：${YAML ? '可用' : '找不到'}`)
  console.log('\n如果全部 MISS，用 --root 或环境变量显式指定：')
  console.log('  node validate-preset.mjs --root "D:\\你的安装路径\\resources\\app.asar.unpacked" <预设目录>')
  console.log('  set DSH_APP_ROOT=D:\\你的安装路径\\resources\\app.asar.unpacked')
  process.exit(0)
}

const target = argv[0]
if (!target) {
  console.error('用法：node validate-preset.mjs [--root <DSH app.asar.unpacked 路径>] <preset 目录 | agent.cordis.yml>')
  console.error('      node validate-preset.mjs --list-roots')
  process.exit(2)
}

let compositionPath = target
if (existsSync(target) && statSync(target).isDirectory()) {
  compositionPath = join(target, 'agent.cordis.yml')
}
if (!existsSync(compositionPath)) {
  console.error(`[错误] 找不到组成文件：${compositionPath}`)
  process.exit(2)
}
const presetDir = dirname(resolvePath(compositionPath))

console.log('='.repeat(70))
console.log('Preset 静态校验')
console.log('='.repeat(70))
console.log(`  组成文件  ${resolvePath(compositionPath)}`)
console.log(`  所在目录  ${presetDir}`)
console.log(`  DSH 根    ${dshRoot || '（没找到，包解析检查会跳过）'}`)
console.log(`  yaml 库   ${YAML ? '可用' : '（没找到，跳过 YAML 解析）'}`)
console.log()

if (!YAML) {
  warn('找不到 yaml 解析库，只能做文件存在性和语法检查。')
  console.log('       运行 node validate-preset.mjs --list-roots 看候选路径。')
}


// ── 1. 解析 YAML ────────────────────────────────────────────────────────────
let rows = null

if (YAML) {
  const text = readFileSync(compositionPath, 'utf8')

  // 组成文件里用了 `!!js <表达式>`（条件行），需要自定义标签才能解析
  const jsTag = {
    tag: '!!js',
    resolve: (value) => ({ __js: String(value) }),
  }

  try {
    rows = YAML.parse(text, { customTags: [jsTag] })
  } catch (error) {
    try {
      // 有的解析器不接受自定义标签，退化处理：先把 !!js 换成普通标量
      const patched = text.replace(/!!js\s+/g, '')
      rows = YAML.parse(patched)
      warn('YAML 里有 !!js 标签，已用替换方式解析（条件行的表达式被当作文本）。')
    } catch (error2) {
      fail(`YAML 解析失败：${error2.message}`)
    }
  }

  if (rows !== null && !Array.isArray(rows)) {
    fail(`根节点必须是数组（一串行），实际是 ${typeof rows}`)
    rows = null
  }
}


// ── 2. 遍历所有行 ───────────────────────────────────────────────────────────
const seenIds = new Map()
const isolatedServices = new Map()   // 服务名 → 隔离域所在的行 id

/** 把 `@scope/pkg/sub/path` 里的包名部分取出来 */
function packageNameOf(specifier) {
  const parts = specifier.split('/')
  if (specifier.startsWith('@')) return parts.slice(0, 2).join('/')
  return parts[0]
}

function checkPackage(specifier, rowId) {
  if (!dshRoot) return
  const pkg = packageNameOf(specifier)
  const pkgDir = join(dshRoot, 'node_modules', ...pkg.split('/'))
  if (!existsSync(pkgDir)) {
    fail(`行 ${rowId}：找不到包 ${pkg}（在 ${join(dshRoot, 'node_modules')} 下）`)
  }
}

function checkLocalFile(specifier, rowId) {
  const path = isAbsolute(specifier) ? specifier : join(presetDir, specifier)
  if (!existsSync(path)) {
    fail(`行 ${rowId}：本地文件不存在 ${path}`)
    return
  }
  if (!specifier.endsWith('.mjs') && !specifier.endsWith('.js')) return

  // 语法检查：跑 `node --check <文件>`
  const result = spawnSync(process.execPath, ['--check', path], { encoding: 'utf8' })

  if (result.error) {
    // 受限沙箱里，Node 无法通过管道捕获子进程输出（Windows 上是 EPERM）。
    // 这不是 preset 的问题，不要报成失败 —— 退回只看退出码的方式。
    const retry = spawnSync(process.execPath, ['--check', path], { stdio: 'ignore' })
    if (retry.error) {
      warn(`行 ${rowId}：无法运行语法检查（${retry.error.code || retry.error.message}），已跳过。`
           + `请手工运行：node --check "${path}"`)
      return
    }
    if (retry.status !== 0) {
      fail(`行 ${rowId}：${specifier} 语法错误（退出码 ${retry.status}）。`
           + `请运行 node --check "${path}" 看详情`)
    }
    return
  }

  if (result.status !== 0) {
    fail(`行 ${rowId}：${specifier} 语法错误\n${(result.stderr || '').trim()}`)
  }
}

function walk(list, insideRealm) {
  if (!Array.isArray(list)) return

  for (const row of list) {
    if (!row || typeof row !== 'object') {
      fail(`发现一个不是对象的行：${JSON.stringify(row)}`)
      continue
    }

    const id = row.id
    const name = row.name

    if (!id) fail(`有一行缺少 id：${JSON.stringify(row).slice(0, 90)}`)
    if (!name) fail(`行 ${id} 缺少 name`)

    if (id) {
      if (seenIds.has(id)) {
        fail(`行 id 重复：${id}（已经出现在第 ${seenIds.get(id)} 个位置）`)
      }
      seenIds.set(id, seenIds.size)
    }

    // 记录隔离域里的服务
    if (row.isolate && typeof row.isolate === 'object') {
      for (const [service, realm] of Object.entries(row.isolate)) {
        isolatedServices.set(service, { rowId: id, realm })
      }
      if (row.group !== true) {
        warn(`行 ${id} 有 isolate 但没有 group: true —— 隔离域只对分组有意义`)
      }
    }

    // 检查 name
    if (typeof name === 'string') {
      if (name === 'cordis:group') {
        if (row.group !== true) {
          fail(`行 ${id}：name 是 cordis:group 但没有写 group: true`)
        }
        if (!Array.isArray(row.config)) {
          fail(`行 ${id}：分组行的 config 必须是数组（子行列表）`)
        }
      } else if (name.startsWith('./') || name.startsWith('../')) {
        checkLocalFile(name, id)
      } else if (name.startsWith('@') || /^[a-z]/.test(name)) {
        checkPackage(name, id)
      }
    }

    // config 形状
    if (row.config !== undefined && row.group !== true && typeof row.config !== 'object') {
      warn(`行 ${id}：config 不是一个对象`)
    }

    // 递归子行
    if (Array.isArray(row.config)) walk(row.config, insideRealm || Boolean(row.isolate))
  }
}

if (rows) {
  walk(rows, false)

  const enabled = []
  const disabled = []
  const collect = (list) => {
    for (const row of list || []) {
      if (!row || typeof row !== 'object') continue
      if (row.disabled) disabled.push(row.id)
      else enabled.push(row.id)
      if (Array.isArray(row.config)) collect(row.config)
    }
  }
  collect(rows)

  note(`共 ${seenIds.size} 行：启用 ${enabled.length}，条件禁用 ${disabled.length}`)
}


// ── 3. preset.yml ───────────────────────────────────────────────────────────
// 判断这个 preset 是不是"随程序发布的"（那种才用 order 排显示顺序）
const isShippedPreset = /[\\/]node_modules[\\/]@deepseek-ai[\\/]dsh-agent-presets[\\/]/.test(presetDir)

const presetYml = join(presetDir, 'preset.yml')
if (!existsSync(presetYml)) {
  warn('没有 preset.yml —— 这个预设会在选择列表里显示成目录名。')
} else if (YAML) {
  try {
    const meta = YAML.parse(readFileSync(presetYml, 'utf8'))
    if (!meta || !meta.name) {
      warn('preset.yml 里没有 name —— 显示名会退化成目录名。')
    } else {
      note(`显示名：${meta.name}`)
    }
    if (meta && meta.order !== undefined && !isShippedPreset) {
      warn('preset.yml 里有 order —— 那是给随程序发布的预设用的，'
           + '自己写的预设不需要，建议删掉。')
    }
  } catch (error) {
    fail(`preset.yml 解析失败：${error.message}`)
  }
}


// ── 4. 两条铁律的辅助判断 ───────────────────────────────────────────────────
const TOOL_ONLY_HINT = /(^@deepseek-ai\/dsh-tool-|tool-|persona|instructions|skill-|command-)/

if (rows) {
  // 铁律 1：有 isolate 的分组，其子行应该都在同一个域里
  const realmsInUse = [...isolatedServices.entries()]
  if (realmsInUse.length > 0) {
    note('发现隔离域（isolate）：')
    for (const [service, info] of realmsInUse) {
      note(`  · ${service}  →  由行「${info.rowId}」建立，realm=${JSON.stringify(info.realm)}`)
    }
    note('  提醒：提供该服务的行**和所有使用它的行**都必须在这个分组内，')
    note('        否则消费者会去解析 host 的同名注册表，然后静默失效。')
  }
}


// ── 输出 ────────────────────────────────────────────────────────────────────
console.log('-' .repeat(70))

if (notes.length) {
  console.log('\n[信息]')
  for (const n of notes) console.log(`  · ${n}`)
}

if (warnings.length) {
  console.log('\n[警告]')
  for (const w of warnings) console.log(`  ! ${w}`)
}

console.log()
if (problems.length) {
  console.log(`[失败] 发现 ${problems.length} 个问题：`)
  for (const p of problems) console.log(`  X ${p}`)
  console.log()
  console.log('  这些问题会让某个行「找不到包」「不激活」或在挂载时抛错。')
  console.log('  参考：part1-多agent协作/03-手把手搭建preset.md 第六节（四种失败）')
} else {
  console.log('[通过] 静态检查没有发现问题。')
  console.log()
  console.log('  但请记住：静态检查**不能**替代真正的挂载验证。')
  console.log('  下一步：新建一个会话并选择这个预设，然后问它「你现在有哪些工具？」')
  console.log('  如果工具列表不对，说明有行没有激活 —— 那才是真正的验收。')
}

console.log('='.repeat(70))
process.exit(problems.length ? 1 : 0)
