# 04 · workflow 脚本编写：让多个 agent 按你的剧本干活

> `workflow` 是 DSH 里唯一让你**用代码控制多个 agent** 的工具。
> 学会它，你就从"跟一个 agent 聊天"升级成"指挥一支队伍"。

---

## 一、先理解它是什么

你交给 `workflow` 的，是**一段 JavaScript**。

关键认知：**这段脚本自己不调用大模型。** 它只做三件事：

1. **派活** —— `agent(prompt)` 开一个子 agent
2. **等结果** —— `await` 拿到那个 agent 的最终输出
3. **编排** —— 用普通 JS 的循环/条件/变量，决定下一步派什么活

```text
       你的脚本（纯逻辑，不烧 token）
            │
            ├── agent(A) ──→ 子 agent A ──→ 返回文本
            ├── agent(B) ──→ 子 agent B ──→ 返回文本
            └── agent(C) ──→ 子 agent C ──→ 返回对象
            │
       ┌────┴────┐
       │  return │  → 结果交回主 agent
       └─────────┘
```

**所以：写 workflow = 写调度逻辑。** 智能的部分在子 agent 里。

---

## 二、脚本能用的东西（就这五个 + args）

脚本运行在一个**受限沙箱**里，**没有**文件系统、网络、定时器、Node API。
这不是限制，是设计：脚本只负责协调，干活的活交给 agent。

| 名字 | 作用 |
|---|---|
| `agent(prompt, opts?)` | 开一个子 agent，等它跑完。**返回它的最终文本**；给了 `schema` 就返回**校验过的对象** |
| `pipeline(items, ...stages)` | 每个 item 独立跑完所有 stage。**stage 之间没有栅栏** |
| `parallel(thunks)` | 并发跑一组函数，**全部跑完才返回**（有栅栏） |
| `phase(title)` | 标记一个阶段，用于进度显示。**title 必须和 meta 里声明的一致** |
| `log(message)` | 输出一行进度文字 |
| `args` | 工具调用时传进来的 `args` 参数（一个对象） |

### ⚠️ 三条会直接杀死脚本的错误

**用错了这些 hook，整个脚本立刻死**（不会降级成某个 item 失败）：

- `agent()` 传了不认识的选项（比如 `effort` / `isolation` / `agentType`）
- `schema` 用了不允许的关键字
- 超出了并发数 / 总 agent 数上限

> 注意这个区别：**stage 里抛异常** → 只有那**一个 item** 变成 `null`，其他 item 继续；
> **hook 本身用错** → **全脚本挂掉**。所以参数要写对。

---

## 三、`agent()` 的选项，只有这么几个

```js
const result = await agent('你的提示词', {
  label: '显示用短标签',        // 在 GUI 里显示，方便你看谁在跑
  phase: '阶段标题',            // 必须和 meta.phases 里的 title 完全一致
  schema: { /* JSON Schema */ },// 给了就返回对象，不给就返回文本
  provider: 'xxx',             // 可选：换供应商
  model: 'xxx',                // 可选：换模型（比如用便宜模型干粗活）
})
```

**除了这些，其它选项一律报错。** 没有 `temperature`，没有"让它多想一会"的旋钮——那些是模型层面的事。

### `schema` 只能用这些关键字

```
type / properties / required / additionalProperties / items / enum / const / oneOf
```

**不能用** `pattern`、`format`、数值范围（`minimum`/`maximum`）。要校验格式，就让 agent 自己在提示词里遵守，拿回来再用 JS 判断。

顶层必须是 `type: 'object'`。

```js
const verdict = await agent('判断这段代码有没有安全问题…', {
  schema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      严重程度: { type: 'string', enum: ['高', '中', '低', '无'] },
      问题列表: { type: 'array', items: { type: 'string' } },
    },
    required: ['严重程度', '问题列表'],
  },
})
// verdict.严重程度 直接就能用，不用解析文本
```

---

## 四、`pipeline` vs `parallel`：最容易搞混的一个点

### `parallel` —— 并发，但**有栅栏**

```js
const 结果 = await parallel([
  () => agent('任务 A'),
  () => agent('任务 B'),
  () => agent('任务 C'),
])
// 这里：A、B、C 全都跑完了
```

- 传的是**一组零参函数**
- **全部完成**才返回
- 某一个抛异常 → 那一个变成 `null`，**不影响别人**
- **只在"下一步确实需要所有结果一起"时才用**

### `pipeline` —— 每个 item 走完全程，**没有栅栏**

