# 中文、英文及卡通音色候选

## 本机已有，可直接选择

| 音色 | 原生语言 | 特点 |
| --- | --- | --- |
| Vivian | 中文 | 明亮、带一点个性的年轻女声 |
| Serena | 中文 | 温柔年轻女声 |
| Uncle_Fu | 中文 | 低沉醇厚男声 |
| Dylan | 中文 | 北京口音青年男声 |
| Eric | 中文 | 四川口音、活泼略沙哑男声 |
| Ryan | 英文 | 有节奏感的男声 |
| Aiden | 英文 | 清晰明朗的美式男声 |

这些属于已安装 Qwen CustomVoice；官方说明所有预设可说模型支持的语言，原生语言通常效果更佳。原有 Ono_Anna 为轻巧活泼的女声，也能用 Qwen 输出中文或英文，它与卸载的 VOICEVOX 无关。

来源：[Qwen 官方音色说明](https://github.com/QwenLM/Qwen3-TTS#custom-voice-generation)。

## 建议补充：固定英文男女声（尚未安装）

Kokoro-82M：女声 `af_heart`、`af_bella`，男声 `am_puck`、`am_michael`。官方列表给 Heart/Bella 的评级优于这两款男声；具体喜好仍需试听。它们是正常配音候选，尚未验证卡通效果。

Kokoro 也提供中文女声 `zf_xiaobei`、`zf_xiaoni`、`zf_xiaoxiao`、`zf_xiaoyi`，男声 `zm_yunjian`、`zm_yunxi`、`zm_yunxia`、`zm_yunyang`，但官方中文评级均为 D，所以中文优先继续用 Qwen。

来源：[Kokoro 官方音色目录与试听入口](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)。

## 更贴近卡通需求：Qwen VoiceDesign（尚未安装）

VoiceDesign 支持按描述创建声音，生成参考录音后可交给现有 Base 模型保存为可复用音色。建议先制作以下原创角色方向；这些是设计提案，不是已经存在或试听确认的音色。

| 方向 | 描述建议 | 语言 |
| --- | --- | --- |
| 元气女主 | 明亮、轻快、清晰，情绪表达活泼 | 中文 / 英文 |
| 温柔治愈女声 | 柔和、亲切、语调自然，有故事感 | 中文 / 英文 |
| 热血青年男声 | 清亮有力、节奏鲜明，避免大喊 | 中文 / 英文 |
| 沉稳角色男声 | 低沉有磁性、咬字清楚，保留戏剧感 | 中文 / 英文 |

优先建议 VoiceDesign：更符合中英文卡通人物需求，并可复用当前录音音色库。固定英文声线则先选 Kokoro Heart/Bella 补足女声。

来源：[Qwen VoiceDesign 与克隆复用流程](https://github.com/QwenLM/Qwen3-TTS#voice-design-then-clone)。
