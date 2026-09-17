/**
 * 例 3 · 结构化返回（Structured Output）
 * ---------------------------------------------------------------
 * 练什么：用 opts.schema 拿到「对象」而不是「一段散文」，
 *         这样结果可以直接用 JS 处理（筛选、排序、生成表格）。
 *
 * schema 只能用这些关键字：
 *   type / properties / required / additionalProperties / items / enum / const / oneOf
 * 不能用 pattern / format / minimum 之类。顶层必须是 type: 'object'。
 *
 * meta（配套填写）：
 * {
 *   "name": "structured-compare",
 *   "description": "并行评估多个姿态估计方案，返回结构化结论并筛选",
 *   "phases": [{ "title": "评估" }]
 * }
 */

const 方案 = ['MediaPipe Pose', 'Ultralytics YOLO-pose', 'RTMPose / MMPose']

const 评分表结构 = {
  type: 'object',
  additionalProperties: false,
  properties: {
    方案: { type: 'string' },
    安装难度: { type: 'string', enum: ['低', '中', '高'] },
    支持多人: { type: 'boolean' },
    许可证: { type: 'string' },
    适合新手入门: { type: 'boolean' },
    一句话理由: { type: 'string' },
    主要坑: { type: 'array', items: { type: 'string' } },
  },
  required: ['方案', '安装难度', '支持多人', '许可证', '适合新手入门', '一句话理由', '主要坑'],
}

phase('评估')

const 结果 = await parallel(
  方案.map((名称) => () =>
    agent(
      `请评估姿态估计方案「${名称}」在以下条件下的适用性：
       - 操作系统 Windows，Python 3.12
       - 显卡 RTX 4060 Laptop 8GB
       - 场景：羽毛球视频，画面里 2-4 人，快速移动
       - 使用者：有 AI 概念、Python 实操少、主要靠 AI 助手写代码

       请用 web_search 核实许可证和是否支持多人，不要凭印象。
       按给定的 JSON 结构返回。`,
      { label: 名称, phase: '评估', schema: 评分表结构 },
    ),
  ),
)

// 到这里 结果 已经是对象数组（失败项是 null），可以直接用 JS 处理
const 有效 = 结果.filter(Boolean)

// 生成一张 Markdown 表格 —— 这就是「结构化」的价值：能直接加工
const 表头 = '| 方案 | 安装难度 | 多人 | 许可证 | 适合新手 | 理由 |'
const 分隔 = '|---|---|---|---|---|---|'
const 行 = 有效.map(
  (x) => `| ${x.方案} | ${x.安装难度} | ${x.支持多人 ? '✅' : '❌'} | ${x.许可证} | ${x.适合新手入门 ? '✅' : '❌'} | ${x.一句话理由} |`,
)

return {
  成功数: 有效.length,
  总数: 方案.length,
  推荐入门: 有效.filter((x) => x.适合新手入门).map((x) => x.方案),
  表格: [表头, 分隔, ...行].join('\n'),
  // 把每个方案踩的坑单独汇总，方便一次性看到风险
  风险汇总: 有效.map((x) => ({ 方案: x.方案, 坑: x.主要坑 })),
}
