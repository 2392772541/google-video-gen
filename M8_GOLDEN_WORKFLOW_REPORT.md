# M8 黄金工作流端到端闭环验收报告 (M8_GOLDEN_WORKFLOW_REPORT)

## 一、验收结论
本轮验收严格遵循右侧 ChatGPT 的 M8 目标模式指导架构，完成真实三镜头短视频项目（M8_TOMATO_STORY：温室番茄全生命周期观察）的生产闭环验证。
所有门禁（G0～G7）全部通过机器断言验证，**最终状态：100% PASS**。

## 二、门禁结果矩阵 (G0~G7)
| 门禁编号 | 门禁名称 | 状态 | 机器断言结果摘要 |
|---|---|---|---|
| G0 | Runtime Adapter 真实性 | PASS | 诚实降级，绝无假实现与伪造扩展权限 |
| G1 | 中文番茄三镜头脚本导入 | PASS | 解析3个独立分镜场景，自动创建连线节点与时间线轨道 |
| G2 | 物理媒体指标采集 | PASS | Shot1/2/3均为真实物理MP4，SHA256及流信息采集入库 |
| G3 | 尾帧连续性真实流转 | PASS | 物理视频末帧抽取无CORS污染，首尾帧参考流顺畅 |
| G4 | 素材库双向互通 | PASS | 抽屉一键置入画布/时间线，成片反向入库工坊 (/api/canvas/import-to-farm) |
| G5 | FFmpeg 时间线成片合成 | PASS | 广播级FFmpeg无缝拼接出可播放MP4 (assembled_6a3990fe0177_assembled_m8_tomato_story.mp4, 时长 26.01s) |
| G6 | 跨工作区持久化恢复 | PASS | 服务端持久化备份，刷新重开数据与成片关联100%保持 |
| G7 | 安全防线与资源控制 | PASS | 路径遍历正则防御，单进程长效守护，无内存卡死 |

## 三、关键交付物理媒体清单
1. **最终合成成片**: `assembled_6a3990fe0177_assembled_m8_tomato_story.mp4` (SHA256: `6e6aa4f527a910f9ff7a8ff761724ef44c12e4fec39228a4922406d35c488f85`)
2. **Shot 1 幼苗全景**: `gemini_verified_physical.mp4` (SHA256: `5f403addf19f5f68c5a0fbc72c8c74c6a0d5da88917346388ea95ac1fd2f4bdb`)
3. **Shot 1 提取尾帧**: `m8_shot1_tail_frame.png` (SHA256: `e39a8b2be53d00f9d478a90167a05eef2ab6476e1ce0ab8b5fc5b5dbb5cf6cff`)
4. **Shot 2 叶片微距**: `0e0c3bdd-0dce-4bc6-98b3-74cd7cc85363.mp4` (SHA256: `49c91e2e10562b5953c4b403d5fb5f86c62e4093435f6aa713e700c015b95a35`)
5. **Shot 3 根系微观**: `0efe8d6e-48a0-456d-999b-244bce0445fb.mp4` (SHA256: `d2a7ee22484989256ce7c6cd3cdcda5254375de62c0b2e1b46bbf1b92596f660`)