```js
const 结果 = await pipeline(
  素材列表,
  (prev, item, index) => agent(`从这份素材提取要点：${item}`),     // stage 1
  (prev, item, index) => agent(`核实这些要点是否属实：${prev}`),   // stage 2
  (prev, item, index) => agent(`写成 300 字成稿：${prev}`),        // stage 3
)
```

- 每个 stage 收到 `(上一阶段的输出, 当前 item, 下标)`
- **素材 1 跑到第 3 步时，素材 5 可能还在第 1 步** —— 这是它比 `parallel` 快的原因
- 某个 item 在某个 stage 抛错 → **只有这个 item 变成 `null`，它剩下的 stage 被跳过**，其他 item 照常

> **经验法则：多阶段处理一律用 `pipeline`。** 只有"必须等所有前置结果才能开始下一步"时才用 `parallel`。

---

## 五、五个可以直接改的模板

### 模板 1：扇出调研（并行 + 汇总）

```js
const 主题 = [
  { 名: 'YOLO 检测', 要求: '讲清楚版本序列与选型' },
  { 名: '姿态估计', 要求: '对比主流方案与依赖难度' },
  { 名: '时序分析', 要求: '学术路线 vs 工程路线' },
]

phase('调研')
const 笔记 = await parallel(
  主题.map((t) => () =>
    agent(
      `你是技术调研员。请调研【${t.名}】，要求：${t.要求}。
       用 web_search 检索至少 3 次核实事实，不要编造库名和命令。
       把笔记写入 D:/program/out/${t.名}.md，然后只返回 5 行摘要。`,
      { label: t.名, phase: '调研' },
    ),
  ),
)

return { 完成: 笔记.filter(Boolean).length, 总数: 主题.length }
```

### 模板 2：生产者—验证者（这一步最值钱）

```js
phase('产出')
const 初稿 = await agent('写出第 1 节的内容，存到 D:/program/out/sec1.md', { phase: '产出' })

phase('审校')
const 意见 = await agent(
  `你是技术审校，任务是**找出错误**，找到越多越好。
   请 read 文件 D:/program/out/sec1.md，逐条核对：
   1) 有没有不存在的库名/命令/版本号（用 web_search 核实可疑点）
   2) 有没有前后自相矛盾
   3) 有没有明显缺口
   把问题清单写入 D:/program/out/sec1-review.md，只返回最严重的 3 条。`,
  { label: '审校 · 第 1 节', phase: '审校' },
)

return { 初稿长度: 初稿?.length ?? 0, 审校意见: 意见 }
```

### 模板 3：结构化产出（要表格不要散文）

```js
const 候选 = ['方案 A', '方案 B', '方案 C']

phase('评估')
const 评估 = await parallel(
  候选.map((c) => () =>
    agent(`评估「${c}」在 8GB 显存、Windows、Python 3.12 下的可行性。`, {
      label: c,
      phase: '评估',
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          方案: { type: 'string' },
          可行性: { type: 'string', enum: ['可行', '勉强', '不可行'] },
          理由: { type: 'string' },
          主要风险: { type: 'array', items: { type: 'string' } },
        },
        required: ['方案', '可行性', '理由', '主要风险'],
      },
    }),
  ),
)

// 现在是对象数组，可以直接用 JS 处理
const 推荐 = 评估.filter((x) => x && x.可行性 === '可行').map((x) => x.方案)
return { 全部: 评估, 推荐 }
```

### 模板 4：流水线（批量素材走同一套流程）

```js
const 文件 = ['a.md', 'b.md', 'c.md', 'd.md', 'e.md']

const 结果 = await pipeline(
  文件,
  (prev, 文件路径) => agent(`读取 ${文件路径}，提取 3-5 条可验证的事实断言，返回列表文本。`),
  (prev, 文件路径) => agent(`逐条核实下面的断言是否属实，用 web_search，标出错误项：\n${prev}`),
  (prev, 文件路径) => agent(`根据核实结果，把 ${文件路径} 改写为一份准确的中文摘要，写入 D:/program/out/clean-${文件路径}`),
)

return {
  总条数: 文件.length,
  成功条数: 结果.filter(Boolean).length,
  失败的文件: 文件.filter((_, i) => !结果[i]),
}
```

> 注意最后那个 `失败的文件` —— **一定要把失败项报出来**。`filter(Boolean)` 会把失败静默吞掉，看起来一切正常。

### 模板 5：两阶段（先发散，再基于结果收敛）

