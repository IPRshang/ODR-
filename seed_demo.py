"""初始化演示数据 - 独立运行，不依赖Flask上下文"""
import sqlite3
import uuid
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'ip_protection.db')

# 如果旧数据库存在则删除
if os.path.exists(DB_PATH):
    try:
        os.unlink(DB_PATH)
    except:
        pass

def gen_id():
    return str(uuid.uuid4())[:8]

# 复制 app.py 的 init_db 逻辑
db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA foreign_keys=ON")

db.executescript('''
    CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY,
        case_no TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        current_stage INTEGER DEFAULT 1,
        stage_status TEXT DEFAULT 'pending',
        priority TEXT DEFAULT 'normal',
        reporter TEXT,
        reporter_dept TEXT,
        report_time TEXT,
        report_location TEXT,
        competitor_name TEXT,
        infringing_product TEXT,
        lead_description TEXT,
        lead_attachments TEXT DEFAULT '[]',
        assessor TEXT,
        assessment_time TEXT,
        assessment_result TEXT,
        assessment_detail TEXT,
        matched_patents TEXT DEFAULT '[]',
        competitor_monitor TEXT DEFAULT '[]',
        approval_status TEXT DEFAULT 'pending',
        approval_decision TEXT,
        approval_comment TEXT,
        approval_time TEXT,
        approver TEXT,
        estimated_cost REAL,
        suggested_plan TEXT,
        evidence_status TEXT DEFAULT 'pending',
        evidence_list TEXT DEFAULT '[]',
        comparison_status TEXT DEFAULT 'pending',
        comparison_report TEXT,
        strategy_doc TEXT,
        design_comparison TEXT,
        legal_status TEXT DEFAULT 'pending',
        legal_stage TEXT,
        legal_notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS case_timeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_title TEXT NOT NULL,
        event_detail TEXT,
        operator TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_type TEXT,
        file_size INTEGER,
        evidence_type TEXT,
        uploader TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        doc_name TEXT NOT NULL,
        doc_type TEXT,
        doc_category TEXT,
        uploader TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS deadlines (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        title TEXT NOT NULL,
        deadline_type TEXT,
        due_date TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        remind_days_before INTEGER DEFAULT 7,
        reminded INTEGER DEFAULT 0,
        responsible_person TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS patents (
        id TEXT PRIMARY KEY,
        patent_no TEXT UNIQUE NOT NULL,
        patent_name TEXT NOT NULL,
        patent_type TEXT,
        applicant TEXT,
        status TEXT,
        filing_date TEXT,
        grant_date TEXT,
        tech_field TEXT,
        key_features TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS competitors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        alias TEXT,
        products TEXT,
        monitor_keywords TEXT,
        alert_enabled INTEGER DEFAULT 1,
        last_check_time TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        operator TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
''')

def add_timeline(case_id, event_type, event_title, event_detail='', operator='系统'):
    db.execute(
        "INSERT INTO case_timeline (case_id, event_type, event_title, event_detail, operator) VALUES (?,?,?,?,?)",
        (case_id, event_type, event_title, event_detail, operator)
    )

# === 演示专利 ===
patents_data = [
    ('CN202310123456.7', '一种基于深度学习的图像识别方法', '发明专利', '本公司', '有权', '2023-06-15', '2024-03-20', '人工智能', 'CNN+Transformer混合架构,多尺度特征融合,自适应注意力机制'),
    ('CN202310234567.8', '智能传感器数据采集系统', '发明专利', '本公司', '有权', '2023-08-20', '2024-05-10', '物联网', '低功耗无线传输,边缘计算,多传感器融合'),
    ('CN202320345678.9', '便携式环境监测设备', '实用新型', '本公司', '有权', '2023-10-12', '2024-06-01', '环境监测', '模块化设计,IP68防水,太阳能供电'),
    ('CN202330456789.0', '智能手表（外观设计）', '外观设计', '本公司', '有权', '2023-12-05', '2024-07-15', '消费电子', '圆形表盘,弧形玻璃,快拆表带结构'),
    ('CN202310567890.1', '基于区块链的数据溯源方法', '发明专利', '本公司', '审中', '2024-02-18', '', '区块链', '分布式账本,智能合约,数据指纹验证'),
]

