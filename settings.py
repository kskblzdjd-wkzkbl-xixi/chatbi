# -*- coding: utf-8 -*-
# settings.py — 读取脚本同目录 .env（可选），提供 DB / Ollama 全局配置
# .env 不存在时用内置默认值（本地开发零配置即可跑）；GitHub 只提交 .env.example，密钥类配置不入库
import os

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

# ↓ DB 连接参数：供 graph.py / load_data.py 共用；字段名与 pymysql.connect 入参一致
DB = dict(host=os.getenv('DB_HOST', '127.0.0.1'),
          port=int(os.getenv('DB_PORT', '3306')),
          user=os.getenv('DB_USER', 'root'),
          password=os.getenv('DB_PASSWORD', ''),
          charset='utf8mb4',
          database=os.getenv('DB_NAME', 'finance_chatbi'))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')   # Ollama 服务地址
LLM_MODEL = os.getenv('LLM_MODEL', 'qwen3:4b')                    # 对话/生成用模型
EMBED_MODEL = os.getenv('EMBED_MODEL', 'bge-m3')                  # 向量模型
