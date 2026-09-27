# -*- coding: utf-8 -*-
# Step3 评估集：20 条真实 rag/sql/chat 问答 → 跑整条 LangGraph 链路
# 统计：意图分类准确率 + 各路任务命中（SQL 走通并命中数值锚点 / RAG 命中要点）
import sys
sys.stdout.reconfigure(encoding='utf-8')
from graph import build_graph   # ← 同目录导入；评估就是反复造图+invoke

QAS = [
    # ---- SQL 路：10 条（前 4 条有已确认的真实数值锚点）----
    ('天晟2026年二季度服务类收款合同有多少个？',            'sql', 'SQL查询', ['34']),
    ('天晟2026年二季度服务类收款合同税额合计多少？',        'sql', 'SQL查询', ['2402.49']),
    ('滨海应急指挥平台项目累计付了多少款？',                'sql', 'SQL查询', ['800000']),
    ('2026年8月营业总收入本年累计是多少？',                   'sql', 'SQL查询', ['1564']),
    ('2026年8月资产总额是多少？',                             'sql', 'SQL查询', ['289978']),
    ('2026年二季度一共签了多少份收款合同？',                  'sql', 'SQL查询', ['100']),
    ('临港智慧停车项目目前付了多少钱？',                      'sql', 'SQL查询', ['1250000']),
    ('2026年8月应交所得税是多少？',                           'sql', 'SQL查询', ['32']),
    ('物业板块付款合同里单一合同金额最高的前三名是哪些？',    'sql', 'SQL查询', ['2000000']),
    ('印花税率0.1%的收款合同有哪些？',                        'sql', 'SQL查询', ['0.0010']),
    # ---- RAG 路：7 条（来源前缀 = M3 向量化后的实际来源「RAG向量检索」，M2 时代为「RAG制度口径」）----
    ('对甲签证为什么要三方确认？',  'rag', 'RAG向量检索', ['三方', '监理', '签证']),
    ('过程结算和最终结算有什么区别？',      'rag', 'RAG向量检索', ['过程结算', '最终结算']),
    ('收款合同和付款合同的结算规则是什么？', 'rag', 'RAG向量检索', ['收', '付']),
    ('合同税金是怎么计算的？',              'rag', 'RAG向量检索', ['税率', '不含税']),
    ('为什么付款要先票后付？',              'rag', 'RAG向量检索', ['票', '付']),
    ('签证结算的流程规范是什么？',          'rag', 'RAG向量检索', ['签证', '确认']),
    ('发票管理有什么规范要求？',            'rag', 'RAG向量检索', ['发票', '规范']),
    # ---- CHAT 路：3 条 ----
    ('你好',        'chat', '闲聊', []),
    ('你是谁？',    'chat', '闲聊', []),
    ('今天有什么财务问题可以问你', 'chat', '闲聊', []),
]
# ↑ QAS = Question-And-Answer-Set：每行是 (问题, 期望意图, 期望来源前缀, 期望答案锚点列表)
#   "锚点" = 期望答案里必须出现的词/数字（SQL 路验证数值对不对，不止看有没有结果）

def run():
    app = build_graph()
    lines = [f'=== Step3 评估集（{len(QAS)} 条）===\n']
    stat = {'intent_ok': 0, 'task_ok': 0, 'sql_road': 0, 'sql_ok': 0,
            'rag_road': 0, 'rag_ok': 0, 'chat_road': 0, 'chat_ok': 0}
    for i, (q, exp_intent, exp_src, anchors) in enumerate(QAS, 1):
        exp_road = 'sql' if exp_intent == 'sql' else exp_intent
        out = app.invoke({'question': q}, {'configurable': {'thread_id': f'ev{i}'}})
        intent = out['intent']; src = out['source']; ans = str(out['answer'])

        intent_ok = (intent == exp_intent)
        road_ok = (src.startswith(exp_src)) or (exp_road == 'chat' and src == '闲聊')
        if exp_road == 'sql':
            nonempty = src != 'SQL查询 0 行'
            anchor_ok = nonempty and (not anchors or any(a in ans for a in anchors))
        else:
            anchor_ok = road_ok and (not anchors or any(a in ans for a in anchors))

        stat['intent_ok'] += int(intent_ok)
        if exp_road == 'sql':
            stat['sql_road'] += 1; stat['sql_ok'] += int(anchor_ok)
        elif exp_road == 'rag':
            stat['rag_road'] += 1; stat['rag_ok'] += int(anchor_ok)
        else:
            stat['chat_road'] += 1; stat['chat_ok'] += int(src == '闲聊')

        flag = 'OK ' if (intent_ok and anchor_ok) else 'XX '
        lines.append(f'\n{flag}[{i:>2}] 期望意图={exp_intent}({exp_src}) 实得意图={intent} [来源] {src}')
        lines.append(f'       Q: {q}')
        lines.append(f'       A: {ans[:160]}')
        if anchors:
            lines.append(f'       锚点: {anchors} -> {"命中" if anchor_ok else "未命中"}')

    n = len(QAS)
    lines.append('\n' + '=' * 46)
    lines.append(f'意图分类准确率 : {stat["intent_ok"]:.0f}/{n} = {stat["intent_ok"]/n*100:.1f}%')
    if stat['sql_road']:
        lines.append(f'SQL 路任务命中 : {stat["sql_ok"]}/{stat["sql_road"]} = {stat["sql_ok"]/stat["sql_road"]*100:.1f}%')
    if stat['rag_road']:
        lines.append(f'RAG 路任务命中 : {stat["rag_ok"]}/{stat["rag_road"]} = {stat["rag_ok"]/stat["rag_road"]*100:.1f}%')
    if stat['chat_road']:
        lines.append(f'CHAT 路任务命中: {stat["chat_ok"]}/{stat["chat_road"]} = {stat["chat_ok"]/stat["chat_road"]*100:.1f}%')
    total_ok = stat['sql_ok'] + stat['rag_ok'] + stat['chat_ok']
    total_road = stat['sql_road'] + stat['rag_road'] + stat['chat_road']
    if total_road:
        lines.append(f'全路任务综合命中: {total_ok}/{total_road} = {total_ok/total_road*100:.1f}%')

    with open(r'C:\Users\26647\Desktop\CHATBI\eval_report.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'  done: intent={stat["intent_ok"]}/{n}  sql={stat["sql_ok"]}/{stat["sql_road"]} '
          f'rag={stat["rag_ok"]}/{stat["rag_road"]}  chat={stat["chat_ok"]}/{stat["chat_road"]}')

if __name__ == '__main__':
    run()