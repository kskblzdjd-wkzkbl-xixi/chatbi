# CHATBI — 财务数据智能检索系统

> 一个基于 **LangGraph 状态机 + RAG 向量检索 + NL2SQL 安全护栏** 的企业财务数据问答系统：让财务人员用自然语言查合同台账、付款进度和财务报表指标。
> 合成数据，schema 与真实企业台账一致；公司与金额均已虚构（见 [数据说明](#数据说明)）。

## 特性

- **Agentic 工作流**：意图路由、SQL 生成、SQL 反思修复三个关键环节交由 LLM 自主决策，LangGraph 状态机约束执行路径 —— 用确定性拓扑限定不可控性
- **NL2SQL 三层安全护栏**：黑名单危险词过滤 → 白名单列名/表名正则校验（防幻觉臆造列）→ 强制 LIMIT 执行验证；失败将报错反馈 LLM 反思重试 ≤ 3 次
- **RAG 向量检索**：bge-m3（1024 维）Embedding + FAISS（top-3 召回），三层降级：向量检索 → 关键词兜底 → 静态话术
- **多轮对话记忆**：LangGraph Checkpointer（MemorySaver）+ `history` Reducer，支持"上一笔/那施工类呢"式指代消解
- **意图三层兜底分类**：LLM 结构化输出（Literal 枚举）→ 置信度 < 0.7 规则层 → 异常规则兜底
- **诚实拒答**：查无结果返回"未查询到满足条件的记录"，不伪装答案
- **量化评估**：20 条 Golden Set 评估集 + 12 题 RAG 双版本对比（关键词版 vs 向量版）

## 架构

```
                用户提问
                   │
                   ▼
            ┌───────────┐
            │  classify │  LLM 意图分类（三层兜底：结构化输出→置信度→规则）
            └─────┬─────┘
     ┌────────────┼─────────────┐
   sql            │             rag/chat
     ▼            │             │
┌──────────────┐  │             │
│ gen_sql(LLM) │  │             │
└──────┬───────┘  │             │
       ▼          │             │
┌──────────────┐  │   ┌────────────┐
│ validate 三层 │  │   │  rag_answer │
│ 护栏校验      │  │   │  FAISS top-3│
└─┬─────────┬──┘  │   │  → LLM 分条 │
fail│      ok│     │   └────────────┘
   ▼       │      │   chat → chat_node（闲聊）
┌──────┐   ▼      │
│ fail │ run_sql  │   retry（≤3 次：把校验报错回填 prompt 反思重写）
└──────┘   │      │
          └── END ┘
```

状态机 `State`（八字段）：`question / intent / sql / validation / retry_count / answer / source / history(Reducer 累加)`。
三层职责边界：**LangGraph 管控制流、LangChain 管能力层、裸 Python 管规则层**。

## 快速开始（约 10 分钟）

### 0. 前置环境

- Python 3.11+，MySQL 8+（本机 `127.0.0.1:3306`）
- [Ollama](https://ollama.com) 运行中，已拉取两个模型：
  ```bash
  ollama pull qwen3:4b      # 对话 / SQL 生成模型
  ollama pull bge-m3        # 向量模型
  ```

### 1. 安装依赖

```bash
git clone <repo-url> chatbi
cd chatbi
pip install -r requirements.txt
```

### 2. 灌数据（建库 + 写入 100 合同 / 7 付款 / 78 报表指标）

```bash
python load_data.py
```

> 数据来自 `synthetic/*.csv`（预置合成数据，可直接灌库）。如需重新生成：`python generate_synthetic_data.py`（固定随机种子，可复现）。

### 3. 构建向量索引（约 1 分钟，首次需加载 bge-m3）

```bash
python build_index.py
```

> 仓库已附带 `rag_index/`，可跳过本步直接运行；语料变更后需重建。

### 4. 启动浏览器演示

```bash
python server.py
```

浏览器打开 **http://127.0.0.1:8000**，试着问：

| 类型 | 提问 |
|---|---|
| SQL 路 | 天晟2026年二季度服务类收款合同税额合计多少？ |
| RAG 路 | 对甲签证为什么要三方确认？ |
| 多轮追问 | 先问"天晟二季度有多少份服务类收款合同"，再问"那施工类呢？" |

### 5.（可选）复现评估

```bash
python eval_set.py        # 20 条 Golden Set 评估 → eval_report.txt
python eval_rag_v2.py     # 12 题 RAG 双版本对比 → eval_report_rag_compare.txt
python probe_rag_v2.py    # 向量检索主路径探针（10 条全 Y = 未静默降级）
```

## 数据说明

- **合成数据声明**：本项目数据库由 `generate_synthetic_data.py` 生成，**保留真实企业台账的 schema 与业务形态**（三表结构、会计科目、合同类型枚举、季度/月度口径），**公司与金额全部虚构**，不包含任何真实企业数据。
- 数据规模：`contract_tb` 100 条收款合同（34 条服务类）｜ `payment_tb` 7 条付款合同（18 列）｜ `fin_report_tb` 78 条财务月报指标（单位：万元）。
- 预设锚点：服务类税额合计 `2402.49`、滨海应急指挥平台未付款 `1200000`、营业总收入本年累计 `1564` 等，供评估与演示对齐。

## 量化评估

### 20 条 Golden Set（五路全绿）

| 路径 | 意图分类 | 任务命中 |
|---|---|---|
| SQL（10 条） | 10/10 | 10/10 |
| RAG（7 条） | 7/7 | 7/7 |
| CHAT（3 条） | 3/3 | 3/3 |
| **综合** | **20/20** | **20/20** |

### RAG 双版本对比（同一 12 题评估集，关键词版 vs 向量版）

| 分组 | 关键词版（规则匹配） | 向量版（bge-m3 + FAISS） |
|---|---|---|
| 原 7 题（制度口径） | 5/7 | **7/7** |
| 刁钻 5 题（换问法） | 0/5 | **4/5** |
| **综合 12 题** | **5/12** | **11/12** |

> 结论：向量检索把"换问法"准确率从 41.7% 提升到 91.7%，且原 7 题 7/7 回归不退化。完整逐题记录见 [eval_report_rag_compare.txt](./eval_report_rag_compare.txt)。

## 项目结构

```
chatbi/
├── graph.py                  # LangGraph 状态机主图（classify/gen_sql/validate/rag_answer）
├── settings.py               # 配置统一入口（读 .env，零配置可跑）
├── load_data.py              # 建库 + 从 synthetic/*.csv 灌数
├── generate_synthetic_data.py# 合成数据生成器（固定 seed，预设评估锚点）
├── rag_corpus.py             # 22 段制度口径语料（含 source/topic 元数据）
├── build_index.py            # bge-m3 向量化 + FAISS 索引构建
├── eval_set.py               # 20 条 Golden Set 评估（intent/sql/rag/chat）
├── eval_rag_v2.py            # 12 题 RAG 双版本对比评估
├── probe_rag_v2.py           # 向量主路径探针（防静默降级）
├── demo.py                   # 三场景演示（数据/制度/多轮记忆）→ demo_out.txt
├── server.py                 # FastAPI 后端 + 静态前端托管
├── static/index.html         # 浏览器聊天界面（气泡/意图/来源/SQL 展示）
├── synthetic/                # 合成数据 CSV（contract/payment/fin_report）
├── rag_index/                # 预构建 FAISS 索引
├── requirements.txt / .env.example / LICENSE
└── _dev_tools/               # 开发期临时探针（不入 git 主仓库）
```

## License

MIT © 2026 李世舟
