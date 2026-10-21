# Circuit Video Skills · 电路讲义转视频

默认是一条五节点制作流程：原讲义与完整选定范围 → 单一正式稿和场景计划 → 专用发音衍生与完整字幕 → 真实音频证据驱动的时间线和 MP4 → 局部复核与返工。内容忠实讲义，制作流程尽量简单；不把所有模型验证工具叠成必经关卡。

当前为有界公开版本。已完成的私有制作案例不随代码发布，也不代表任意讲义都能无人工判断地自动转换。正式稿编写和独立源稿/视听比较由实际 AI 助手工作完成，不是预置答案或一个神奇的自动解析命令。

## 0.2.1 编写提示更新

按学习目标与已有知识选择解释深度：画面承载可读的精确结构，旁白说明含义、关系和必要推理，并在继续展开已无助于理解时推进。正式稿仍是唯一配音/完整字幕正文，完整选定内容由旁白与画面共同覆盖。这是编写指导的改进，不保证每次稿件都理想或结构自动有效；沿用既有结构和源稿核验，不新增风格审查或改写环节。

## 安装

已测试 Python 3.12。自行安装 FFmpeg/ffprobe 和中文字体；Linux 可用 Noto CJK Regular/Bold。默认寻找已安装 Noto Sans CJK SC，也可设置 CIRCUIT_FONT_REGULAR、CIRCUIT_FONT_HEADING 指向自己的字体。没有捆绑字体。

```sh
python -m venv .venv
# 激活虚拟环境后，先阅读 THIRD_PARTY_NOTICES.md 中 PyMuPDF 的许可边界。
python -m pip install -r requirements-production.txt
# 仅在需要且已获授权使用 Edge 服务时安装：
python -m pip install 'edge-tts==7.3.1'
```

只运行本地无声渲染器可改装 requirements.txt，不需要 PDF 或 TTS 依赖。可选模型测试另外安装 requirements-p1.txt；它不是普通讲义制作的前置门。具体已测试版本见 skills/circuit-teaching-video/config/requirements-tested.txt，不是跨平台锁文件。

## 默认五节点命令

将整个 skills/circuit-teaching-video 作为 Skill 加载，读取 [SKILL.md](skills/circuit-teaching-video/SKILL.md) 与 [输入输出合同](skills/circuit-teaching-video/authoring/CONTRACT.md)。PDF、PAGES 和 PROJECT 由本次任务提供，PAGES 是完整选定单元的物理页号。

```sh
SKILL=skills/circuit-teaching-video
python "$SKILL/scripts/course_video.py" prepare --source "$PDF" --pages "$PAGES" --project "$PROJECT"
# 新的 AI 编写步骤读取 author-request.md、全部选定原页图像和文字，
# 生成唯一 AUTHOR_RESPONSE；另一次实际源稿比较检查完整覆盖。
python "$SKILL/scripts/course_video.py" ingest --project "$PROJECT" --plan "$AUTHOR_RESPONSE"
python "$SKILL/scripts/course_video.py" voice-input --project "$PROJECT"
# 只有适用授权允许发送旁白时才执行；开关本身不构成许可：
python "$SKILL/scripts/course_video.py" synthesize --project "$PROJECT" --allow-network
python "$SKILL/scripts/course_video.py" render --project "$PROJECT"
python "$SKILL/scripts/course_video.py" qa --project "$PROJECT" --review "$AV_REVIEW"
```

若服务已返回完整原始音频，但句边界重叠或狭窄标点差异使旧适配器拒绝，保留首次失败，离线调用 bind-voice --raw-run "$RAW_RUN"。只有明确接受该投影时才加 --allow-whitespace-comma-projection，不要为了修元数据再请求配音。改变词语、乱序、缺句或多句事件不会被悄悄修好；大段请求的服务分块可能仍触发明确失败，不能靠删除教学内容规避。

