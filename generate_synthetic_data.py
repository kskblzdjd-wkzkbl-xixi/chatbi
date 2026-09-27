# -*- coding: utf-8 -*-
"""
generate_synthetic_data.py — 财务检索项目开源版数据生成器（脱敏）
背景：项目数据库来自真实集团财务台账（用友客户泰达有线，实习保密红线）。
     GitHub 公开前必须脱敏：保留三表 schema 与业务形态，虚构公司与金额。
     README 将注明："合成数据，schema 与真实企业台账一致"。

脱敏策略（预设锚点，保住评估/面试数字）：
  - contract_tb：100 条收款合同；其中服务类恰 34 条（锚点：数量 34），
    服务类税额合计恰 = 2402.49（锚点），含印花税率 0.1% = 0.0010 的合同（锚点）。
  - payment_tb：7 条付款合同（金额本就是造数，保留；只虚构公司/项目/人名）。
    锚点：滨海应急指挥平台 200 万/已付 80 万/未付 120 万；临港停车已付 60万+65万=125 万。
  - fin_report_tb：78 条通用会计科目 + 随机金额（单位万元）。
    锚点：营业总收入本年累计 1564、资产总额 289978、应交所得税 32。
  - 全脚本固定随机种子，可复现；生成后内置断言校验锚点，不达标直接报错。

运行：python generate_synthetic_data.py -> synthetic/contract.csv 等三份 CSV
下游：load_data.py 从 synthetic/*.csv 灌库（真实 Excel 不再参与）
"""
import csv
import os
import random
from decimal import Decimal

# ↓ 输出目录：以脚本所在目录为基准（避免依赖运行目录，开源后可任意位置运行）
BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, 'synthetic')
SEED = 20260928                      # 固定种子：保证任何机器上生成结果一致
RATE_POOL = [('0.0010', 4), ('0.0005', 1), ('0.0003', 1)]  # (印花税率, 出现权重)，0.1% 为主
# ↓ 锚点常量（评估集 eval_set.py / 演示 demo.py 里的期望答案，脱敏后保持不变）
ANCHOR_SVC_TAX = Decimal('2402.49')  # 服务类 34 条税额合计
ANCHOR_FIN = {'营业总收入': Decimal('1564'),      # 本年累计(ytd_amount)，单位万元
              '资产总额':   Decimal('289978'),
              '应交所得税': Decimal('32')}

# ↓ 素材池：全部虚构，无真实公司/项目/人名
REGIONS = ['滨海', '自贸', '临港', '空港', '北辰', '东疆', '武清', '宝坻', '宁河', '静海']
SVC_WORDS = ['视频监控运维', '光纤网络铺设', '智慧停车系统', '宽带接入服务', '机房巡检',
             '数据专线', '园区网络运维', '安防监控升级', '信息系统集成', '呼叫中心服务']
BUILD_WORDS = ['管网改造工程', '楼宇装修工程', '土建施工工程', '道路翻新工程',
               '机房建设工程', '管线铺设工程', '电力增容工程']
OTHER_WORDS = ['设备采购', '办公家具租赁', '软件购销', '承揽加工', '融资租赁', '短期借款']
C_TYPES = ['服务', '施工', '租赁', '购销', '承揽', '融资', '借款']


def rnd_amount(r: random.Random, lo: int, hi: int) -> Decimal:
    # ↓ 随机金额：返回 Decimal，四舍五入到分
    return Decimal(r.randint(lo, hi) + r.randint(0, 99) / 100).quantize(Decimal('0.01'))


def make_contract_name(r: random.Random, ctype: str) -> str:
    # ↓ 按合同类型拼虚构名称（区域词 + 业务词）
    reg = r.choice(REGIONS)
    if ctype == '服务':
        return f'{reg}{r.choice(SVC_WORDS)}服务合同'
    if ctype == '施工':
        return f'{reg}{r.choice(BUILD_WORDS)}合同'
    return f'{reg}{r.choice(OTHER_WORDS)}合同'


def pick_rate(r: random.Random) -> Decimal:
    # ↓ 按权重取印花税率（0.1% 为主，锚点"印花税率0.1%的收款合同"依赖此分布）
    pool = []
    for rate, w in RATE_POOL:
        pool += [rate] * w
    return Decimal(r.choice(pool))


