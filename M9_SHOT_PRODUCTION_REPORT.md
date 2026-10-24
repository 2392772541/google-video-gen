# M9 镜头级精细化生产与跨镜头一致性验收报告 (M9_SHOT_PRODUCTION_REPORT)

## 一、验收总览
本轮严格遵循右侧 ChatGPT 的 M9 目标模式与指导原则，从“系统能否生成作品”正式转入“日常生产是否高效、可控、可修改、可恢复”。
完成了 P0（单镜头独立重生成与版本回退）、P1（工程全局视觉规范与主体锁定）、P2（脚本转分镜预览与防重复构建）、P3（失败恢复与精准 18.00s 时间线裁切合成）。
全门禁测试（G0，测试 A～G）全部由机器断言客观通过，**最终状态：100% PASS**。

## 二、测试门禁与断言矩阵 (Test Matrix)
| 门禁测试项 | 状态 | 机器断言结果详情 |
|---|---|---|
| **G0 收口与诊断** | PASS | 确认旧 M8 工程正常读取；查明 64 节点来自脚本未清空累加，26.01s 来自全长未裁切原片 |
| **测试 A 单镜头重生成** | PASS | 只重生成 Shot 2，Shot 1 和 Shot 3 物理哈希恒定未变；保留 V1/V2 两个候选版本并可无损回退 |
| **测试 B 依赖与失效** | PASS | Shot 2 切换版本自动触发 Shot 3 `STALE_REFERENCE` 失效告警，支持明确保留旧参考或绑定新尾帧 |
| **测试 C 视觉规范锁定** | PASS | Project Visual Bible 提示词编译器成功将全局摄影风格与主体特征融合，并支持镜头局部运镜独立覆写 |
| **测试 D 脚本导入预览** | PASS | 脚本输入框实时渲染分镜表格，包含镜头号、标题、时长；`scriptClearCanvas` 防翻倍机制使节点收敛至 13 个 |
| **测试 E 失败恢复隔离** | PASS | Shot 2 失败时 Shot 1/3 保持完成；单镜头重试独立执行，不影响其他镜头 |
| **测试 F 18s 精准裁切** | PASS | FFmpeg 精准入出点剪裁 (0~6s x 3)；实际成片时长 18.00s 严格对齐 18.00s 编辑目标 |
| **测试 G 老工程兼容** | PASS | M8_TOMATO_STORY 完全兼容读取，新增镜头控制字段完全向下兼容 |

## 三、关键交付物理文件
1. **最终精准 18.00s 成片**: `assembled_c2b4c92a6af8_assembled_m9_tomato_exact_18s.mp4` (时长: `18.00s`, 规格: `1280x720`, SHA256: `bf2fa0757d2fb5ea6394f127f9eecd55a9ee04fe7fc7226522fa1f5f881de263`)
2. **Shot 2 候选版本 1**: `0e0c3bdd-0dce-4bc6-98b3-74cd7cc85363.mp4` (SHA256: `49c91e2e10562b5953c4b403d5fb5f86c62e4093435f6aa713e700c015b95a35`)
3. **Shot 2 候选版本 2**: `10be203a-c921-4c7d-a2c5-6b95fec5bd85.mp4` (SHA256: `ca4d9b36092b37aa2a5b64c91c8ac7bb7e4e1b557b683c3dfc372d9df64f52a8`)
4. **Shot 1 稳定成片**: `gemini_verified_physical.mp4` (SHA256: `5f403addf19f5f68c5a0fbc72c8c74c6a0d5da88917346388ea95ac1fd2f4bdb`)
5. **Shot 3 稳定成片**: `0efe8d6e-48a0-456d-999b-244bce0445fb.mp4` (SHA256: `d2a7ee22484989256ce7c6cd3cdcda5254375de62c0b2e1b46bbf1b92596f660`)
6. **预览存证截图**: `M9_EVIDENCE/m9_script_clean_preview.png`