for p in patents_data:
    db.execute('''
        INSERT OR IGNORE INTO patents (id, patent_no, patent_name, patent_type, applicant, status, filing_date, grant_date, tech_field, key_features)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (gen_id(),) + p)

# === 演示竞对 ===
competitors_data = [
    ('星河科技有限公司', '星河科技', '智能穿戴设备、AI芯片', 'AI芯片,智能穿戴,传感器', 1),
    ('云翼智能技术有限公司', '云翼智能', '环境监测设备、IoT平台', '环境监测,物联网,传感器', 1),
    ('蓝海创新科技有限公司', '蓝海创新', '图像识别、机器视觉', '图像识别,深度学习,视觉算法', 1),
]

for c in competitors_data:
    db.execute('''
        INSERT OR IGNORE INTO competitors (id, name, alias, products, monitor_keywords, alert_enabled)
        VALUES (?,?,?,?,?,?)
    ''', (gen_id(),) + c)

# === 演示案件1：法律行动中 ===
case_id = gen_id()
case_no = 'WQ20260727001'
db.execute('''
    INSERT INTO cases (id, case_no, title, current_stage, stage_status, priority,
        reporter, reporter_dept, report_time, report_location,
        competitor_name, infringing_product, lead_description,
        assessment_result, assessment_detail, assessor,
        matched_patents, approval_decision, approval_comment,
        evidence_status, comparison_report, strategy_doc,
        legal_status, legal_stage, legal_notes)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
''', (
    case_id, case_no,
    '星河科技涉嫌侵犯图像识别专利', 6, 'in_progress', 'high',
    '张三', '销售部', '2026-07-20 14:30', '上海国际会展中心',
    '星河科技有限公司', '星眸X3智能摄像头',
    '在展会上发现星河科技展出的星眸X3智能摄像头产品涉嫌抄袭我司图像识别算法专利技术...',
    '可诉', '经智慧芽AI特征比对，星眸X3使用的CNN+Transformer混合架构与我司CN202310123456.7专利高度相似...',
    '李四',
    json.dumps(['CN202310123456.7'], ensure_ascii=False),
    'approved', '批准启动维权，预算50万元以内',
    'in_progress',
    '侵权比对结论：星眸X3产品的图像识别模块与我司CN202310123456.7专利权利要求1-5存在实质性相似...',
    '建议先发律师函警告，同时准备证据保全和诉讼材料...',
    'in_progress', '立案', '2026年7月25日向上海知识产权法院递交起诉状，已正式立案...'
))
add_timeline(case_id, 'lead_submit', '线索提报', '张三在上海国际会展中心发现星河科技侵权线索')
add_timeline(case_id, 'assessment', '初步评估完成', '李四通过智慧芽AI特征比对确认高度相似', '李四')
add_timeline(case_id, 'approval', '管理层审批：批准启动', '预算50万元，建议先发律师函', '王五')
add_timeline(case_id, 'evidence', '证据上传：公证书_20260721.pdf', '展会现场公证取证', '李四')
add_timeline(case_id, 'evidence', '证据上传：产品拆解报告.pdf', '技术特征详细对比', '法务部')
add_timeline(case_id, 'comparison', '侵权比对完成', '比对报告确认实质性相似', '李四')
add_timeline(case_id, 'legal', '法律行动：立案', '已向上海知识产权法院立案', '法务部')

db.execute("INSERT INTO evidence (id, case_id, file_name, file_type, evidence_type, uploader, description) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '公证书_20260721.pdf', 'pdf', '公证书', '李四', '上海东方公证处出具，对星河科技展会现场取证'))
db.execute("INSERT INTO evidence (id, case_id, file_name, file_type, evidence_type, uploader, description) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '技术拆解对比报告.pdf', 'pdf', '其他', 'IP部', '星眸X3产品技术拆解与我司专利详细对比'))

db.execute("INSERT INTO documents (id, case_id, doc_name, doc_type, doc_category, uploader, description) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '侵权比对报告_20260722.pdf', '侵权比对报告', '分析报告', '李四', '智慧芽AI防侵权检索Agent自动生成'))
db.execute("INSERT INTO documents (id, case_id, doc_name, doc_type, doc_category, uploader, description) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '维权策略方案_v1.pdf', '维权策略方案', '内部文件', 'IP部', '包含律师函、行政投诉、民事诉讼三级策略'))
db.execute("INSERT INTO documents (id, case_id, doc_name, doc_type, doc_category, uploader, description) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '起诉状_20260725.pdf', '起诉状', '诉讼文书', '法务部', '上海知识产权法院'))

db.execute("INSERT INTO deadlines (id, case_id, title, deadline_type, due_date, remind_days_before, responsible_person) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '举证期限', '举证期限', (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'), 7, '李四'))
db.execute("INSERT INTO deadlines (id, case_id, title, deadline_type, due_date, remind_days_before, responsible_person) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '首次开庭', '开庭日期', (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d'), 7, '法务部'))
db.execute("INSERT INTO deadlines (id, case_id, title, deadline_type, due_date, remind_days_before, responsible_person) VALUES (?,?,?,?,?,?,?)",
           (gen_id(), case_id, '诉讼费缴纳', '官费缴纳', (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'), 3, '法务部'))

# === 演示案件2：审批中 ===
case_id2 = gen_id()
case_no2 = 'WQ20260727002'
db.execute('''
    INSERT INTO cases (id, case_no, title, current_stage, stage_status, priority,
        reporter, reporter_dept, report_time,
        competitor_name, infringing_product, lead_description,
        assessment_result, assessment_detail, assessor, matched_patents)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
''', (
    case_id2, case_no2,
    '云翼智能涉嫌侵犯环境监测设备专利', 3, 'in_progress', 'normal',
    '赵六', '研发部', '2026-07-25 10:00',
    '云翼智能技术有限公司', '云鹰ENV-200环境监测仪',
    '研发团队在京东平台发现云翼智能销售的环境监测仪与我司专利产品高度相似...',
    '可诉', '经检索比对，云鹰ENV-200的模块化结构设计与我司CN202320345678.9实用新型专利存在相似之处...',
    '李四',
    json.dumps(['CN202320345678.9'], ensure_ascii=False)
))
add_timeline(case_id2, 'lead_submit', '线索提报', '赵六在电商平台发现侵权产品')
add_timeline(case_id2, 'assessment', '初步评估：可诉', '模块化结构设计存在侵权嫌疑', '李四')

# === 演示案件3：评估中 ===
case_id3 = gen_id()
case_no3 = 'WQ20260727003'
db.execute('''
    INSERT INTO cases (id, case_no, title, current_stage, stage_status, priority,
        reporter, reporter_dept, report_time,
        competitor_name, infringing_product, lead_description)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
''', (
    case_id3, case_no3,
    '蓝海创新涉嫌外观设计侵权', 2, 'in_progress', 'low',
    '钱七', '市场部', '2026-07-26 16:00',
    '蓝海创新科技有限公司', '蓝海穿戴Pro智能手表',
    '市场部在抖音平台发现蓝海创新最新款智能手表外观与我司专利产品极为相似...'
))
add_timeline(case_id3, 'lead_submit', '线索提报', '钱七在社交媒体发现外观侵权线索')

db.commit()
db.close()
print("✅ 演示数据初始化完成！")
print(f"   专利: 5条")
print(f"   竞对: 3条")
print(f"   案件: 3条（法律行动中1条、审批中1条、评估中1条）")
