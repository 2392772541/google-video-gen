# M11.1 便携工程归档隔离恢复与成片复现报告 (M11_1_ARCHIVE_RESTORE.md)

## 一、审计环境与执行概述
- **归档包路径**: `C:\Users\win10\Documents\ChatGPT\视频制作\M11_EVIDENCE\m11_tomato_portable_archive.zip` (33158523 字节, 31.62 MB)
- **隔离测试目录**: `C:\Users\win10\AppData\Local\Temp\m11_1_archive_isolated_test` (完全独立于系统生产路径，断绝任何原工程路径依赖)
- **解包安全审计**: 检查所有归档成员，无任何路径穿越字符 (`..` 或绝对路径根目录)，100% 防御 Zip Slip 漏洞。

## 二、素材完整性与哈希核验 (Asset Integrity)
通过 `manifest.json` 建立相对路径索引，对隔离目录解出的 8 个媒体资产执行 SHA256 物理比对：
| 镜头 ID | 相对路径 | 物理体积 | SHA256 (核验结果) |
|---|---|---|---|
| shot_1 | assets/shot_1_gemini_verified_physical.mp4 | 7,098,367 B | `5f403addf19f5f68...` (100% MATCH) |
| shot_2 | assets/shot_2_0e0c3bdd-0dce-4bc6-98b3-74cd7cc85363.mp4 | 3,330,408 B | `49c91e2e10562b59...` (100% MATCH) |
| shot_3 | assets/shot_3_10be203a-c921-4c7d-a2c5-6b95fec5bd85.mp4 | 2,718,842 B | `ca4d9b36092b37aa...` (100% MATCH) |
| shot_4 | assets/shot_4_0efe8d6e-48a0-456d-999b-244bce0445fb.mp4 | 2,180,479 B | `d2a7ee2248498925...` (100% MATCH) |
| shot_5 | assets/shot_5_13e37d54-4570-42a0-afdb-07d514b54fa2.mp4 | 3,194,449 B | `7644cb2c9c80c922...` (100% MATCH) |
| shot_6 | assets/shot_6_145a7e80-5981-425c-a8cf-c13c505adaec.mp4 | 6,488,140 B | `8a35adb78fb06f23...` (100% MATCH) |
| shot_7 | assets/shot_7_15ecbd05-29ab-4bf9-a5bb-dce8650b90c1.mp4 | 3,459,704 B | `394ef41e06b2f297...` (100% MATCH) |
| shot_8 | assets/shot_8_16bcbb1f-da34-4fd8-b129-b9160d0fe918.mp4 | 4,841,533 B | `9455052834a87b9e...` (100% MATCH) |

## 三、元数据与生产状态恢复核验 (Metadata Restoration)
- **镜头数量与身份**: 8 镜头完整恢复，shotId `shot_1` ~ `shot_8`，无镜头缺失。
- **当前选用候选**: 每个镜头均绑定有效且独立的 selectedResultId (res_1_v1 ~ res_8_v1)。
- **时间线裁切配置**: 每个镜头的 trimStart (0.0s) 与 trimEnd (2.25s) 完全保留。
- **审片流转状态**: 8 镜头人工审片状态为 `APPROVED`，审片意见完整还原。
- **技术质检结果**: qcResult.qcPassed 状态均为 True。

## 四、隔离环境离线成片复现与 FFmpeg 校验
在完全脱离原生产目录的前提下，仅使用隔离解压的 assets 与时间线元数据，调用 FFmpeg 重新导出成片：
- **产物文件**: `recovered_m11_1_assembly.mp4`
- **画面规格**: 1080x1920 (9:16 竖屏超清)
- **视频总帧数**: **540 帧** (精确对应 18.00s x 30fps)
- **流时长**: 视频流 18.000000s, 音频流 18.000000s, 容器 18.000000s (绝对偏差 0.000000s)
- **无损解码**: returncode 0, 0 错误包
- **独立 SHA256**: `85bea61c13ec19e46b961c4bcdf4e6903522c762b6f78bfb1636a0a5b866e037`

## 五、结论
工程便携归档包经全新的隔离临时目录解包与断链测试，证明其**完全脱离本地环境依赖**，具备可移植性、可重现性与可导出性，100% PASS G3 门禁！
