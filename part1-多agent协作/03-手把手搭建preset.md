# 03 · 手把手搭建你自己的 agent preset

> 目标：读完之后你能自己造出一个**只有你有**的 agent——它有专属人格、专属工具、专属行为。
> 这一篇是"搭建"的核心。

---

## 〇、先认清一件事

**一个 agent 的能力 = 它挂载了哪些 plugin row。**

没有"设置面板"，没有"配置文件里勾选功能"。你写一个 YAML，列出这个 agent 要哪些行，它就有什么能力。**这就是全部的魔法。**

---

## 一、preset 是什么，放在哪

一个 preset 就是**一个目录**：

```
<你的预设目录>/
├── agent.cordis.yml     ← 必需。这个 agent 的组成（哪些行）
├── preset.yml           ← 建议有。显示名称和描述
├── my-tool.mjs          ← 可选。你自己写的插件
└── skills/              ← 可选。这个 agent 专属的技能包
```

**两个位置，别搞混：**

| 位置 | 路径 | 谁能改 |
|---|---|---|
| **随程序发布的预设** | `…\resources\app.asar.unpacked\node_modules\@deepseek-ai\dsh-agent-presets\presets\` | ❌ **永远不要动** |
| **你自己写的预设** | `%USERPROFILE%\.dsh\.agent-presets\<id>\` | ✅ 随便改 |

> ### ⛔ 铁律：不要编辑、删除随程序发布的预设
>
> 里面是 `standard`（完整编码 agent）、`minimal`、`ptc`、`cordis`（就是你现在这个模式）。
> **升级程序会覆盖它**。更要命的是：弄坏 `cordis` 会让"改预设"这个能力本身消失——你就没法自救了。
>
> **要改它的行为 → 复制一份出来改副本。** 这也是下面第一步。

你机器上的预设目录里可能已经有自己写的预设了。打开看看——真实的例子比文档好懂，
尤其是那些带了自定义 `.mjs` 插件的：它们正好是本文要教的东西。

---

## 二、第一步：复制一份出来

```powershell
# 1) 找到随程序发布的 standard 预设
#    把下面这行的路径换成你自己的 DSH 安装目录（结尾是 resources\app.asar.unpacked）
$ship = "$env:LOCALAPPDATA\Programs\DSH Desktop\resources\app.asar.unpacked\node_modules\@deepseek-ai\dsh-agent-presets\presets\standard"

# 2) 复制到你的预设目录，取个新名字
$mine = "$env:USERPROFILE\.dsh\.agent-presets\coach"
Copy-Item -Path "$ship\*" -Destination $mine -Recurse -Force
```

**为什么要复制而不是从零写？**
因为 `standard` 是**已经能挂载的**完整组成。从零写几乎一定会漏东西（少一个 realm、少一个消费者行），而复制出来的起点是好的。改坏了也好对照。

> 本教程已经帮你把这份副本准备好了：`D:\program\learn-ai-coach\preset-coach\`。
> 里面除了 `standard` 的完整内容，还加了一个自定义工具插件和中文人格。可以直接用，也可以当模板看。

---

## 三、`preset.yml`：给它一个名字

```yaml
name: 羽毛球教练
description: 带羽毛球运动分析专用工具的编码 agent，会主动用多 agent 做调研与交叉验证。
```

- `name` → 选择会话时看到的显示名
- `description` → 显示在名字下面的一句说明
- `order` → **只给随程序发布的预设用**，你自己写的**不要加**

> 不写 `preset.yml` 会怎样？这个预设会用**目录名**出现在所有选择列表里（比如显示成 `coach`）。不算错，但很难看。

---

## 四、`agent.cordis.yml`：核心，逐行读懂

这个文件就是**一串行（row）**。每行长这样：

```yaml
- id: tool-web                              # 本文件内唯一的行 id，用来报错定位
  name: '@deepseek-ai/dsh-tool-web'         # 要挂载的包（或 ./本地文件.mjs）
  config:                                   # 传给这个包的配置（可选）
    fetch: true
```

### 四种行，你只要认识这四种

**① 普通行**——挂一个包，贡献一点能力

```yaml
- id: tool-fs
  name: '@deepseek-ai/dsh-tool-fs'
