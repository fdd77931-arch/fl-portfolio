# Health AI · 智能健康助手

## 现有架构核查

作品集 GitHub Pages 从 `main` 的根目录发布。公开演示位于 `demos/xunji/`，使用原生 HTML、CSS、JavaScript，无构建步骤。原网页调用独立的 Cloudflare Worker 的 `/api/status` 和 `/api/ask`。前端曾将服务的配置状态作为连接状态，接收过无证据的模型补充结果。线上 Worker 在本次环境中连接超时，未能读取其内部配置和持久化资源。

原网页的 10 类危险信号、急救教程、科普示例和目录搜索由浏览器运行。原始目录 `knowledge.json` 有 1,867 条，含部分摘要和大量目录记录。旧 Python 原型在独立的 healthcare-agent 仓库，提供规则分诊与会话流程。本轮部署使用独立 FastAPI 后端。公开代码及可读的历史材料未定位到可复用的向量索引，前端调用点未出现模型 API Key。

## 实现

1. 原作品集和演示路径继续使用。网页从 `config.js` 获取公开 API origin。默认同源，独立服务同时托管演示页面。
2. 浏览器和后端均优先检查急症信号。后端先检查明显的诊疗请求和个人标识，再将符合条件的提问提交给百炼。问答文本不落盘，应用日志记录接口、状态、耗时和上游错误类别。
3. 混合检索使用中英文 BM25 与百炼 Embedding。两个候选序列通过倒数排名融合，交给百炼 Rerank。库规模较小时使用 SQLite 和精确余弦相似度。索引签名包含百炼 Base URL、模型名和文档内容。调整模型或资料后须重建。
4. 证据片段与文档使用独立 ID。服务端校验模型引用，按文档聚合来源，并保留每段对应的片段、章节和位置。有主题词支持时采用可配置的重排序门槛。只有语义命中时要求向量相似度和重排序得分同时达到更高门槛。结构性校验后，另一次 Qwen 调用逐段检查医学主张是否受到所引证据支持。未通过核验时返回证据不足。
5. 文档库有六个逻辑集合、十二个医学领域。种子集位于 `demos/xunji/evidence.json`。历史静态目录仍可浏览，未核验条目在页面单独标记。新导入的待审核资料保留在后端，公开来源接口只列已核验及已被替代的条目。只有状态为 `verified` 的片段参与问答。被新指南替代的版本可通过同一 ID 更新为 `superseded`，其目录记录仍可查询。
6. 文档来源、出版信息、版本、章节、核验时间和许可随片段保存。无官方年份的动态资料保留在线版本和核验日期。受限资料保留链接及自撰摘要。开放原文的归档说明见 `data/originals/README.md`。

## 本地运行

从仓库根目录运行。先将 `backend/.env.example` 复制为 `backend/.env`。将轮换后的密钥和控制台显示的地域端点填到该文件。

```sh
cd backend
uv venv --python 3.12
uv pip install -r requirements.txt
.venv/bin/python -m health_ai.index --smoke
.venv/bin/python -m uvicorn health_ai.main:app --host 127.0.0.1 --port 8080 --no-access-log
```

打开 [本地演示](http://127.0.0.1:8080/demos/xunji/)。未配置百炼时可以验证知识浏览和急症提示。生产配置中，`DASHSCOPE_BASE_URL` 应填聊天和 Embedding 的兼容接口根路径。若 Rerank 的兼容路径有区别，用 `DASHSCOPE_RERANK_BASE_URL` 另配。模型 ID 都能通过环境变量调整。打开页面时显示服务就绪状态，在实际问答成功后显示百炼问答可用。

- [百炼聊天接口](https://www.alibabacloud.com/help/en/model-studio/qwen-api-reference)
- [百炼 Embedding](https://www.alibabacloud.com/help/en/model-studio/embedding)
- [百炼文本重排序接口](https://help.aliyun.com/zh/model-studio/text-rerank-api)

## API 与资料导入

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | `{"question":"…"}`，返回带引用段落、急症、资料不足、诊疗边界或服务错误 |
| POST | `/api/retrieve` | 同一问题结构。评估用 `?trace=true` 读取排序 ID |
| POST | `/api/ingest` | 管理员 Bearer 令牌。提交 `sources` 和可选原始文档 |
| GET | `/api/sources` | 支持 `collection`、`domain`、`q`、`limit`、`offset` |
| GET | `/api/health` | 进程、模型配置、索引状态和最近的真实问答状态 |
| GET | `/api/knowledge/stats` | 文档数、片段数、分类、版本状态、已索引数量 |

导入由服务运营人员负责。先核查原文许可和版本，再用 `demos/xunji/evidence.json` 中相同的字段结构准备元数据。导入携带相应的 `HEALTH_AI_INGEST_TOKEN`。导入供检索的 `verified` 片段时实时生成向量。也可使用本地离线 PDF 解析和 OCR，安装 PyMuPDF，扫描版另装 Tesseract 及对应语言包。

```sh
cd backend
uv pip install pymupdf
.venv/bin/python -m health_ai.import_pdf /path/to/guide.pdf /path/to/metadata.json --ocr chi_sim+eng
```

## 发布

Dockerfile 以仓库根目录为构建上下文。部署到支持 HTTPS、环境密钥及持久卷的独立服务。单实例运行，挂载可写持久卷到 `/data`。平台应使用可信反向代理并覆盖客户端转发头。公开运行时，限流为每客户端每分钟 12 次付费请求、单进程合计 50 次，另有常规请求限额。多实例部署需要共享限流以及共享向量数据库。应用不记录健康问题，托管方的访问日志也应关闭请求体记录。

```sh
docker build -f backend/Dockerfile -t health-ai .
```

在生产服务的密钥管理处设置 `DASHSCOPE_API_KEY`、两个地域端点和可选导入令牌。用与 API 相同的镜像、环境变量和挂载卷，先执行一次 `python -m health_ai.index --smoke`。这个检查也可在发布后单独运行。问答索引未就绪时，容器仍提供来源目录和急症判断。先访问后端 HTTPS 下的演示并提交测试问题，确认 `/api/health` 的 `connected` 和原文链接。随后把 API origin 填到 `demos/xunji/config.js`，检查 GitHub Pages origin 的 CORS，再发布前端。

## 评估

```sh
cd backend
uv pip install pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m health_ai.evaluate --links --report /tmp/health-ai-offline.json
.venv/bin/python -m health_ai.evaluate --base-url http://127.0.0.1:8080 --report /tmp/health-ai-live.json
```

115 道合成问题覆盖检索、急症、无证据拒答和个人诊疗边界。离线模式评估 BM25、本地规则以及无证据题是否误命中主题词。实时模式记录关键词、向量、融合、重排序位置及引用完整度。引用校验确认 ID 对应本次检索证据。模型核验可能出错，临床正确性及每项主张是否准确反映来源需要人工逐条核阅。来源 HTTP 可访问率受网络、机构访问限制和镜像影响。