def build_contract_rows(r: random.Random) -> list:
    # ↓ 100 条收款合同：34 服务类（税额合计=2402.49）+ 66 随机类型
    rows = []
    no = 1
    # ---- 服务类 33 条随机 + 第 34 条校准补差 ----
    tax_sum = Decimal('0')
    for i in range(33):
        amount = rnd_amount(r, 50000, 800000)
        rate = pick_rate(r)
        tax = (amount * rate).quantize(Decimal('0.01'))   # 勾稽：税额 = 金额 × 税率
        tax_sum += tax
        rows.append(['TSNC-2026-SK-%03d' % no, make_contract_name(r, '服务'),
                     str(amount), str(amount), '服务', str(rate), str(tax), '收款合同', '2026Q2'])
        no += 1
    # ↓ 第 34 条服务类：固定税率 0.0010，税额 = 锚点 - 已累计（补差法，保证合计精确）
    rate34 = Decimal('0.0010')
    tax34 = (ANCHOR_SVC_TAX - tax_sum).quantize(Decimal('0.01'))
    amount34 = (tax34 / rate34).quantize(Decimal('0.01'))
    rows.append(['TSNC-2026-SK-%03d' % no, make_contract_name(r, '服务'),
                 str(amount34), str(amount34), '服务', str(rate34), str(tax34), '收款合同', '2026Q2'])
    no += 1
    # ---- 其余 66 条：类型随机（排除"服务"，保证服务类数量锚点恰为 34）----
    for i in range(66):
        ctype = r.choice([t for t in C_TYPES if t != '服务'])
        amount = rnd_amount(r, 30000, 2000000)
        rate = pick_rate(r)
        tax = (amount * rate).quantize(Decimal('0.01'))
        rows.append(['TSNC-2026-SK-%03d' % no, make_contract_name(r, ctype),
                     str(amount), str(amount), ctype, str(rate), str(tax), '收款合同', '2026Q2'])
        no += 1
    return rows


def build_payment_rows() -> list:
    # ↓ 7 条付款合同：金额保留原造数（非真实企业数据），只虚构公司/项目/人名
    #   列顺序与 load_data INSERT / CSV 表头一致（18 列）
    return [
        ['天晟有线电视网络有限公司', 'P001', '滨海智慧园区视频监控项目', 'TSNC-2026-FK-YWFW-001',
         '视频监控运维服务合同', '天晟城发集团', '津安防科技公司', '服务类', '运维服务',
         '2026-01-15', '工程管理部', '李强', '2026-01-15', 520000, 490566, 29434, 260000, 260000],
        ['天晟有线电视网络有限公司', 'P001', '滨海智慧园区视频监控项目', 'TSNC-2026-FK-SG-002',
         '园区光纤铺设工程', '天晟城发集团', '津通信工程公司', '施工类', '工程施工',
         '2026-02-01', '工程管理部', '王芳', '2026-02-01', 880000, 830000, 50000, 440000, 440000],
        ['天晟有线电视网络有限公司', 'P002', '临港智慧停车项目', 'TSNC-2026-FK-YWFW-003',
         '智慧停车系统开发', '临港国资公司', '京智泊科技公司', '服务类', '系统开发',
         '2026-03-10', '技术研发部', '张明', '2026-03-10', 1200000, 1132075, 67925, 600000, 600000],
        ['天晟有线电视网络有限公司', 'P002', '临港智慧停车项目', 'TSNC-2026-FK-YWFW-004',
         '停车设备采购', '临港国资公司', '津停车设备厂', '采购类', '设备采购',
         '2026-04-20', '采购部', '赵丽', '2026-04-20', 650000, 613208, 36792, 650000, 0],
        # ↓ 锚点合同：滨海应急指挥平台 合同额 200万(最高) / 已付 80万 / 未付 120万
        ['天晟有线电视网络有限公司', 'P003', '滨海应急指挥平台', 'TSNC-2026-FK-SG-005',
         '应急指挥中心改造', '滨海新区管委会', '津建筑集团', '施工类', '工程施工',
         '2026-05-05', '工程管理部', '钱进', '2026-05-05', 2000000, 1886792, 113208, 800000, 1200000],
        ['天晟有线电视网络有限公司', 'P004', '社区宽带接入项目', 'TSNC-2026-FK-YWFW-006',
         '小区宽带接入服务', '天晟物业服务公司', '津电信服务公司', '服务类', '网络服务',
         '2026-06-12', '运营部', '孙浩', '2026-06-12', 360000, 339623, 20377, 180000, 180000],
        ['天晟有线电视网络有限公司', 'P004', '社区宽带接入项目', 'TSNC-2026-FK-YWFW-007',
         '智慧物业管理系统', '天晟物业服务公司', '深智慧物业软件公司', '软件类', '软件采购',
         '2026-07-01', '技术研发部', '周涛', '2026-07-01', 450000, 405405, 44595, 0, 450000],
    ]


