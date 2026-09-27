import sys
sys.stdout.reconfigure(encoding='utf-8')
from graph import check_sql_whitelist, validate_sql 
cases = [
    # (说明, SQL, 期望通过白名单?)
    ('基本查询', "SELECT COUNT(*) FROM contract_tb WHERE source_month='2026Q2'", True),
    ('聚合+分组+排序+DESC回归', "SELECT contract_type, SUM(tax_amount) FROM contract_tb GROUP BY contract_type ORDER BY tax_amount DESC LIMIT 3", True),
    ('字符串字面量不当列名', "SELECT * FROM contract_tb WHERE contract_type='服务'", True),
    ('反引号包裹', 'SELECT `tax_amount` FROM `contract_tb`', True),
    ('表前缀只校验列名', 'SELECT contract_tb.tax_amount FROM contract_tb', True),
    ('幻觉列必须拦', 'SELECT revenue FROM contract_tb', False),
    ('幻觉表必须拦', "SELECT * FROM contracts WHERE type='服务'", False),
    ('别名也要拦(策略:prompt不教模型用别名)', 'SELECT c.tax_amount FROM contract_tb c', False),
]
ok = 0
for name, sql ,except_ok in cases:
    got = check_sql_whitelist(sql)
    passed = (got == 'ok') == except_ok
    ok += passed
    print(('PASS' if passed else 'FAIL'), name, '->' ,got[:70])
r1 = validate_sql({'sql': 'UPDATE contract_tb SET tax_amount=0'})
print('PASS' if '非 SELECT' in r1['validation'] else 'FAIL', '非SELECT拦截 ->', r1['validation'][:50])
r2 = validate_sql({'sql': 'SELECT * FROM contract_tb; DROP TABLE contract_tb'})
print('PASS' if '危险关键字' in r2['validation'] else 'FAIL', '危险词拦截 ->', r2['validation'][:50])
print(f'白名单单测: {ok}/8')