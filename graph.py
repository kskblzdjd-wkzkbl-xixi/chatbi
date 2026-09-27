import sys
sys.stdout.reconfigure(encoding='utf-8')

import re
import pymysql
from typing import TypedDict, Annotated, Literal
from operator import add

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from langchain_ollama import OllamaEmbeddings

from langchain_community.vectorstores import FAISS
from settings import DB, OLLAMA_URL as OLLAMA, LLM_MODEL as MODEL, EMBED_MODEL  # ← 配置统一从 settings 读取（.env 可覆盖）
SQL_BLOCK_KEYWORDS = ('insert','update','delete','drop','alter','truncate',
                      'create','grant','revoke','set','call')
SAFE_TABLES = {'contract_tb','payment_tb','fin_report_tb'}
SAFE_COLUMNS = {
    'contract_no','contract_name','contract_amount','net_amount',
    'contract_type', 'tax_rate', 'tax_amount', 'remark', 'source_month',
    # payment_tb（物业付款台账，18 列）
    'company', 'project_code', 'project_name', 'contract_no', 'contract_name',
    'party_a', 'party_b', 'cat1', 'cat2', 'sign_date', 'dept', 'handler',
    'start_date', 'contract_amount', 'net_amount', 'tax_amount',
    'paid_amount', 'unpaid_amount',
    # fin_report_tb（财务月报指标，7 列）
    'report_type', 'item', 'row_no', 'month_amount', 'ytd_amount',
    'prev_ytd_amount', 'report_month',
}
SQL_KEYWORDS = {
    'select','from','where','group','by','order','limit','having','as', 'and', 'or', 'not', 'in', 'between', 'like', 'is', 'null',
    'distinct', 'on', 'join', 'left', 'right', 'inner', 'full', 'outer',
    'asc', 'desc',
    'sum', 'count', 'avg', 'min', 'max', 'if', 'nullif', 'coalesce',
    'existing', 'matches',
}
def check_sql_whitelist(sql: str) -> str:
    if not sql:
        return '空 SQL'
    stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", sql)
    stripped = re.sub(r'`([a-zA-Z_][a-zA-Z0-9_]*)`', r'\1', stripped)
    ident_toks = re.findall(r'(?:[a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)',
                            stripped.lower())
    allowed = SQL_KEYWORDS | SAFE_COLUMNS | SAFE_TABLES
    unknown = {t for t in ident_toks if t not in allowed}
    if unknown:
        return '列名/标识符未在白名单内: ' + ', '.join(sorted(unknown))[:150]
    return 'ok'
class FinanceState(TypedDict):
    question: str
    intent: str
    answer: str
    sql: str
    validation: str
    retry_count: int
    source: str
    history: Annotated[list,add]
llm = ChatOllama(model=MODEL,base_url=OLLAMA,temperature=0.1)
class Intent(TypedDict):
    intent: Literal['sql','rag','chat']
    confidence:float
