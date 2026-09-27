# -*- coding: utf-8 -*-
# 回归探针: 向量版 rag_answer 是否仍答对 7 条原题, 且能接住新问法
from graph import rag_answer, VECTOR_OK
CASES = [
    ('对甲签证为什么要三方确认？', ['三方', '监理', '签证']),
    ('过程结算和最终结算有什么区别？', ['过程结算', '最终结算']),
    ('收款合同和付款合同的结算规则是什么？', ['收', '付']),
    ('合同税金是怎么计算的？', ['税率', '不含税']),
    ('为什么付款要先票后付？', ['票', '付']),
    ('签证结算的流程规范是什么？', ['签证', '确认']),
    ('发票管理有什么规范要求？', ['发票', '规范']),
    ('合同变更了钱怎么算？', ['变更', '签证']),        # 刁钻1
    ('甲方拖着不确认工程量怎么办？', ['三方', '确认']),  # 刁钻2
    ('为什么总价对不上不含税的数？', ['税率', '不含税']), # 刁钻3
]
print('VECTOR_OK =', VECTOR_OK)
for q, kws in CASES:
    r = rag_answer({'question': q})
    hit = all(k in r['answer'] for k in kws)
    print(f"[{'Y' if hit else 'N'}] {r['source']} | {q} -> {'命中' if hit else '缺:'+str([k for k in kws if k not in r['answer']])}")