```

**② 分组行 + `isolate` 隔离域**——把"会提供服务"的行关进一个小房间

```yaml
- id: delegation
  name: cordis:group          # 固定写法：这是一个分组
  group: true
  isolate:
    workflowEngine: true      # 这里列出的服务，每个挂载它的会话各有一份
  config:
    - id: workflow-worker-thread
      name: '@deepseek-ai/dsh-workflow-worker-thread'
      config:
        provider: spawn
    - id: tool-workflow
      name: '@deepseek-ai/dsh-tool-workflow'
```

**③ 条件行**——按平台开关

```yaml
- id: tool-bash
  name: '@deepseek-ai/dsh-tool-bash'
  disabled: !!js process.platform === 'win32'   # Windows 上不挂 bash
```

**④ 本地文件行**——挂你自己写的 `.mjs`

```yaml
- id: tool-session-status
  name: ./tool-session-status.mjs     # 相对本 YAML 所在目录
  config:
    outputsDir: 'D:\program\learn-ai-coach\starter\outputs'
```

### 🌟 两条铁律（这两条错了，挂载直接失败）

> **铁律 1：会"提供服务"的行，不能光溜溜地待在 preset 里。**
> 否则它的服务会注册到进程全局，第二个会话挂载同一个 preset 时**撞名崩溃**。
> 正确做法：把提供者和**所有使用它的行**，一起包进一个带 `isolate` 的分组。
> `isolate: { 服务名: true }` 里的 `true` = 每个挂载会话一份私有实例。

> **铁律 2：preset 只是"使用"的 host 能力，不要包 `isolate`。**
> 比如 `tool-bash`、`tool-jobs`、`tool-goal`——它们不提供任何服务，消费的是 host 里的注册表。
> 把它们包进隔离域，它们就**找不到** host 的实例，**静默失效**（不报错，但不干活）。
>
> 这一条很阴险：**包错了不报错**，只是那个工具永远不出现。

**怎么判断一行到底提供不提供服务？** 名字看不出来。得看运行时的服务列表，或者挂载一次看报错——报错会**直接点名**是哪个服务。

### 需要重点关注的几行

在副本里找到这几行，它们就是"多 agent 能力"的来源：

```yaml
- id: delegation
  name: cordis:group
  group: true
  isolate:
    workflowEngine: true
  config:
    - id: tool-subagent                    # ← subagent 工具
      name: '@deepseek-ai/dsh-tool-subagent'
      config:
        provider: spawn
        toolName: subagent
        modelSelectionSettings: true       # 允许给子 agent 指定别的模型
        backgroundMode: continuable        # 跑完还能继续派活
    - id: tool-subagent-fork               # ← fork 工具
      name: '@deepseek-ai/dsh-tool-subagent'
      config:
        provider: fork
        toolName: subagent_fork
        backgroundMode: continuable
    - id: workflow-worker-thread
      name: '@deepseek-ai/dsh-workflow-worker-thread'
      config:
        provider: spawn
    - id: tool-workflow                    # ← workflow 工具
      name: '@deepseek-ai/dsh-tool-workflow'
    - id: tool-ralph                       # ← ralph 工具
      name: '@deepseek-ai/dsh-tool-ralph'
      config:
        subagentProvider: spawn
        maxRounds: 64