intent_llm =llm.with_structured_output(Intent)
sql_examples = [
    {"q":"二季度服务类收款合同有多少个？",
     "a":"SELECT COUNT(*) FROM contract_tb WHERE source_month='2026Q2' AND contract_type='服务' "},
     {"q":"二季度服务类收款合同税额合计",
      "a":"SELECT SUM(tax_amount) FROM contract_tb WHERE source_month='2026Q2' AND contract_type='服务'"
      },
      {"q": "滨海应急指挥平台项目累计付了多少款？",
     "a": "SELECT SUM(paid_amount) FROM payment_tb WHERE project_name='滨海应急指挥平台'"},
    {"q": "8月营业总收入本年累计是多少？",
     "a": "SELECT ytd_amount FROM fin_report_tb WHERE item LIKE '%营业总收入%' AND report_month='202608'"},
    {"q": "上月资产负债表现金及现金等价物是多少？",
     "a": "SELECT month_amount FROM fin_report_tb WHERE item LIKE '%现金%' AND report_month='202608'"},
    {"q": "2026年8月资产总额是多少？",
     "a": "SELECT ytd_amount FROM fin_report_tb WHERE item LIKE '%资产总额%' AND report_month='202608'"},
    {"q": "2026年8月应交所得税是多少？",
     "a": "SELECT ytd_amount FROM fin_report_tb WHERE item LIKE '%应交所得税%' AND report_month='202608'"},
    {"q": "二季度一共签了多少份收款合同？",
     "a": "SELECT COUNT(*) FROM contract_tb WHERE source_month='2026Q2'"},
    {"q": "付款合同里合同金额最高的前三名是什么？",
     "a": "SELECT contract_name, contract_amount FROM payment_tb ORDER BY contract_amount DESC LIMIT 3"},
    {"q": "印花税率0.1%的收款合同有哪些？",
     "a": "SELECT contract_name, tax_rate FROM contract_tb WHERE tax_rate=0.0010"},
]
example_prompt = ChatPromptTemplate.from_messages([
    ('human', '问：{q}'),
    ('ai',   '答：{a}'),
])
few_shot = FewShotChatMessagePromptTemplate(
    examples=sql_examples,          # 示例是数据：加示例不改模板
    example_prompt=example_prompt,
)
NL2SQL_SYS = """你只输出一条可直接执行的 MySQL SELECT 语句,禁止输出任何解释、注释、markdown 代码块或额外文字。
表名必须一字不差使用：
contract_tb(收款合同台账): 列[contract_no, contract_name, contract_amount, net_amount, contract_type, tax_rate, tax_amount, remark, source_month]
  - 该表所有记录同属一家公司(天晟)，问题里出现"天晟/天晟有线/有线"时【不要】做任何公司过滤
  - contract_type 取值: 服务/施工/租赁/购销/承揽/融资/借款
  - 季度过滤: source_month='2026Q2'
  - tax_rate 为印花税率小数(如0.1%=0.0010, 0.03%=0.0003)：问税率就用 tax_rate=0.0010 这种小数形式
  - 表内【没有】contract_type='收款'：问"一共多少份收款合同"指全表，用 SELECT COUNT(*) FROM contract_tb，不要加 type 过滤
payment_tb(付款合同台账): 列[company, project_name, contract_no, contract_name, party_a, party_b, cat1, cat2, sign_date, dept, contract_amount, net_amount, tax_amount, paid_amount, unpaid_amount]
  - 该表全表就是"物业板块"的付款合同，问题里出现"物业板块"时【不要】做任何板块过滤
  - 项目过滤: project_name, 需按公司: company
fin_report_tb(财务报表指标): 列[item, row_no, month_amount, ytd_amount, prev_ytd_amount, report_month]
  - 月份过滤: report_month='202608'; 本月数=month_amount, 本年累计=ytd_amount, 上年同期=prev_ytd_amount
  - 存量/期间指标(资产总额/负债/所得税/税费等)数值多在 ytd_amount,month_amount 常为空：取这类指标优先用 ytd_amount
规则：
1. 仅 SELECT;禁止 INSERT/UPDATE/DELETE/DROP/ALTER/分号
2. 表名和列名必须与上方【完全一致】，不允许改名或臆造列；列名只有上方列出这些
3. 问题提到"天晟/天晟有线/有线"这类公司名时，在 contract_tb 中忽略公司过滤(contract_tb 全表就是天晟的)
4. 问资产总额/负债/税费/所得税等存量指标时，取 ytd_amount(month_amount 常为空)
5. 问"最高/最大/前N名"排名类问题：用 ORDER BY <金额列> DESC LIMIT N,【禁止】加其它 WHERE 过滤条件"""
gen_sql_prompt = ChatPromptTemplate.from_messages([
    ('system', NL2SQL_SYS),
    few_shot,                                            # few-shot 块整体注入
    ('human', '{history_block}\n问题:{question}\n{retry_note}答：'),
])
gen_sql_chain = gen_sql_prompt | llm | StrOutputParser()
rag_prompt = ChatPromptTemplate.from_messages([
    ('system', """你是一位企业财务制度专家。基于以下真实业务口径回答问题，回答需专业、分条：
【参考语料】
{context}"""),
    ('human', '{history_block}问题：{question}\n'),
])
rag_chain = rag_prompt | llm | StrOutputParser()
embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA)
try:
    store = FAISS.load_local('rag_index', embeddings,
                             allow_dangerous_deserialization=True)
    VECTOR_OK = True
except Exception:
    store = None
    VECTOR_OK = False
chat_chain = (
    ChatPromptTemplate.from_template('你是财务智能助手，简短友好回答。\n{history_block}问题：{question}')
    | llm
    | StrOutputParser()
    )

