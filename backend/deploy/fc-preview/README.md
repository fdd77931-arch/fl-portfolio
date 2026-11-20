# 阿里云函数计算验收环境

`health-ai-preview` 是位于华北 2（北京）的签名访问验收函数。它运行正式 FastAPI 应用和同一份种子资料，通过阿里云 `InvokeFunction` 的 `POST /invoke` 事件入口检查进程、知识库统计、急症判断和前端静态文件。

## 构建与调用

从仓库根目录执行。

```sh
sh backend/deploy/fc-preview/build.sh /tmp/health-ai-fc-preview.zip
```

配置 FC3 自定义运行时 `custom.debian11`。启动命令为 `/bin/sh`，参数是 `/code/bootstrap.sh`，监听 9000。该运行时自带 Python 3.12，构建脚本随 ZIP 打包 Linux x86_64 依赖。

上传 ZIP 后，用具有 `fc:InvokeFunction` 权限的调用方发送以下事件。

```json
{"check":"health-ai"}
```

预览依靠签名调用，没有公网触发器。它从包中读取证据，临时 SQLite 位于 `/tmp`，验收包和预览函数不需要配置模型密钥或开放网络。

## 北京百炼联调

已用下列北京公共兼容端点验证 `qwen-plus`、`text-embedding-v4` 和 `qwen3-rerank`。

```dotenv
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-api/v1
```

正式部署继续使用生产服务的安全环境变量，持久化知识库与向量索引，并通过自定义 HTTPS 域名或 API 网关提供访问。先验收公开 API 的模型调用、CORS 和引用，随后更新 GitHub Pages 的 API origin。阿里云默认 `fcapp.run` 域名用于测试环境。

- [自定义运行时和内置 Python 版本](https://help.aliyun.com/zh/functioncompute/custom-runtime/)
- [函数计算 InvokeFunction](https://help.aliyun.com/zh/functioncompute/api-fc-2023-03-30-invokefunction)
- [函数计算默认域名的使用范围](https://help.aliyun.com/zh/functioncompute/the-default-public-network-domain-name-of-function-compute-is-not-allowed-in-the-production-environment)

## 验收记录

2026 年 11 月 20 日对北京函数 `health-ai-preview` 进行签名调用。FastAPI 响应成功，知识库返回 19 份文档及 21 个已核验证据片段，急症判断直接返回提醒，演示静态入口可读取。

在独立本地 API 进程中，使用北京百炼建立 21 条真实向量并进行 12 道抽测。8 道证据题返回预期来源，2 道急症题提前拦截，2 道无证据题返回资料不足。首次抽测的阿司匹林题因生成了证据未支持的内容而被拒。扩充药品摘要及约束生成提示后，该题返回预期的 MedlinePlus 来源。本次抽测检查调用链与引用命中，临床专家评估需独立进行。
