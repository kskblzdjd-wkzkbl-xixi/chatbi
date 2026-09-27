# -*- coding: utf-8 -*-
# eval_rag_v2.py —— 同题双版对比评估（升级价值量化证据）
# Run A 关键词版 vs Run B 向量版, 12 题, 输出双列 Report
from graph import rag_answer, rag_fallback, _RAG_RULES

# ↓ 12 题: (问题, 判断命中词列表)
CASES = [
    # ---- 原 7 条(回归红线, 两版都应过) ----
    ('对甲签证为什么要三方确认？', ['三方', '监理', '签证']),
    ('过程结算和最终结算有什么区别？', ['过程结算', '最终结算']),
    ('收款合同和付款合同的结算规则是什么？', ['收', '付']),
    ('合同税金是怎么计算的？', ['税率', '不含税']),
    ('为什么付款要先票后付？', ['票', '付']),
    ('签证结算的流程规范是什么？', ['签证', '确认']),
    ('发票管理有什么规范要求？', ['发票', '规范']),
    # ---- 刁钻 5 条(进阶价值试金石) ----
    ('合同变更了钱怎么算？', ['变更', '签证']),            # 刁钻1
    ('甲方拖着不确认工程量怎么办？', ['三方', '确认']),     # 刁钻2
    ('哪些付款必须领导签字才能走？', ['签证', '审批']),     # 刁钻3
    ('怎么防止对方虚开发票？', ['发票', '规范']),          # 刁钻4
    ('为什么总价对不上不含税的数？', ['税率', '不含税']),   # 刁钻5
]

def hit(ans: str, kws: list) -> bool:
    return all(k in ans for k in kws)

lines = []
stat = {'A7':0,'A刁':0,'B7':0,'B刁':0}
for i,(q,kws) in enumerate(CASES):
    a = 'Y' if hit(rag_fallback(q), kws) else 'N'   # Run A: 关键词版
    b = 'Y' if hit(rag_answer({'question':q})['answer'], kws) else 'N'  # Run B: 向量版
    is_tricky = i >= 7
    if a=='Y' and not is_tricky: stat['A7']+=1
    if a=='Y' and is_tricky:     stat['A刁']+=1
    if b=='Y' and not is_tricky: stat['B7']+=1
    if b=='Y' and is_tricky:     stat['B刁']+=1
    lines.append(f"{'刁钻' if is_tricky else '原题'} | {q[:14]:<14} | 关键词A:{a} | 向量B:{b}")
    print(f"{q} -> A:{a} B:{b}")

summary = (
    "\n===== 评估汇总 =====\n"
    f"原7题:   关键词版 {stat['A7']}/7   向量版 {stat['B7']}/7\n"
    f"刁钻5题: 关键词版 {stat['A刁']}/5   向量版 {stat['B刁']}/5\n"
    f"综合:    关键词版 {stat['A7']+stat['A刁']}/12 → 向量版 {stat['B7']+stat['B刁']}/12\n"
)
with open('eval_report_rag_compare.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n' + summary)
print("written -> eval_report_rag_compare.txt\n" + summary)