_FIN_KEYWORDS_SQL = ['金额','税额','合同','已付','未付','税率','税','项目','合计','多少','累计','收入','成本','资产','负债','本月','本年','报表','汇总']
_FIN_KEYWORDS_RAG = ['签证','结算','确认','规则','流程','办法','制度','口径','区别','为什么','如何','要求','审批','依据','规范','发票']
def _rule_fallback_intent(q: str) -> str:
    rag_hit = sum(1 for kw in _FIN_KEYWORDS_RAG if kw in q
                  )
    sql_hit = sum(1 for kw in _FIN_KEYWORDS_SQL if kw in q
                  )
    if rag_hit > sql_hit:
        return 'rag'
    if sql_hit > 0:
        return 'sql'
    return 'chat'
def _classify_intent(q: str) -> str:
    try:
        o = intent_llm.invoke(
            f"你是财务问答系统的意图分类器，判断用户问题走哪条路：\n"
            f"- sql  : 查具体数据/金额/汇总/查询类（如合同金额、税额、已付款、三表数字）\n"
            f"- rag  : 问制度/规则/流程/口径类（如签证确认、结算规则、报表口径）\n"
            f"- chat : 闲聊/打招呼/与财务无关\n"
            f"问题：{q}")
        intent = o.get('intent','') if isinstance(o,dict) else getattr(o,'intent','')
        conf = float(o.get('confidence',0) if isinstance(o,dict) else getattr(o,'confidence',0))
        if intent in ('rag','sql','chat'):
            if conf < 0.7:
                return _rule_fallback_intent(q)
            return intent
    except Exception: 
        pass
    return _rule_fallback_intent(q)
def classify(state:FinanceState)-> dict:
    q = state['question']
    intent = _classify_intent(q)
    return {'intent': intent,'history':[{'q':q,'intent':intent}]}
def route_intent(state: FinanceState) -> str:
    return state['intent']
def _history_block(state:FinanceState,n: int =2) -> str:
    h=state.get('history') or []
    if not h:
        return ''
    lines = [f"用户: {it.get('q','')}" for it in h[-n:]]
    return '对话历史（上几轮用户问题）：\n' + '\n'.join(lines) + '\n'
_RAG_RULES = [
    ('签证', '对甲签证采用三方确认（甲方 / 乙方 / 监理方）共同确认工程量，避免签证金额争议。'),
    ('过程结算', '过程结算按已完成工程量阶段性计量付款；最终结算待工程全部完工验收合格后进行。'),
    ('结算', '收款合同按客户回款结算；付款合同按合同进度付款，先票后付 / 先款后付以协议约定为准。'),
    ('税金', '合同税金 = 不含税价款 × 适用税率（增值税）。'),
    ('发票', '发票管理须合规，业务应与票据一致，先票后付以防范税务风险。'),
]
def rag_fallback(q: str) -> str:
    for kw,txt in _RAG_RULES:
        if kw  in q:
            return txt
    return '制度知识库暂不可用，请稍后重试或换种问法。'
def clamp(o,limit=4000):
    s= str(o)
    return s if len(s) <= limit else s[:limit] + '…[输出过长已截断]'
def rag_answer(state:FinanceState) -> dict:
    q = state['question']
    ans = ''
    src = 'RAG制度口径'
    # 层① FAISS 向量检索(主力): 只有索引加载成功且能召回才走
    if VECTOR_OK and store is not None:
        try:
            docs = store.similarity_search_with_score(q, k=3)  # top-3 召回
            context = '\n'.join(d.page_content for d, _ in docs)
            if context.strip():   # 召回非空才拼进 prompt
                ans = rag_chain.invoke({'history_block': _history_block(state),
                                        'question': q, 'context': context})
                src = 'RAG向量检索'
        except Exception:
            ans = ''   # embedding/索引异常 → 落层②
    # 层②关键词兜底(原方案降级): 层①空/异常时接
    if not ans.strip():
        ans = rag_fallback(q)
    return {'answer': clamp(ans), 'source': src}
def gen_sql(state:FinanceState) -> dict:
    q = state['question']
    prev_err = state.get('validation')
    retry_note = ''
    if prev_err and prev_err not in ('ok','') and state.get('retry_count',0) > 0:
        retry_note = f'上次校验失败，错误：{prev_err}。重新输出正确的 SQL。\n'
    try:
        sql = gen_sql_chain.invoke({
            'history_block': _history_block(state),
            'question':q,
            'retry_note': retry_note,
        }).strip()
        sql = re.sub(r'<think>.*?</think>','',sql,flags=re.S)
        if '```' in sql:
            sql = sql.split('```')[1] if sql.count('```') >= 2 else sql.replace('```','')
        sql = ''.join(line for line in sql.splitlines()  if not line.strip().startswith('--'))
        sql = sql.strip().rstrip(';')
        low = sql.lower()
        if 'select' in low:
            sql = sql[low.index('select'):]
    except Exception as e:
        return {'sql':'','validation': f'LLM异常: {e}',
                'retry_count':state.get('retry_count',0) + 1}
    return {'sql': sql,'validation':'ok',
            'retry_count': state.get('retry_count',0) + 1}
