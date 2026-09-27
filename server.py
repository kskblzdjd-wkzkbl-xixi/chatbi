# -*- coding: utf-8 -*-
# CHATBI 演示层后端：FastAPI 复用 graph.py 的 LangGraph 应用
# 运行：python server.py → 浏览器打开 http://127.0.0.1:8000
# 前置：MySQL 在跑、Ollama 在跑（bge-m3 + qwen3:4b）
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from graph import build_graph   # ← 同目录导入项目主图（graph.py 顶部会加载 FAISS 索引）

# ↓ 模块级只 build 一次：MemorySaver 存进程内存，thread_id 区分会话实现多轮记忆
app_graph = build_graph()

app = FastAPI(title='CHATBI 财务智能检索演示')

class ChatRequest(BaseModel):
    question: str
    session_id: str = 'demo'   # 前端生成；同 session 连续提问走同一记忆

@app.post('/api/chat')
def chat(req: ChatRequest):
    q = (req.question or '').strip()
    if not q:
        raise HTTPException(status_code=400, detail='问题不能为空')
    try:
        out = app_graph.invoke(
            {'question': q},
            {'configurable': {'thread_id': req.session_id}},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'服务异常：{e}')
    # 只回前端需要的字段；answer 可能含多行表格，原样返回
    return {
        'answer': out.get('answer', ''),
        'source': out.get('source', ''),
        'intent': out.get('intent', ''),
        'sql': out.get('sql') or '',
    }

# ↓ 静态页面托管：index.html 与 /api/chat 同源，无跨域问题
BASE = Path(__file__).resolve().parent
app.mount('/', StaticFiles(directory=BASE / 'static', html=True), name='static')

if __name__ == '__main__':
    import uvicorn
    print('CHATBI 前端已启动：http://127.0.0.1:8000')
    uvicorn.run(app, host='127.0.0.1', port=8000)
