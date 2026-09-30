# 视频字幕

已完成视频卡片 → **字幕** → **生成字幕**。任务在本机后台运行，可关闭面板后返回。

## 使用

1. 语言默认自动检测，也可选择工作台的十种语言。
2. 对照视频校对文字、开始/结束秒数。点击句子序号定位；拆分按文字和时长中点分开，需要人工微调；可与下句合并。
3. 调整字号、颜色、顶部/底部、边距和底框，然后保存。字号与边距以 720 像素画布为基准随视频缩放。
4. 下载 SRT、VTT、ASS；或点击「生成带字幕视频」，完成后观看、下载 MP4、发送字幕版 TG。
5. 原片下载和原片 TG 保留在原卡片。字幕修改后需重新烧录；旧版本不会作为当前字幕版发出。TG 发送回执按文件摘要去重，结果不明时先核实再重发。

字幕按实际成片音轨生成。有完整文案的完整视频使用 forced alignment；被截短的预览及缺少原文的视频使用 ASR，避免将完整文案塞入 15 秒预览。新建视频会保存文案快照，历史视频会读取原播报记录作为回退。预览与完整版各自维护字幕。

识别/对齐并不保证每个词都准确。编辑器的样式预览为近似效果；字体、自动换行以 libass 输出为准。中文默认使用本机 PingFang SC；其他系统须安装中文字体并配置对应字体回退。

## 本地部署

独立虚拟环境，不改变 Open WebUI 或 local-tts 的 Python 依赖：

```bash
uv venv .venv-subtitles --python 3.11
uv pip install --python .venv-subtitles/bin/python -r scripts/requirements-subtitles.txt
brew install ffmpeg-full
```

默认复用 `~/.cache/whisper/small.pt`；不会自动下载模型，也不调用云端字幕服务。

可用环境变量：

- `STUDIO_SUBTITLE_PYTHON`：独立字幕环境 Python 的绝对路径；默认项目 `.venv-subtitles/bin/python`。
- `STUDIO_WHISPER_MODEL`：本地 OpenAI Whisper 格式 checkpoint；默认 `~/.cache/whisper/small.pt`。MLX 格式不能直接替代。
- `STUDIO_SUBTITLE_FFMPEG`：含 libass 的 FFmpeg；macOS 优先 `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`，否则 PATH。

stable-ts 适配器位于 `scripts/subtitle-engine.py`，输入/输出均为本地 JSON 文件。若后续替换对齐模型，可保留这个边界和持久化任务接口。当前固定 stable-ts 2.19.1、Whisper 20250625、torch/torchaudio 2.8.0，CPU 4 线程，避免挤占 local-tts 的 GPU；长片字幕可能耗时数分钟。stable-ts 上游已暂停开发，因此保持隔离和固定版本。

## 接口及持久化

均在 `/api/v1/video-studio`，需登录并属于视频所有者：

- `GET /jobs/{id}/captions`：字幕状态、时间轴、样式、原文。
- `POST /jobs/{id}/captions`：`{revision?, language}` 生成/重新生成。已有字幕必须带当前 revision；重复进行中的请求返回已有任务。
- `PUT /jobs/{id}/captions`：`{revision, cues:[{start,end,text}], style:{size,color,position,margin,background}}`。
- `POST /jobs/{id}/captions/render`：`{revision}`，对当前保存版本烧录。
- `GET /jobs/{id}/captions/file?format=srt|vtt|ass|mp4`：鉴权下载。
- `POST /jobs/{id}/telegram?variant=original|captioned`：管理员显式发送。默认保持原片兼容行为。

`video_studio` 表使用 `kind=caption`，不增加迁移；`revision` 负责并发编辑，`version` 代表字幕内容，`rendered_version` 绑定成片。生成/渲染共用持久队列，独立单领导者 worker 和进程锁；运行中不可编辑或删除关联视频，重启将中断任务标记失败，不自动重跑。视频和字幕不调用彼此的模型生成接口。

文件使用视频 ID 前缀存于 `video-studio/`。原片不覆盖；字幕成片按版本命名，成功发布新版本后清理旧成片。删除视频会清理字幕成片和临时文件，失败由既有后台清理重试。SRT/VTT/ASS 按已保存内容即时导出；渲染用临时 ASS 完成后清除。

回滚代码不会破坏原视频，caption kind 和附加 JSON 字段可保留；回滚后清理旧字幕产物需重新启用新代码的清理器。

## 验证记录

本次不添加或运行自动化测试，也不触发付费视频生成或 TG 实发。已核实本机 Whisper checkpoint、Python 依赖导入、FFmpeg ass/subtitles 滤镜可用；Python 静态检查与生产构建通过；Svelte 检查保持既有 7001 errors / 198 warnings / 344 files 基线。服务已重启就绪。字幕实际对齐质量、视频烧录与浏览器交互仍需使用真实素材验收。

参考：[stable-ts 官方文档](https://github.com/jianfch/stable-ts)、[FFmpeg 字幕滤镜](https://ffmpeg.org/ffmpeg-filters.html#subtitles-1)、[Homebrew ffmpeg-full](https://formulae.brew.sh/formula/ffmpeg-full)。