def validate_sql(state:FinanceState) -> dict:
    sql = state.get('sql','')
    low = sql.lower().strip()
    if not low.startswith('select'):
        return {'validation': f'非 SELECT 语句，仅允许只读查询: {sql[:60]}'}
    for b in SQL_BLOCK_KEYWORDS:
        if b in low:
            return {'validation': f'包含危险关键字 {b!r}'}
    wl = check_sql_whitelist(sql)
    if wl != 'ok':
        return {'validation': wl}  
    try:
        if 'limit' not in low:
            sql += ' LIMIT 50'
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        cur.execute(sql)
        cur.fetchall()
        cur.close(); conn.close()
        return {'validation': 'ok'}
    except Exception as e:
        return {'validation': f'SQL执行失败: {str(e)[:120]}'}
def route_validate(state: FinanceState) -> str:
    if state.get('validation') == 'ok':
        return 'ok'
    if state.get('retry_count',0) >= 3:
        return 'fail'
    return 'retry'
def run_sql(state:FinanceState) -> dict:
    sql = state.get('sql','')
    if 'limit' not in sql.lower():
        sql += ' LIMIT 50'
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close();conn.close()
    if not rows:
        return {'answer':'未查询到满足条件的记录。若问题带金额/条件过滤，可能查询条件过严，可放宽或换种问法。',
                'source':'SQL查询0行'}
    sep = '|'.join(cols)
    lines = [sep]
    for r in rows[:20]:
        lines.append('|'.join(str(x) if x is not None else '' for x in r))
    ans = '\n'.join(lines)
    return {'answer': clamp(ans, 6000), 'source': f'SQL查询 {len(rows)} 行'}

def sql_fail(state: FinanceState) -> dict:
    return {'answer': f'无法生成有效查询，请换种问法。最近错误：{state.get("validation", "")}',
            'source': 'SQL-FAIL'}

def chat_reply(state:FinanceState) -> dict:
    q = state['question']
    try:
        ans = chat_chain.invoke({'history_block': _history_block(state),'question': q})
    except Exception:
        ans = '你好！我是财务智能助手，可帮你查询合同/收付款/财务三表数据或了解制度口径。'
    return{'answer': clamp(ans),'source':'闲聊'}
def build_graph():
    g = StateGraph(FinanceState)
    g.add_node('classify',classify)
    g.add_node('rag',rag_answer)
    g.add_node('gen_sql',gen_sql)
    g.add_node('validate',validate_sql)
    g.add_node('run_sql',run_sql)
    g.add_node('fail',sql_fail)
    g.add_node('chat',chat_reply)
    g.add_edge(START,'classify')
    g.add_conditional_edges('classify',route_intent,{'rag':'rag','sql':'gen_sql','chat':'chat'})
    g.add_edge('rag',END)
    g.add_edge('chat',END)
    g.add_edge('gen_sql','validate')
    g.add_conditional_edges('validate',route_validate,{'ok':'run_sql','retry':'gen_sql','fail':'fail'})
    g.add_edge('run_sql',END)
    g.add_edge('fail',END)
    return g.compile(checkpointer=MemorySaver())
if __name__ == '__main__':
    app = build_graph()
    app.get_graph().print_ascii()
    print('=' * 50)
    demos = ['天晟2026年二季度有哪些服务类收款合同？税额合计多少？',
        '2026年8月资产负债表营业总收入本年累计是多少？',
        '对甲签证为什么要三方确认？',
        '你好',
        '上月提醒我财务数据有误',]
    for q in demos:
        print(f'\n>>> question: {q}')
        cfg ={'configurable': {'thread_id': 'demo-1'}}
        out = app.invoke({'question': q},config= cfg)
        print(f'[意图] {out["intent"]}')
        print(f'[来源] {out["source"]}')
        print(f'[答案] {str(out["answer"])[:400]} ')