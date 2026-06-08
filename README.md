# 作文评分系统 (Essay Grader)

像真实老师一样给高中英文作文打分 + 逐句批注 + 给改进建议。老师布置作业、复核反馈；学生提交作文、即时拿到评分和批注。

## 它怎么"像真老师"

评分引擎 = **大模型 + 真实专业资源**（当前接 DeepSeek，经本地 OpenAI 兼容反代）：

- **评分量表**：直接用 [ELLIPSE 语料](https://github.com/scrosseye/ELLIPSE-Corpus) 的官方 rubric（受训人类评分员使用），1–5 分、6 个分项：Cohesion / Syntax / Vocabulary / Phraseology / Grammar / Conventions + Overall。
- **分数校准**：从 ELLIPSE 语料里抽出已由真人评分的样本作为锚点（`app/data/calibration.json`），让 AI 的尺度对齐真实评分。
- **批注风格**：强制结构化输出——每条批注引用作文原文、标注类型（论点/证据/语法/词汇…）、给具体可执行的修改建议，并区分"做得好"和"要改"。

> 调研来源：ELLIPSE、[PERSUADE](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9767095/)（2.5 万篇议论文 + 24 位写作老师批注）、[ASAP/ASAP++](https://www.kaggle.com/datasets/lburleigh/asap-2-0)。当前默认用 ELLIPSE rubric；可扩展接入 PERSUADE 的论证元素标注。

## AP 评分模式（专打 AP English Language，最严谨）

ELLIPSE 量表评的是**语言能力**（流畅/语法/词汇），所以一篇润色过的文常拿满分却没看论证。**AP 模式**改用官方 College Board **6 分制分析量表**评 AP English Language 三种 FRQ（Synthesis / Rhetorical Analysis / Argument），评的是**论证质量**：

- **量表分解**：Row A 论点(0–1) + Row B 证据&评析(0–4) + Row C sophistication(0–1)，分行打分再求和；Row B 第 4 分的"语法门控"硬规则在代码里强制执行。量表原文见 `data/ap/scoring_guidelines_2024_set1_raw.txt`。
- **样卷锚定**：用官方打过分的真实样卷做 few-shot 锚点（`data/ap/samples.json`，2024 set-1）。
- **不微调**：公开拿不到成规模 AP 标注数据，所以是"量表接地 + 样卷锚定 + 自洽多趟"的 LLM 评委（2025 年低数据 AES 的 SOTA 路线），**不假装训练**。

**诚实的准确度（实测，非编造）**：在 26 篇无泄漏官方留出样卷（2023 全部 + 2024 set-2）上，总分 **QWK ≈ 0.6（相邻±1 一致率 ~85%）**，落在文献天花板区间，即"逼近第二位人类阅卷员"。复现：`./.venv/bin/python -m app.ap.eval --holdout --passes 3`。

**已知局限（写在明处）**：① Row C（sophistication）是当前模型(GLM-4.6)的能力天花板——它几乎从不给这一分，专用判官也救不回，要再提升得换更强评委模型；② passes=1 单趟噪声大，认真取数用 `--passes 3`。

用法见下方「Chrome 扩展」AP 模式，或直接调 `POST /api/ap_grade`。

## 技术栈

FastAPI + Jinja2 + Tailwind(CDN) + SQLite(SQLModel) + OpenAI Python SDK（指向任意 OpenAI 兼容端点，当前为 DeepSeek 反代），纯 Python 后端。

评分引擎与 provider 解耦，只读三个环境变量，换模型/换厂商不动代码：`GRADER_BASE_URL`、`GRADER_API_KEY`、`GRADER_MODEL`。

## 快速开始

```bash
cd essay-grader
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 配置：复制 .env.example -> .env，填入端点与 key
cp .env.example .env
#   GRADER_BASE_URL / GRADER_API_KEY / GRADER_MODEL（默认 DeepSeek 本地反代）

# (可选) 重新生成校准锚点
./.venv/bin/python scripts/build_calibration.py

# (可选) 灌入演示账号：teacher/demo1234 与 student/demo1234
./.venv/bin/python scripts/seed_demo.py

# 先单独验证评分引擎（确认端点可用，会打印一份完整批改）
./.venv/bin/python scripts/try_grade.py

# 启动 Web 应用（端口须为 8011，浏览器插件默认连这个端口）
./.venv/bin/uvicorn app.main:app --reload --port 8011
# 打开 http://localhost:8011
```

## 流程

- **老师**：注册（选"老师"）→ 新建作业（题目/文体/年级）→ 在作业页看学生提交、分数、点开复核，可补充人工批注。
- **学生**：注册（选"学生"）→ 选作业或自由练习 → 粘贴作文 → 提交 → 即时看到分项分数、Google-Docs 风格右边距批注、改进优先级。

站内结果页是 **Google Docs 风格**：作文在左，批注卡片浮在右边距、与对应句子水平对齐，悬停画虚线连接，点击联动。

## 免费分发模型：Bring Your Own Backend（BYO）

设计原则：**对终端用户免费，作者零成本零责任**。代价透明 —— 用户自己在本机跑这个后端、用自己的模型访问（本地开源模型或自己的 API key）。没有共享 key、没有中心服务器、没有流量经过作者。

非技术用户上手：

```
1. 双击 start.command（macOS）→ 自动建环境、装依赖、起服务、打开配置页
2. 在 http://127.0.0.1:8011/setup 选来源并填自己的 key/模型：
   - 本地 Ollama / LM Studio（完全免费离线）
   - 智谱 GLM / DeepSeek 官方（自带 key，各有免费额度）
   - 自定义任意 OpenAI 兼容端点
3. 点“测试连接”确认可用 → 开始评分
```

> 为什么不做“装插件=把你机器变共享中转池”那种？那是 ToS 违规 + 应用商店下架红线 + 把法律/安全责任甩给用户。BYO 是唯一既免费又干净的路子。

### 别人怎么下载用（你的 key 不会被带走）

每个用户用**自己的** key，跑在**自己**机器上 —— 作者/你的 key 全程只在你本机 `.env` 里：

```
1. git clone <repo>             # .env 已 gitignore，不会带出任何人的 key
2. 双击 start.command           # 建环境、装依赖、起服务、开 /setup
3. 在 /setup 填自己的来源/key   # 本地 Ollama 免费，或自带 GLM/DeepSeek key
4. chrome://extensions → 开发者模式 → 加载已解压 → 选 extension/
```

### 防滥用闸（保护你自己的 key 不被跑干）

后端只绑 `127.0.0.1`（外网打不进来），再叠三道 env 可调的闸 —— 卡死的循环 / 手滑狂点 / 超长文本都**在调用模型前**被拦掉（返回 429）：

| 变量 | 默认 | 作用 |
|------|------|------|
| `GRADER_DAILY_LIMIT` | 200/天 | 每日评分上限，跑不爆 |
| `GRADER_RATE_PER_MIN` | 12/分 | 防瞬时刷爆 |
| `GRADER_MAX_CHARS` | 15000 | 防超长文本烧 token |

任一设为 `0` 关闭。实现见 `app/core/limiter.py`，挂在 `/api/grade` 和 `/api/ap_grade` 前。`start.command` 首次生成的 `.env` 自带这三行；缺省也走内置默认值。

## Chrome 扩展（Google Docs 常驻批注 + 任意网页）

`extension/`（v0.3.0）是一个 Manifest V3 扩展。每个面板顶部有**模式开关**：
- **AP score（官方量表）** + 题型下拉（Rhetorical Analysis / Argument / Synthesis）→ 出 Row A/B/C 拆分评分（走 `/api/ap_grade`）
- **Quick language check** → ELLIPSE 语言评分 + 内联批注（走 `/api/grade`）

两种用法：

**A. Google Docs 常驻（主用法）** —— 打开任意 Google 文档时，右下角常驻一个 **📝 Grade** 按钮：
```
点 📝 Grade → 面板弹出 → 选模式(AP/语言)+题型 → “Scan this document & grade” → 抓取全文 → 出分
```
> 原理：Google Docs 是 canvas 渲染、DOM 抓不到正文，所以用它的导出接口
> `docs.google.com/document/d/<id>/export?format=txt`（带用户登录 cookie），由扩展**后台**抓取
> 并调本地评分后端 —— 绕开 Google Docs 的 CSP。

**B. 任意网页** —— 选中文字 → 右键“用作文评分助手批改选中文字” → 侧边栏出结果。

安装与配置：
```
1. 先启动本地后端：双击 start.command（或 uvicorn app.main:app --port 8011）
2. chrome://extensions → 开“开发者模式” → “加载已解压的扩展程序” → 选 essay-grader/extension
3. 右键扩展图标 → 选项：API 地址填 http://127.0.0.1:8011，token 见 .env 的 GRADER_API_TOKEN（留空则不用填）
4. 打开任意 Google 文档，点右下角 📝 评分 → 扫描
```

后端 API（供扩展/第三方调用）：

```
POST /api/grade      Header: X-API-Key: <GRADER_API_TOKEN>（留空则免鉴权）
  body: {"text": "...", "prompt": "可选", "grade_level": "可选", "essay_type": "argumentative essay"}
  返回: {scores, summary, strengths, priorities, annotations:[{quote,type,comment,suggestion,start,end,located}], text}

POST /api/ap_grade   Header: X-API-Key: <GRADER_API_TOKEN>   # 官方 AP 6 分制
  body: {"text": "...", "frq_type": "rhetorical_analysis|argument|synthesis",
         "prompt": "可选", "source_material": "可选", "passes": 1}
  返回: {total, max_total:6, rows:{A_thesis,B_evidence_commentary,C_sophistication}, overall_comment, top_fixes, meta}

GET  /api/health     → {ok, model, configured}
```
> 两个评分端点都过防滥用闸（429 = 超速/超日额/超长）。

## 项目结构

```
app/
  main.py            FastAPI 路由 + 认证 + /api/grade + /api/ap_grade (CORS + 限流)
  db.py              SQLModel 模型 (User/Assignment/Submission/Evaluation)
  core/
    rubric.py        ELLIPSE rubric（结构化）
    grader.py        语言评分引擎（OpenAI 兼容；JSON 模板 + 防御性解析）
    limiter.py       防滥用闸（每日/每分钟/长度上限）
    render.py        批注 → 高亮 HTML
  ap/                ★ AP 官方量表评分
    rubric.py        AP 6 分制量表（3 题 Row A/B/C 官方原文）
    scorer.py        量表分解 + 自洽多趟 + 语法门控（含 dedicated_c 备用开关）
    anchors.py       官方样卷 few-shot 锚定（2024 set-1，无泄漏）
    eval.py          QWK / 完全 / 相邻一致率 评测台
  data/calibration.json   ELLIPSE 评分校准锚点
  templates/  static/     站内 Google-Docs 风格结果页
extension/           Chrome MV3 扩展 v0.3.0（AP 模式 + 语言模式；Docs 常驻 + 侧边栏）
  manifest.json background.js content.* sidepanel.* options.* icons/
scripts/
  build_calibration.py   从 ELLIPSE 语料抽校准样本
  ap_grade.py            命令行跑 AP 评分
  build_ap_samples.py    下载官方样卷 PDF → fitz 栅格化 → 视觉转写 → 引文校验
  seed_demo.py  try_grade.py
data/ap/             AP 量表原文 + samples.json（样卷 PDF 与转写缓存 gitignore）
data/raw/            ELLIPSE 原始语料 (gitignore)
```

## 注意事项 / 生产化 TODO

- 现用 Tailwind Play CDN（开发便利，无 SRI）；上线请改用构建版 Tailwind。
- `.env`、`*.db`、`*.png`、`extension/_*`、官方样卷 PDF 已被 gitignore，勿提交 key/数据库（插件图标 `extension/icons/*.png` 有例外、会随仓库发布）。
- 当前默认评分模型 **智谱 GLM-4.6**（在 `/setup` 配置）；引擎与 provider 解耦，可随时换本地 Ollama / DeepSeek 官方 / 任意 OpenAI 兼容端点。思考型模型会输出 `<think>`/`reasoning_content`（解析器已处理）。
- 厂商通常对**突发请求限流/封 key**。SDK 已关自动重试（`max_retries=0`），别短时间连发；AP 评测多趟跑请用 `--passes` 而非并发。被限时 API/页面有友好提示。防滥用闸（见上）也帮你避免把自己 key 跑爆。
- 环境变量：`GRADER_BASE_URL` / `GRADER_API_KEY` / `GRADER_MODEL` / `GRADER_MAX_TOKENS` / `GRADER_API_TOKEN`（扩展鉴权，留空免鉴权）/ `GRADER_VISION_MODEL`（样卷转写，默认 `glm-4.5v`）/ 防滥用 `GRADER_DAILY_LIMIT` `GRADER_RATE_PER_MIN` `GRADER_MAX_CHARS`。
- 可扩展：接入 PERSUADE 论证元素标注、支持中文作文 rubric、教师批量导出。
