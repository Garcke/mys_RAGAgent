# 米游社收藏夹 AI 知识库（MYS_RagAgent）

一个基于 **FastAPI + ChromaDB + DashScope(Qwen)** 的米游社收藏夹知识库应用：

- 扫码登录米游社账号
- 拉取收藏夹帖子
- 增量归档到本地向量库
- 基于归档内容进行知识库问答
- 支持按游戏分区选择入库（当前分区 / 全部分区）

---

## 功能概览

- **扫码登录**：通过米游社二维码登录并提取 `stuid/stoken/mid`
- **收藏夹浏览**：按游戏分区查看收藏帖子
- **增量入库**：归档收藏帖到 RAG 知识库，自动去重
- **入库范围选择**：点击归档前弹窗选择
  - 当前分区
  - 全部分区
- **分区入库状态提示**：在游戏分区标签显示 `入库中...` / `已入库`
- **RAG 问答**：基于归档内容回答问题并返回参考来源
- **寒暄优化**：如“你好”这类寒暄不会附带参考来源

---

## 项目结构

```text
MYS_RagAgent/
├─ main.py                 # FastAPI 入口与 API 路由
├─ requirements.txt        # Python 依赖
├─ static/                 # 前端页面与样式脚本
│  ├─ index.html
│  ├─ style.css
│  ├─ app.js
│  └─ marked.min.js
├─ rag/                    # RAG 核心模块
│  ├─ agents.py            # 归档流程
│  ├─ chroma.py            # ChromaDB 读写
│  ├─ retrieval.py         # 检索与回答生成
│  └─ db.py
├─ mys_api/                # 原始 API 脚本参考
└─ data/chroma/            # 本地向量库数据目录
```

---

## 环境要求

- Python 3.10+
- Windows / macOS / Linux

---

## 快速开始

### 1) 克隆项目

```bash
git clone <your-repo-url>
cd MYS_RagAgent
```

### 2) 创建虚拟环境并安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 3) 配置环境变量

在项目根目录创建 `.env`：

```env
DASHSCOPE_API_KEY=你的阿里云百炼API_KEY
```

### 4) 启动服务

```bash
python main.py
```

启动后访问：

- 首页：`http://127.0.0.1:8000/`
- API 文档：`http://127.0.0.1:8000/docs`

---

## 主要 API

- `POST /api/login/qrcode/generate` 生成扫码二维码
- `POST /api/login/qrcode/status` 查询扫码状态
- `POST /api/roles/list` 获取角色列表
- `POST /api/favourite/get` 获取收藏夹
- `POST /api/rag/ingest/favourites` 归档收藏帖（支持 `selected_game_id`）
- `GET  /api/rag/stats` 知识库统计
- `POST /api/rag/query` 知识库问答
- `DELETE /api/rag/reset` 清空知识库

---

## 入库策略说明

- 归档采用**增量式**，不会覆盖历史数据
- 点击“归档收藏帖”会弹窗确认入库范围
- 当选择“当前分区”时，会携带 `selected_game_id` 仅归档该分区帖子
- UI 会在分区标签显示入库状态（`入库中...` / `已入库`）

---

## 常见问题

### 1. 输入“你好”为什么会出现参考来源？
已修复：寒暄类问题会直接返回问候，不附带来源。

### 2. ChromaDB 数据存在哪里？
默认在 `data/chroma/`。

### 3. API Key 未配置会怎样？
问答相关能力会不可用，请先配置 `DASHSCOPE_API_KEY`。

---

## License

仅用于学习与内部开发使用，请遵守米游社及相关接口的使用规范。