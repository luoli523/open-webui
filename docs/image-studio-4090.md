# 4090 图像工作台

入口：`/audio-studio` → **生成图像**，目前仅管理员可见。原有本机 ComfyUI、云图像、语音与 H3 设置保持独立。

## 服务连接

1. 在 local-tts 的 Ubuntu NVIDIA 主机完成 `bash scripts/image_cuda.sh install`。
2. 执行 `bash scripts/image_cuda.sh api-install` 和 `api-start`，服务监听远端 `127.0.0.1:8093`。
3. 建立 SSH 隧道，将本机 `127.0.0.1:28093` 转发到远端 `127.0.0.1:8093`。
4. 展开工作台“4090 连接设置”，填写该本机地址，输入远端 `run/image-api.key` 密钥并启用。密钥保存在后端配置，不返回浏览器。

当前机器使用独立 launchd 隧道 `com.luoli.image-4090-tunnel`，原 H3 隧道继续使用 28092。

## 生成

- 默认 **4090 · Viggle Turbo · 6 步**，可选 **4090 · Qwen Image · 40 步**。
- 无参考图时生成 1024×1024；上传一张 PNG/JPEG/WebP 后按指令编辑，约 1MP 并保持参考图宽高比。
- 参考图上限 10 MB、1600 万像素、宽高比 1:4 至 4:1。
- seed 留空随机；固定同一 seed 便于比较两种模式。
- 每次一张，结果通过已有 Files 服务鉴权保存，历史按用户隔离，显示最近 50 条。
- GPU 与 H3 共用，忙时返回重试提示；页面显示等待秒数，不作固定耗时承诺。
- 请求是同步的；浏览器离开或网络中断可能仍会完成远端任务。暂不提供排长队或取消操作。

## 实现

后端 `/api/v1/image-studio/config`、`/images` 复用管理员认证。连接地址仅允许 loopback HTTP，拒绝重定向。图片结果和元数据会在保存前校验。历史复用媒体记录表 `video_studio` 的独立 `image` 类型，不需迁移既有视频数据。

生产构建：`NODE_OPTIONS=--max-old-space-size=8192 npm run build`，然后 `./owui.sh restart`。
