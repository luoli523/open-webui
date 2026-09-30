# 本地语音工作台

入口：`/audio-studio`。页面包含生成播报、我的音色和管理员 Telegram 设置。

## 使用

- 选择 guige、luwei 或预设音色，输入文案生成。后台完成后可试听、下载 MP3/WAV。
- 「我的音色」支持上传 1–120 秒、最大 20 MB 的录音，或通过麦克风录制。
- 参考原文选填：留空采用声音特征，有原文采用录音与文本参考。自动识别使用本机 Whisper，结果可修改。
- 麦克风需要浏览器授权及安全上下文：本机使用 `http://localhost:8080`；通过局域网 IP 的普通 HTTP 页面可能无法录音，可用上传或配置 HTTPS。
- 新建音色归当前用户所有；既有 guige/luwei 可选择，由管理员编辑。重命名保持 ID，替换录音产生版本。
- 删除音色会从列表隐藏；旧版本保留，避免损坏排队任务和已生成音频。
- 生成历史显示最近 50 条。失败或重启中断可重新生成；点击重新生成采用该音色当前版本。
- 第一版 Telegram 设置和发送仅面向管理员，使用一个默认目标；私聊先向 Bot 发 `/start`，群组/频道确保 Bot 有发送权限。
- Telegram 结果不确定时先核对聊天，再选择「已收到」或「确认未收到，允许重试」。不会自动重发。

## 服务与数据

- `local-tts`：`http://127.0.0.1:8091`。保持回环监听；WebUI 通过后端代理访问，拒绝浏览器带 Origin 的直接写请求。
- WebUI 后端可通过 `LOCAL_TTS_BASE_URL` 改变回环端口。当前设计用于本机直接运行。
- 音色：`local-tts/voices/<id>/voice.json` 与 `versions/<version>/reference.wav/reference.txt`。
- 既有 `voices/guige/reference.*` 和 `voices/luwei/reference.*` 自动发现，编辑时保存不可变快照。
- local-tts 新增 `studio_voices.py`、`mlx-whisper==0.4.3`；TTS 和 ASR 共用一个 GPU 工作线程。
- 转写使用现有 `~/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx/snapshots/`，不自动下载或回退云端。
- 任务/回执在 WebUI 的 `audio_studio` 表，音频在 `$DATA_DIR/audio-studio/`。
- Telegram Token 在管理员后端配置 `audio.studio.telegram`。普通用户无法读取；前端配置 API 只返回配置状态与目标。
- 当前工作进程采用本机文件锁。运行一台主机、一个后端 worker；不适用于多主机共享数据库部署。

## 源码运行

使用 Node 22（本仓库要求不高于 22）安装和构建：

```sh
npm ci
NODE_OPTIONS=--max-old-space-size=8192 npm run build
```

复用已安装的 Open WebUI 0.11.4 Python 依赖，设置以下环境再运行：

```sh
export DATA_DIR="$HOME/.open-webui"
export PYTHONPATH="$PWD/backend"
uvx --python 3.11 --from open-webui==0.11.4 python scripts/serve-source.py --host 0.0.0.0 --port 8080
```

先停止占用 8080 的旧实例。`serve-source.py` 保留原数据目录的签名密钥，设置源码构建和静态资源目录。
本机原有、Git 忽略的 `owui.sh` 另已增加 `source` / `release` 命令，分别切换源码版和 PyPI 版；登录自启动继续使用同一脚本。

可用 `scripts/import-studio-telegram.py <本地env文件> <WebUI数据库>` 迁入已有 Telegram 配置，脚本不输出凭证。应在备份后、受控本地环境下执行。

## 验证

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_audio_studio.py -v
# 在 local-tts 项目中：
.venv/bin/python -m unittest discover -s tests -v
```

类型检查 `npm run check` 当前存在大量仓库基线错误；必须区分新增文件诊断和原有诊断。构建与实际接口联调应独立验证。

## 备份与回滚

部署前用 SQLite backup API 备份数据库，并保存 `owui.env`、原 `owui.sh` 与 local-tts 的配置/音色元数据。
新增迁移 `a71d90ce2401` 只创建 `audio_studio` 表，不改变原有业务表。

回滚时先停源码实例；旧版 Alembic 不认识新 revision，不能直接切回旧包后启动。保留数据库副本后，用本源码环境 downgrade 到 `d4c1a8e37b62`（会删除工作台任务/回执），或恢复升级前备份（会丢失升级后的数据库变更），再运行 `owui.sh release`。音频和音色素材保持备份，不随回滚删除。
