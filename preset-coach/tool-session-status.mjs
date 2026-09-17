/**
 * tool-session-status.mjs —— 一个最小可用的自定义工具插件样本。
 *
 * 它教三件事：
 *   1. 一个 preset 插件文件必须导出什么（name / inject / apply）；
 *   2. 怎么往 host 的 `tools` 注册表注册一个模型可调用的工具；
 *   3. 怎么读 YAML 那一行里传进来的 `config`。
 *
 * 工具本身：扫描羽毛球动作分析项目的 outputs 目录，报告每个 session
 * 在"骨架 → 击球 → 指标 → 报告"四步流水线上跑到哪了。
 *
 * 这个文件不依赖任何 DSH 内部服务，只用 Node 标准库 + ctx.tools.register，
 * 所以它是最安全的入门模板。
 */

import { readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'

/** 插件名：挂载失败时，报错信息用它定位是哪一行出的问题。 */
export const name = 'tool-session-status'

/**
 * 硬依赖。写成 `['tools']` 的意思是：工具注册表必须先存在，本行才会激活。
 * 如果这个服务永远不出现，挂载会报 "waiting for tools" —— 那正是
 * agent.cordis.yml 里说明的"某一行没有激活"的第四类失败。
 *
 * 注意：只有"离不开"的服务才写在这里。可选的服务要用 ctx.get('名字') 拿，
 * 拿到 undefined 就优雅降级，而不是让整行挂不上。
 */
export const inject = ['tools']

/** 流水线产物：文件名 + 中文短名，顺序即表格列顺序。 */
const STAGES = [
  ['01_pose.csv', '骨架'],
  ['02_events.csv', '击球'],
  ['03_metrics.json', '指标'],
  ['report.html', '报告'],
]

/** 没在 YAML 里配置时用的默认目录。 */
const DEFAULT_OUTPUTS_DIR = 'D:\\program\\learn-ai-coach\\starter\\outputs'

/**
 * 每个挂载本插件的实例调用一次。
 * @param {object} ctx Cordis 上下文
 * @param {object} [config] 来自 agent.cordis.yml 中该行的 `config:` 块
 */
export function apply(ctx, config) {
  const outputsDir =
    typeof config?.outputsDir === 'string' && config.outputsDir.length > 0
      ? config.outputsDir
      : DEFAULT_OUTPUTS_DIR

  ctx.tools.register({
    name: 'pose_status',

    // description 是写给「模型」看的，不是写给人看的。
    // 重点是"什么时候该调用我"，而不只是"我是什么"。
    description: [
      '查看羽毛球动作分析项目的进度：列出 outputs 目录下的每个 session，',
      '以及「骨架 / 击球 / 指标 / 报告」四步各自是否已经产出。',
      '当用户问"跑到哪一步了""有哪些结果""还差什么"时使用。',
      '不读取视频内容，也不运行任何分析。',
    ].join('\n'),

    // 参数用 JSON Schema 描述。这个工具不需要参数。
    parameters: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },

    // output.schema 约束返回值的形状；render 决定在 GUI 里渲染成什么。
    // 返回一个 { text } 对象，render 把它变成一段文本 —— 这是最简单的形态。
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { text: { type: 'string' } },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },

    /**
     * 真正干活的函数。
     *
     * 约定：出错时**返回一句可读的话**，不要 throw。
     * throw 会变成一次红色的工具错误，模型只能重试；
     * 而返回"读不到目录 X，因为 Y"能让模型自己去纠正路径。
     */
    async execute() {
      let entries
      try {
        entries = await readdir(outputsDir, { withFileTypes: true })
      } catch (error) {
        return {
          text: `读不到输出目录：${outputsDir}\n原因：${error.message}\n`
            + '（还没有跑过分析，或者该行 config.outputsDir 路径不对。）',
        }
      }

      const sessions = entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .sort()

      if (sessions.length === 0) {
        return { text: `输出目录存在，但下面还没有任何 session：${outputsDir}` }
      }

      const header = `| session | ${STAGES.map(([, label]) => label).join(' | ')} |`
      const divider = `|---|${STAGES.map(() => '---').join('|')}|`

      const rows = []
      for (const session of sessions) {
        const cells = []
        for (const [file] of STAGES) {
          const exists = await stat(join(outputsDir, session, file))
            .then(() => true, () => false)
          cells.push(exists ? '✅' : '—')
        }
        rows.push(`| ${session} | ${cells.join(' | ')} |`)
      }

      return {
        text: [`共 ${sessions.length} 个 session（目录：${outputsDir}）`, '', header, divider, ...rows].join('\n'),
      }
    },
  })
}