CourseProject 仅有 SourcePackage、LessonPlan、MediaTimeline、BuildManifest 四部分。字幕始终来自完整正式稿；发音变化不改变字幕正文。布局返工复用同一已验证音频，声音/正式稿变化使旧音频或时间线失效；所有旧响应、失败和版本保留。最新尝试与历史成功分开，技术成功不等于视听、科学或发布批准。没有强制用户中途听审。

## 可选强解析器入口

默认无需另装解析器即可保留原页。已手动配置并确认适用许可时，可在 prepare 之后、正式稿编写之前使用外部 MinerU 4.0.12 basic 作为主要结构提取来源；不要把多个解析器串行跑一遍。模型须事先全部缓存，适配器在导入 ORT 前禁用遥测并设离线模式，缺模型会停止，不会自动下载。不同代码/模型各有条款，本仓库 MIT 不能替代它们。

```sh
"$MINERU_PYTHON" "$SKILL/scripts/mineru_source.py" \
  --project "$PROJECT/CourseProject.json" --output "$PROJECT/parser-import-001" \
  --run-local --mineru-home "$MINERU_HOME" --model-manifest "$MODEL_MANIFEST"
```

把该次 SourcePackage.import.json 的明确路径和哈希交给编写步骤，连同全部原页图像使用，保留输入/输出证据。它是提取旁件，不是第二份正式稿，也不改写 CourseProject；原相对路径由 source_base 明确定位。仅在出现具体缺陷的块回看原图/裁片，OCR 不能当网表或科学结论。参见 [可选解析器接口及限制](skills/circuit-teaching-video/references/external-parser.md)。

## 已实现与边界

- 原始 PDF、完整选页、图像/文字、完整稿件和画面引用保持关联；结构检查不代替实际内容比较。
- 真实句起点与完整 PCM 时长生成独占显示窗，保留原始提供方区间；不是逐词、音素或精确句末对齐。
- 画面、字体、公式和完整字幕按实际几何检查；不足时明确失败，不摘要化字幕或拉伸语音。
- 范围是可读 PDF、经检查的白底电路/数学/图表裁片、中文旁白和句级提示。不是所有扫描件、照片、任意拓扑、自动仿真或科学认证。
- 原始压缩栅格图的近白像素可能影响底衬效果，须看实际编码画面并局部调整提示。不能因声明 white_matte_safe 就假定一切栅格图都安全。
- 当前基础文字提取仍有复杂布局局限；更强解析器只能作为独立外部适配器，不能把 OCR 当网表。仓库提供可选外部 MinerU 适配脚本，但不包含或自动安装 MinerU 代码/模型。
- 任何新源素材、远程配音、交付与公开发布均须满足各自权限和第三方条款。仓库无课程 PDF、第三方教学图、音频、视频、字体、模型权重或账号信息。

## 本地回归与底层工具

```sh
python -m pip install -r requirements-p1.txt
python -B -m unittest discover -s skills/circuit-teaching-video/tests -v
python scripts/release_audit.py
```

测试中的音轨为明确标记的合成开发夹具，测试不会发起真实 TTS。较低层的 pipeline.py、原创分压例、可选来源/模型门和旧规划工具保留兼容，但不构成默认五节点的强制步骤。可选详情：[适配器](skills/circuit-teaching-video/references/adapters.md)、[旧合成工作流](skills/circuit-teaching-video/references/executable-workflow.md)、[可选模型门](skills/circuit-teaching-video/references/prefreeze-integration.md)。

## 许可证

本仓库自己的代码、文档和原创示例采用 [MIT](LICENSE)。依赖、字体、服务、模型及第三方讲义仍受各自条款约束。PyMuPDF 的 AGPL/商业许可、FFmpeg 的配置差异和 Edge 的服务条款不被 MIT 覆盖；不作整体 MIT 兼容或再分发合法性的承诺。见 [第三方说明](THIRD_PARTY_NOTICES.md)、[来源范围](PROVENANCE.md) 与 [安全说明](SECURITY.md)。