```js
phase('发散')
const 视角 = await parallel([
  () => agent('从"性能"角度分析这个方案的问题', { phase: '发散' }),
  () => agent('从"安全"角度分析这个方案的问题', { phase: '发散' }),
  () => agent('从"可维护性"角度分析这个方案的问题', { phase: '发散' }),
])

phase('收敛')
// 这里需要所有视角一起 —— 这种才适合用 parallel + 后续阶段
const 结论 = await agent(
  `下面是三个独立视角的分析，请综合成一份问题清单，按优先级排序：\n\n${视角.filter(Boolean).join('\n\n---\n\n')}`,
  { label: '综合', phase: '收敛' },
)

return 结论
```

---

## 六、写 workflow 的八条经验

1. **子 agent 看不到你的对话。** 提示词必须**自包含**——把背景、路径、要求、输出格式全写进去。
   （对比：`subagent_fork` 才会继承对话，但 workflow 里的 `agent()` 是全新的。）

2. **让 agent 自己把大产物写进文件，只让它返回短摘要。**
   否则几万字的调研结果会原路灌回来，把你自己撑爆。**文件是给未来的你的，摘要是给现在的你的。**

3. **给每个 agent 划清互斥的边界。** "你只负责 X，不要碰 Y"——不然 6 个 agent 会重复劳动。

4. **强制统一输出格式。** 6 份格式各异的笔记，汇总时你会想哭。

5. **永远配一个验证者。** 这是多 agent 相对单 agent 唯一"真·变强"的地方。见模板 2。

6. **控制并发数量。** 6-8 路并行是甜点区。20 路同时开，你既看不懂也管不住，还容易触发上限把整个脚本弄死。

7. **`return` 要返回可检查的东西。** 不要只 `return '成功'`。
   返回 `{ 完成数, 总数, 失败项 }`，主 agent 才能发现"其实挂了两个"。

8. **先在脑子里跑一遍。** 问自己：如果某个 agent 返回 `null`，我的脚本会崩吗？
   `.filter(Boolean)`、`?? '默认值'`、`if (!结果) continue` —— 这三招能挡掉大部分崩溃。

---

## 七、怎么运行

`workflow` 工具需要两个参数：

**`meta`** —— 身份信息（纯 JSON，不是代码）：

```json
{
  "name": "badminton-ai-research",
  "description": "六路并行调研，再由一个审校 agent 交叉核验",
  "whenToUse": "需要在一个陌生领域快速铺开资料时",
  "phases": [
    { "title": "调研", "detail": "6 个 agent 各自负责一个专题" },
    { "title": "审校", "detail": "1 个 agent 读完全部笔记找错" }
  ]
}
```

> `phases` 里的 `title` 必须和脚本里 `phase('...')` 的字符串**完全一致**，否则进度显示对不上。

**`script`** —— 脚本正文（只要函数体，**不要** `export const meta`，**不要** TypeScript）：

```js
const 结果 = await agent('...')     // 顶层 await 可以直接用
return { 结果 }                     // 最后一定要 return
```

**调用是前台阻塞的**：这个工具调用会一直等到整个脚本跑完才返回。

---

## 八、你要写的第一个 workflow（建议）

**别从大项目开始。** 按这个顺序练：

| 第几次 | 做什么 | 学到什么 |
|---|---|---|
| 1 | 2 个 agent 并行，各写一段话 | `parallel` 的基本用法 |
| 2 | 1 个写 + 1 个挑错 | 验证者模式的价值 |
| 3 | 3 个 agent 输出带 `schema` 的对象 | 结构化返回 |
| 4 | 5 个文件走 `pipeline` 三步 | 流水线 |
| 5 | 拿你自己的真实任务拆一次 | 边界怎么划 |

**每练一次，就打开 GUI 看那几张小卡片**：谁在跑、跑了多久、返回了什么。**看得见的编排，才是真的学会了。**

---

## 九、可运行的例子

`examples/` 目录下有四份可以直接改的脚本，从简单到复杂：

| 文件 | 练什么 |
|---|---|
| `01-hello-fanout.js` | 最小扇出：3 个 agent 并行写一段话 |
| `02-producer-verifier.js` | 生产者 + 验证者：一个写，一个挑错 |
| `03-structured-compare.js` | 结构化返回：`schema` + 汇总成表 |
| `04-research-pipeline.js` | 完整流水线：调研 → 核实 → 成稿 + 失败项报告 |

**用法**：把文件内容复制进 `workflow` 工具的 `script` 参数，`meta` 按上面格式填。
