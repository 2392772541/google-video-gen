# Gemini 网页端视频生成成功基线与物理核验报告 (Gemini Success Baseline)

## 1. 物理产物与机器断言证据 (Physical Artifact & Cryptographic Evidence)
- **文件绝对路径**: `C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\gemini_verified_physical.mp4`
- **文件物理体积**: `7,098,367` 字节 (~7.10 MB)
- **SHA-256 哈希**: `5F403ADDF19F5F68C5A0FBC72C8C74C6A0D5DA88917346388EA95AC1FD2F4BDB`
- **生成会话源**: `https://gemini.google.com/app/985128971f049cad`
- **生成账号**: Google Pro 账号 (`Gopal Kumar Pro`, Chrome Profile `profile_gflow-test`)
- **生成参考输入**: 真实单张参考图 (`gemini_test_ref.png`) + 英文电影级动作提示词

## 2. ffprobe 机器物理流核验 (ffprobe Audio/Video Stream Inspection)
```json
{
    "streams": [
        {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1280,
            "height": 720,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "16:9",
            "duration": "10.000000"
        }
    ],
    "format": {
        "duration": "10.005000",
        "size": "7098367"
    }
}
```

## 3. 根因消除与防护措施 (Root Cause Eliminated & Hardened Guardrails)
1. **彻底消除 `:last-child` 导致的漏检与超时**:
   - 旧代码采用 `model-response:last-child video` 与 `model-response:last-child button`，在 Gemini 最新版网页结构中因存在同级 hover/action 容器，`:last-child` 匹配结果恒为 0，导致即便网页端生成成功也超时作废；
   - 现已重构为：优先扫描全局原生成片下载入口 `button[aria-label*='Download video' i], a[download]`，通过 `expect_download` 直接提取原片（耗时 <2s）；并辅以 `page.evaluate` 在安全上下文中以 `currentSrc` 提取视频流。
2. **单图参考放行与时长不可控机制**:
   - `model-spec.ts` 明确 Gemini 支持 `supportsIngredients: true`, `maxReferences: 1`；
   - 界面明确告知用户“Gemini 网页端时长为平台服务端默认决定（不可控）”，不设虚假滑块，后端不再因与请求时长秒数差异误判作废。
3. **无限画布回填与持久化**:
   - 生成视频落盘后通过 `/videos/{task_id}/content` 供前端播放；
   - 经 Playwright 自动化验证，在刷新页面后节点元数据与视频播放状态 100% 保持。
