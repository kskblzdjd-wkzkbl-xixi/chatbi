import sys
sys.stdout.reconfigure(encoding='utf-8')
import csv
import os
import pymysql

from settings import DB  # ← DB 连接配置统一从 settings 读取（.env 可覆盖）

# ↓ 开源版数据源：synthetic/*.csv（由 generate_synthetic_data.py 生成，schema 与真实台账一致、公司与金额已虚构）
#   以脚本所在目录为基准，避免依赖运行目录（开源后任意位置可运行）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'synthetic')
def get_conn():
    return pymysql.connect(**DB)
def init_db_and_tables():
    conn = pymysql.connect(host=DB['host'],port=DB['port'],user=DB['user'],password=DB['password'],charset='utf8mb4')
    cur=conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS finance_chatbi DEFAULT CHARSET utf8mb4")
    conn.select_db('finance_chatbi')
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contract_tb (
            id INT AUTO_INCREMENT PRIMARY KEY,
            contract_no  VARCHAR(64)  COMMENT '合同编号',
            contract_name VARCHAR(255) COMMENT '合同名称',
            contract_amount DECIMAL(18,2) COMMENT '合同金额',
            net_amount    DECIMAL(18,2) COMMENT '不含税价款',
            contract_type VARCHAR(32)  COMMENT '合同类型(服务/施工/租赁)',
            tax_rate      DECIMAL(8,4) COMMENT '税率',
            tax_amount    DECIMAL(18,2) COMMENT '税额',
            remark        VARCHAR(64)  COMMENT '备注',
            source_month  VARCHAR(32)  COMMENT '所属期间',
            KEY idx_no (contract_no)
        )
    """)
    cur.execute("""
CREATE TABLE IF NOT EXISTS payment_tb (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company      VARCHAR(64)  COMMENT '所属公司',
            project_code VARCHAR(64)  COMMENT '集团统一项目编码',
            project_name VARCHAR(255) COMMENT '项目名称',
            contract_no  VARCHAR(64)  COMMENT '合同编号',
            contract_name VARCHAR(255) COMMENT '合同名称',
            party_a      VARCHAR(128) COMMENT '合同甲方',
            party_b      VARCHAR(128) COMMENT '合同乙方',
            cat1         VARCHAR(64)  COMMENT '合同一级类别',
            cat2         VARCHAR(64)  COMMENT '合同二级类别',
            sign_date    VARCHAR(32)  COMMENT '签订日期',
            dept         VARCHAR(64)  COMMENT '部门名称',
            handler      VARCHAR(64)  COMMENT '经办人',
            start_date   VARCHAR(32)  COMMENT '起始日期',
            contract_amount DECIMAL(18,2) COMMENT '合同当前金额',
            net_amount   DECIMAL(18,2) COMMENT '不含税金额',
            tax_amount   DECIMAL(18,2) COMMENT '税金',
            paid_amount  DECIMAL(18,2) COMMENT '已付款金额',
            unpaid_amount DECIMAL(18,2) COMMENT '未付款金额',
            KEY idx_no (contract_no),
            KEY idx_proj (project_name))
    """)
    cur.execute("""
CREATE TABLE IF NOT EXISTS fin_report_tb (
            id INT AUTO_INCREMENT PRIMARY KEY,
            report_type VARCHAR(64) COMMENT '报表类型',
            item        VARCHAR(255) COMMENT '项目',
            row_no      INT COMMENT '行次',
            month_amount  DECIMAL(18,2) COMMENT '本月数',
            ytd_amount    DECIMAL(18,2) COMMENT '本年累计',
            prev_ytd_amount DECIMAL(18,2) COMMENT '上年同期',
            report_month VARCHAR(32) COMMENT '报表月份'
        )
    """)

    cur.execute("DELETE FROM contract_tb")
    cur.execute("DELETE FROM payment_tb")
    cur.execute("DELETE FROM fin_report_tb")
    conn.commit()
    cur.close();conn.close()
    print("[init]库/表就绪，历史数据清空")
def read_csv_rows(name: str, cols: list) -> list:
    # ↓ 读 synthetic/{name}.csv：空字符串转 None，按 cols 顺序出元组（列顺序与建表/INSERT 一致）
    path = f'{DATA_DIR}/{name}.csv'
    with open(path, newline='', encoding='utf-8') as f:
        rows = []
        for rec in csv.DictReader(f):
            rows.append(tuple(None if (rec.get(c) or '') == '' else rec.get(c) for c in cols))
    print(f'  [read] {path}  {len(rows)} 条')
    return rows
def load_contract():
    cols = ['contract_no','contract_name','contract_amount','net_amount',
            'contract_type','tax_rate','tax_amount','remark','source_month']
    rows = read_csv_rows('contract', cols)
    conn = get_conn(); cur = conn.cursor()
    cur.executemany(
            "INSERT INTO contract_tb (contract_no,contract_name,contract_amount,net_amount,"
        "contract_type,tax_rate,tax_amount,remark,source_month) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    conn.commit()
    print(f"[contract_tb]写入 {len(rows)} 条")
    cur.close();conn.close()
def load_payment():
    cols = ['company','project_code','project_name','contract_no','contract_name',
            'party_a','party_b','cat1','cat2','sign_date','dept','handler','start_date',
            'contract_amount','net_amount','tax_amount','paid_amount','unpaid_amount']
    rows = read_csv_rows('payment', cols)
    conn = get_conn(); cur = conn.cursor()
    cur.executemany(
        "INSERT INTO payment_tb (company,project_code,project_name,contract_no,contract_name,"
        "party_a,party_b,cat1,cat2,sign_date,dept,handler,start_date,"
        "contract_amount,net_amount,tax_amount,paid_amount,unpaid_amount) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    conn.commit()
    print(f"[payment_tb]写入 {len(rows)} 条")
    cur.close(); conn.close()
def load_fin_report():
    cols = ['report_type','item','row_no','month_amount','ytd_amount',
            'prev_ytd_amount','report_month']
    rows = read_csv_rows('fin_report', cols)
    conn = get_conn(); cur =conn.cursor()
    cur.executemany(
        "INSERT INTO fin_report_tb (report_type,item,row_no,month_amount,ytd_amount,"
        "prev_ytd_amount,report_month) VALUES (%s,%s,%s,%s,%s,%s,%s)",rows)
    conn.commit()
    print(f"[fin_report_tb]写入 {len(rows)} 条")
    cur.close(); conn.close()
if __name__=='__main__':
    init_db_and_tables()
    load_contract()
    load_payment()
    load_fin_report()
    print("[完成] 全部灌数成功")
    

