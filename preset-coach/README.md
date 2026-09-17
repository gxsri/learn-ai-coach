# preset-coach · 一个可以直接装的 agent 预设

> 这是"如何搭建 agent preset"的**成品**。
> 教程在 `part1-多agent协作/03-手把手搭建preset.md`，这里是可直接使用的文件。

---

## 它是什么

一个基于官方 `standard` 预设复制、改了两处的 agent 组成：

| 改动 | 内容 |
|---|---|
| **① 人格** | 换成羽毛球分析工程助手；明确要求"偏好最小可运行脚本、先说清假设、不许编造库名和命令" |
| **② 新增一个自定义工具** | `tool-session-status.mjs` —— 扫描分析项目，报告每个 session 跑到哪一步了 |

其余的行（文件、Shell、Skills、子代理、workflow、ralph…）与官方 `standard` 完全一致。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `agent.cordis.yml` | 组成文件 —— 这个 agent 挂载哪些 plugin row |
| `preset.yml` | 显示名和描述 |
| `tool-session-status.mjs` | 自定义工具插件（本地文件行 `name: ./tool-session-status.mjs`） |

---

## 怎么安装

```powershell
# 复制到你的预设目录
Copy-Item -Path .\preset-coach\* -Destination "$env:USERPROFILE\.dsh\.agent-presets\coach" -Recurse -Force

# 重启 DSH，然后新建会话时选「羽毛球教练」
```

装完**验证两件事**：

1. 问它 **"你现在有哪些工具？"** —— 应该出现 `pose_status`
2. 调一下 `pose_status` —— 应该返回一张表格

> ⚠️ 预设列表里的 `broken` 标记**不等于**校验通过。
> 真正的验收只有一条：**新建会话，看工具列表对不对。**

---

## 静态校验（不启动会话就能查）

仓库里带了一个校验器：

```powershell
node .\part1-多agent协作\validate-preset.mjs "$env:USERPROFILE\.dsh\.agent-presets\coach"
```

它检查 YAML 能否解析（含 `!!js` 标签）、每行有没有 id/name、引用的包在不在
DSH 的 `node_modules` 里、本地 `.mjs` 存不存在且语法正确。

找不到 DSH 安装目录时会提示你用 `--root` 或 `DSH_APP_ROOT` 指定。

**它查不出**这三类（只有真正挂载才会暴露）：

- `invalid config: $.<字段> missing required value`
- `N row(s) did not activate: <id>: waiting for <服务>`
- `row(s) published process-global service(s) [<名字>]`

---

## 这个预设是怎么被验证的

不是"看起来对"，是**真的挂载过**：

| 预设 | 启用行数 | 全部 `fiberState` 一致 |
|---|---|---|
| `standard`（官方，已知可用） | 24 | ✅ 基线 |
| **`coach`** | **25** | ✅ 比基线正好多一行 |
| `liangshen`（另一个自写预设） | 25 | ✅ |

多出来的那一行正是 `tool-session-status` —— 说明**自定义插件真的激活了**。

> 踩过的坑：`fiberState` 是**数字枚举**，光看 `2` 判断不了它是不是"已激活"。
> 正确做法是**拿一个已知能用的预设当基线对照**，看差异是不是正好等于你的改动。

---

## 想改的话

| 想做什么 | 改哪里 |
|---|---|
| 改人格（它怎么说话、什么风格） | `agent.cordis.yml` 里 `persona` 那一行的 `text` |
| 让这个 agent 少一个能力 | 删掉对应的行，比如删 `tool-ralph` 就没有 ralph 了 |
| 加自己的工具 | 照着 `tool-session-status.mjs` 写一个 `.mjs`，再加一行 `name: ./你的文件.mjs` |
| 调整工具的输出目录 | `tool-session-status` 那一行的 `config.outputsDir` |

**两条铁律**（写在 `agent.cordis.yml` 的注释里）：

1. **会"提供服务"的行，必须包在带 `isolate` 的分组里** —— 否则第二个会话挂载时会撞名
2. **只消费 host 能力的行，绝对不能包 `isolate`** —— 包了就找不到 host 的实例，**静默失效**

第 2 条很阴险：**包错了不报错**，只是那个工具永远不出现。