```

**想让你的 agent 没有某个能力？把那一行整体删掉或注释掉。**
比如把 `tool-ralph` 删了，这个 agent 就没有 `ralph` 工具了。**这就是"裁剪 agent"。**

---

## 五、写你自己的工具（`.mjs`）——最实用的一步

这是"搭建"里最有价值的部分：**把你的工作流封装成一个工具，让 agent 直接调用。**

一个插件文件必须导出三样东西：

| 导出 | 必需 | 作用 |
|---|---|---|
| `export const name` | ✅ | 插件名，报错时用它定位 |
| `export const inject` | 视情况 | **硬依赖**的服务列表。服务不在时，这行会"等待"而不是报错 |
| `export function apply(ctx, config)` | ✅ | 挂载时被调用，在这里注册工具/监听事件 |

### 完整可用的例子

下面这个工具会扫描你的分析项目，报告每个 session 跑到了哪一步：

```js
// tool-session-status.mjs
import { readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'

export const name = 'tool-session-status'

// 硬依赖：工具注册表必须先存在。写法固定为 ['tools']
export const inject = ['tools']

// 流水线的四个产物，顺序就是展示顺序
const STAGES = [
  ['01_pose.csv', '骨架'],
  ['02_events.csv', '击球'],
  ['03_metrics.json', '指标'],
  ['report.html', '报告'],
]

export function apply(ctx, config) {
  // config 就是 YAML 里那一行 config: 下面的内容
  const outputsDir =
    typeof config?.outputsDir === 'string' && config.outputsDir.length > 0
      ? config.outputsDir
      : 'D:\\program\\learn-ai-coach\\starter\\outputs'

  ctx.tools.register({
    name: 'pose_status',

    // ★ 这段文字是给模型看的。写清楚"什么时候该用它"，比写清功能更重要
    description:
      '查看羽毛球动作分析项目的进度：列出 outputs 目录下每个 session，'
      + '以及骨架/击球/指标/报告四步各自完成没有。'
      + '在用户问"跑到哪了""有哪些结果"时使用。',

    // 参数用 JSON Schema 描述。没有参数就是空对象
    parameters: { type: 'object', properties: {}, additionalProperties: false },

    // output.schema 约束返回值；render 决定在 GUI 里怎么显示
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { text: { type: 'string' } },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },

    // execute 是真正干活的函数。它可以是 async
    async execute() {
      let entries
      try {
        entries = await readdir(outputsDir, { withFileTypes: true })
      } catch (error) {
        return { text: `读不到输出目录 ${outputsDir}：${error.message}` }
      }

      const sessions = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort()
      if (sessions.length === 0) {
        return { text: `输出目录 ${outputsDir} 下还没有任何 session。` }
      }

      const header = '| session | ' + STAGES.map((s) => s[1]).join(' | ') + ' |'
      const divider = '|---|' + STAGES.map(() => '---').join('|') + '|'
      const rows = []
      for (const session of sessions) {
        const cells = []
        for (const [file] of STAGES) {
          const exists = await stat(join(outputsDir, session, file)).then(() => true, () => false)
          cells.push(exists ? '✅' : '—')
        }
        rows.push(`| ${session} | ${cells.join(' | ')} |`)
      }
      return { text: [header, divider, ...rows].join('\n') }
    },
  })
}
```

然后在 YAML 里挂上它：

```yaml
- id: tool-session-status
  name: ./tool-session-status.mjs
  config:
    outputsDir: 'D:\program\learn-ai-coach\starter\outputs'