def build_fin_report_rows(r: random.Random) -> list:
    # ↓ 78 条财务月报科目：通用会计科目名（公共知识，无敏感），金额随机；3 个锚点固定
    items = ['货币资金', '交易性金融资产', '应收票据', '应收账款', '预付账款', '其他应收款', '存货',
             '一年内到期的非流动资产', '流动资产合计', '长期股权投资', '固定资产', '在建工程', '无形资产',
             '长期待摊费用', '递延所得税资产', '非流动资产合计', '资产总额', '短期借款', '应付票据',
             '应付账款', '预收账款', '应付职工薪酬', '应交税费', '应交增值税', '应交所得税', '其他应付款',
             '一年内到期的非流动负债', '流动负债合计', '长期借款', '应付债券', '长期应付款',
             '非流动负债合计', '负债总额', '实收资本', '资本公积', '盈余公积', '未分配利润',
             '所有者权益合计', '营业总收入', '主营业务收入', '其他业务收入', '营业成本', '主营业务成本',
             '其他业务成本', '税金及附加', '销售费用', '管理费用', '财务费用', '资产减值损失',
             '信用减值损失', '投资收益', '营业利润', '营业外收入', '营业外支出', '利润总额', '所得税费用',
             '净利润', '基本每股收益', '经营活动现金流量净额', '投资活动现金流量净额',
             '筹资活动现金流量净额', '现金及现金等价物净增加额', '期初现金及现金等价物余额',
             '期末现金及现金等价物余额', '国有资产保值增值率', '资产负债率', '流动比率', '速动比率',
             '存货周转率', '应收账款周转率', '总资产周转率', '销售利润率', '成本费用利润率',
             '带息负债总额', '有息负债率', '带息负债占比', '利息保障倍数', '现金比率']
    rows = []
    for i, item in enumerate(items, 1):
        # ↓ 锚点科目：本年累计 = 锚点值（单位万元）；存量指标本月数常为空（与真实口径一致）
        if item in ANCHOR_FIN:
            ytd = ANCHOR_FIN[item]
            month = None
        else:
            ytd = rnd_amount(r, 1, 400000)          # 随机本年累计（万元）
            month = rnd_amount(r, 1, 40000) if r.random() < 0.3 else None
        prev = rnd_amount(r, 1, 300000) if r.random() < 0.7 else None
        rows.append(['天津企业财务月报', item, i,
                     str(month) if month is not None else '',
                     str(ytd), str(prev) if prev is not None else '', '202608'])
    return rows


def write_csv(name: str, header: list, rows: list):
    # ↓ 写 synthetic/*.csv（utf-8；空值统一存 ''，由 load_data 转 None）
    os.makedirs(OUT_DIR, exist_ok=True)
    path = f'{OUT_DIR}/{name}'
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f'  [write] {path}  {len(rows)} 条')


def verify_anchors(c_rows, p_rows, f_rows):
    # ↓ 生成后自检：锚点全中，不达标直接抛错（保护评估集/面试数字）
    svc = [r for r in c_rows if r[4] == '服务']
    assert len(svc) == 34, f'服务类数量锚点失效: {len(svc)} != 34'
    tax_sum = sum(Decimal(r[6]) for r in svc)        # 第 6 列 = tax_amount
    assert tax_sum == ANCHOR_SVC_TAX, f'服务类税额合计锚点失效: {tax_sum} != {ANCHOR_SVC_TAX}'
    assert len(c_rows) == 100, f'合同总数锚点失效: {len(c_rows)} != 100'
    assert any(Decimal(r[5]) == Decimal('0.0010') for r in c_rows), '印花税率 0.1% 锚点失效'
    # ↓ payment 锚点：滨海应急指挥平台 最高额/已付/未付；临港停车已付合计 125 万
    binhai = [r for r in p_rows if r[2] == '滨海应急指挥平台']
    assert len(binhai) == 1 and binhai[0][13] == 2000000 and binhai[0][16] == 800000 \
        and binhai[0][17] == 1200000, 'payment 滨海锚点失效'
    lingang = [r for r in p_rows if r[2] == '临港智慧停车项目']
    assert sum(r[16] for r in lingang) == 1250000, f'临港已付锚点失效: {sum(r[16] for r in lingang)}'
    # ↓ fin_report 锚点：三个科目 ytd 值
    for item, val in ANCHOR_FIN.items():
        hit = [r for r in f_rows if r[1] == item]
        assert hit and Decimal(hit[0][4]) == val, f'报表锚点失效: {item}'  # 第 4 列 = ytd_amount
    print('  [ok] 锚点自检全部通过（34/2402.49/100/0.0010/2000000/800000/1200000/1250000/1564/289978/32）')


def main():
    r = random.Random(SEED)                          # 固定种子：全链路可复现
    c_rows = build_contract_rows(r)
    p_rows = build_payment_rows()
    f_rows = build_fin_report_rows(r)
    verify_anchors(c_rows, p_rows, f_rows)           # 先自检再落盘
    write_csv('contract.csv',
              ['contract_no', 'contract_name', 'contract_amount', 'net_amount',
               'contract_type', 'tax_rate', 'tax_amount', 'remark', 'source_month'],
              c_rows)
    write_csv('payment.csv',
              ['company', 'project_code', 'project_name', 'contract_no', 'contract_name',
               'party_a', 'party_b', 'cat1', 'cat2', 'sign_date', 'dept', 'handler',
               'start_date', 'contract_amount', 'net_amount', 'tax_amount',
               'paid_amount', 'unpaid_amount'],
              p_rows)
    write_csv('fin_report.csv',
              ['report_type', 'item', 'row_no', 'month_amount', 'ytd_amount',
               'prev_ytd_amount', 'report_month'],
              f_rows)
    print('[done] 合成数据已生成（synthetic/*.csv），可交由 load_data.py 灌库')


if __name__ == '__main__':
    main()