```

**就这两步。** 新建会话后，这个 agent 就多了一个叫 `pose_status` 的工具。

### 写自定义工具的四条经验

1. **`inject` 只写你真正离不开的服务。** 可选的服务用 `ctx.get('名字')` 拿，拿到 `undefined` 就优雅降级——不要因为一个可选服务不在，整个工具就挂载失败。
2. **`description` 是写给模型看的，不是写给人的。** 要写"**什么时候**用我"，而不只是"我是什么"。
3. **出错要返回可读的话，不要 throw。** `throw` 会让工具调用变成红色错误；返回一句"读不到目录 X，因为 Y"模型能自己纠正。
4. **一切副作用都要能撤销。** 注册工具、开定时器、挂监听，都用 `ctx.effect()` / `ctx.on()` 或官方 API 返回的 disposer——否则这个 preset 卸载时会留下野指针。

---

## 六、验证：怎么知道它能不能用

改完 YAML 之后，检查这四种失败（对应四类错误）：

| 报错长这样 | 意思 | 怎么修 |
|---|---|---|
| `Cannot find package …` | 某行写的包名不存在 | 核对包名拼写；本地文件用 `./文件名.mjs` |
| `invalid config: $.<字段> missing required value` | 某行的 config 缺必填项 | 补上那个字段 |
| `N row(s) did not activate: <id>: waiting for <服务>` | 某行在等服务，永远等不到 | 通常是**铁律 2**：被错误地包进 isolate，或者依赖的服务根本没挂 |
| `row(s) published process-global service(s) [<名字>]` | 某行把服务注册到了全局 | **铁律 1**：给提供者 + 所有消费者包一个 `isolate` 分组 |

> **注意**：预设列表里的 `broken` 标记**不等于**验证通过。它只检查"文件能不能解析、有没有命名的行"。上面这四种失败**全都能通过那个检查**。

### 更深的验证：读每一行的 `fiberState`

`agentPresets` 这个 host 服务能告诉你**每一行到底激活了没有**：

```
standingKeyFor(id)         → 真的把这个 preset 的插件子树组装一次（权威检查）
compositionInventory()     → 每个 preset 的每一行，带 entryId / moduleName / enabled / fiberState
list()                     → 名单行：trust / name / path / broken
```

> **⚠️ 一个实测踩到的坑**：`fiberState` 是**数字枚举**，不是字符串。
> 你无法直接看出 `2` 是不是"已激活"。**正确做法是拿一个已知能用的 preset 当基线对照。**

本教程安装的 `coach` 预设，就是这样被验证的（对照官方 `standard`）：

| 预设 | 总行数 | `fiberState=2` | `fiberState` 为空 |
|---|---|---|---|
| `standard`（官方，已知可用） | 27 | **24** | 3 |
| `coach`（教程安装的） | 28 | **25** | 3 |
| `liangshen`（你自己写的，已知可用） | 30 | **25** | 5 |

**读法**：

- `fiberState=2` 就是"已激活"（三个预设里所有启用的行都是 2，包括本地 `.mjs` 行）
- `fiberState` 为空的那几行是 `cordis:group` 分组行 —— 它们是伪行，没有真实 fiber
- **`coach` 比 `standard` 正好多一行**，多出来的正是 `tool-session-status`：
  ```
  include:agent-presets:tool-session-status  ./tool-session-status.mjs  fiberState=2
  ```
  **这就证明自定义工具行真的激活了。**
- 反过来：如果有哪一行的 `fiberState` 和基线**不一样**，那一行就是嫌疑对象

**这个方法的通用形式**：
> **复制一份已知能用的组成，只改一处，然后对比 `fiberState` 分布。**
> 差异应该正好是你改动的那一行。多出来的、少掉的、状态不同的，都是线索。

**真正的验证 = 真的挂载一次**（就是启动一个新会话用这个预设），然后**看工具列表对不对**。

实操流程：

1. 新增或编辑 `agent.cordis.yml`
2. **重启 DSH**（预设列表在启动时扫描）
3. 新建会话 → 选你的预设
4. 问它一句"你现在有哪些工具？" → 核对工具列表
5. 调一下你的自定义工具 → 看返回对不对

**改一点、验一点。** 一次改五行然后挂载失败，你会不知道是哪行的问题。

### 静态校验脚本

本教程附带一个静态校验工具，可以在**不启动会话**的情况下先查一遍：

```powershell
node .\validate-preset.mjs "$env:USERPROFILE\.dsh\.agent-presets\coach"
```

> 找不到 DSH 的 `node_modules` 时，用 `--root` 显式指定安装目录：
> `node .\validate-preset.mjs --root "D:\你的安装路径\resources\app.asar.unpacked" <预设目录>`

它检查：YAML 能否解析（含 `!!js` 自定义标签）、每行有没有 id/name、id 有没有重名、
引用的包在不在 DSH 的 node_modules 里、引用的本地 `.mjs` 存不存在且语法正确、
`preset.yml` 有没有写错、以及列出了所有 `isolate` 隔离域。

**它查不出**上面表格里的后三类（config 无效、行没激活、服务发布到全局）——
**那三类只有真正挂载一次才会暴露。**

---

## 七、常见误解

**❓"我想让 agent 更聪明，是不是该加很多工具？"**
不是。工具越多，模型选错的概率越大。**加工具要有明确的使用场景。**

**❓"我能不能在 preset 里放宽沙箱/审批？"**
不能，也不该。沙箱、审批、权限是 **host 平面**的边界。一个 preset 的权限**恰好等于它列出的那些行**——让它自己放开自己的约束，等于没有约束。

**❓"为什么我不能把会话持久化、模型路由放进 preset？"**
因为它们是**跨会话**的。会话列表必须全局一份，否则会话就碎了。**判断标准：这个能力是否被会话之外的东西读取？是 → host 平面。**

**❓"能不能让两个不同的 preset 共享一个服务实例？"**
`isolate` 的值写字符串（标签）可以让几个分组**加入同一个隔离域**。但注意：**同一个服务名仍然只能注册一次**，第二次会抛错。标签是"打通房间"，不是"共享实例"。

---

## 八、下一步

- 想写 `workflow` 编排脚本 → `04-workflow脚本编写.md`
- 想看看这一切在真实任务里怎么用 → `05-实战复盘.md`
