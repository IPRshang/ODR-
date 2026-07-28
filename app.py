"""
维权快速响应系统 - 后端 API
基于 Flask + SQLite
"""

import json
import os
import sqlite3
import uuid
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g, send_from_directory

app = Flask(__name__, static_folder='static', static_url_path='/static')
DB_PATH = os.path.join(os.path.dirname(__file__), 'ip_protection.db')
PATSNAP_CONFIG = os.path.join(os.path.dirname(__file__), 'patsnap_config.json')
PATSNAP_BASE_URL = 'https://connect.patsnap.com'

# ============ 数据库 ============

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript('''
        -- 案件主表
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
            
            -- 第二步：初步评估
            assessor TEXT,
            assessment_time TEXT,
            assessment_result TEXT,
            assessment_detail TEXT,
            matched_patents TEXT DEFAULT '[]',
            competitor_monitor TEXT DEFAULT '[]',
            
            -- 第三步：决策审批
            approval_status TEXT DEFAULT 'pending',
            approval_decision TEXT,
            approval_comment TEXT,
            approval_time TEXT,
            approver TEXT,
            estimated_cost REAL,
            suggested_plan TEXT,
            
            -- 第四步：证据保全
            evidence_status TEXT DEFAULT 'pending',
            evidence_list TEXT DEFAULT '[]',
            
            -- 第五步：侵权比对
            comparison_status TEXT DEFAULT 'pending',
            comparison_report TEXT,
            strategy_doc TEXT,
            design_comparison TEXT,
            
            -- 第六步：法律行动
            legal_status TEXT DEFAULT 'pending',
            legal_stage TEXT,
            legal_notes TEXT,
            
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 案件时间线
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

        -- 证据文件
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

        -- 文档
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

        -- 期限监控
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

        -- 专利库
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

        -- 竞对监控库
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

        -- 操作日志
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            operator TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    ''')
    db.commit()
    db.close()

init_db()

# ============ 工具函数 ============

def gen_id():
    return str(uuid.uuid4())[:8]

def gen_case_no():
    today = datetime.now().strftime('%Y%m%d')
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM cases WHERE case_no LIKE ?", (f'WQ{today}%',)).fetchone()[0]
    return f"WQ{today}{count+1:03d}"

def add_timeline(case_id, event_type, event_title, event_detail='', operator='系统'):
    db = get_db()
    db.execute(
        "INSERT INTO case_timeline (case_id, event_type, event_title, event_detail, operator) VALUES (?,?,?,?,?)",
        (case_id, event_type, event_title, event_detail, operator)
    )
    db.commit()

def log_audit(case_id, action, detail='', operator='系统'):
    db = get_db()
    db.execute("INSERT INTO audit_log (case_id, action, detail, operator) VALUES (?,?,?,?)",
               (case_id, action, detail, operator))
    db.commit()

# ============ API 路由 ============

# --- 首页 ---
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# --- 案件 CRUD ---
@app.route('/api/cases', methods=['GET'])
def list_cases():
    db = get_db()
    stage = request.args.get('stage')
    status = request.args.get('status')
    keyword = request.args.get('keyword')
    
    sql = "SELECT * FROM cases WHERE 1=1"
    params = []
    
    if stage:
        sql += " AND current_stage = ?"
        params.append(int(stage))
    if status:
        sql += " AND stage_status = ?"
        params.append(status)
    if keyword:
        sql += " AND (title LIKE ? OR case_no LIKE ? OR competitor_name LIKE ?)"
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])
    
    sql += " ORDER BY updated_at DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/cases/<case_id>', methods=['GET'])
def get_case(case_id):
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not row:
        return jsonify({"error": "案件不存在"}), 404
    
    result = dict(row)
    # 附加时间线
    timeline = db.execute(
        "SELECT * FROM case_timeline WHERE case_id = ? ORDER BY created_at DESC",
        (case_id,)
    ).fetchall()
    result['timeline'] = [dict(t) for t in timeline]
    
    # 附加证据
    evidence = db.execute(
        "SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at DESC",
        (case_id,)
    ).fetchall()
    result['evidence'] = [dict(e) for e in evidence]
    
    # 附加文档
    docs = db.execute(
        "SELECT * FROM documents WHERE case_id = ? ORDER BY created_at DESC",
        (case_id,)
    ).fetchall()
    result['documents'] = [dict(d) for d in docs]
    
    # 附加期限
    deadlines = db.execute(
        "SELECT * FROM deadlines WHERE case_id = ? ORDER BY due_date ASC",
        (case_id,)
    ).fetchall()
    result['deadlines'] = [dict(d) for d in deadlines]
    
    return jsonify(result)

@app.route('/api/cases', methods=['POST'])
def create_case():
    data = request.json
    db = get_db()
    case_id = gen_id()
    case_no = gen_case_no()
    
    db.execute('''
        INSERT INTO cases (id, case_no, title, priority, reporter, reporter_dept,
            report_time, report_location, competitor_name, infringing_product,
            lead_description, lead_attachments)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        case_id, case_no,
        data.get('title', ''),
        data.get('priority', 'normal'),
        data.get('reporter', ''),
        data.get('reporter_dept', ''),
        data.get('report_time', datetime.now().strftime('%Y-%m-%d %H:%M')),
        data.get('report_location', ''),
        data.get('competitor_name', ''),
        data.get('infringing_product', ''),
        data.get('lead_description', ''),
        json.dumps(data.get('lead_attachments', []), ensure_ascii=False)
    ))
    db.commit()
    
    add_timeline(case_id, 'lead_submit', '线索提报', f'案件编号: {case_no}', data.get('reporter', '系统'))
    log_audit(case_id, 'create', f'创建案件 {case_no}')
    
    return jsonify({"id": case_id, "case_no": case_no}), 201

@app.route('/api/cases/<case_id>', methods=['PUT'])
def update_case(case_id):
    data = request.json
    db = get_db()
    
    allowed_fields = [
        'title', 'priority', 'reporter', 'reporter_dept', 'report_time',
        'report_location', 'competitor_name', 'infringing_product',
        'lead_description', 'current_stage', 'stage_status'
    ]
    
    updates = []
    params = []
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    
    if updates:
        updates.append("updated_at = ?")
        params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        params.append(case_id)
        sql = f"UPDATE cases SET {', '.join(updates)} WHERE id = ?"
        db.execute(sql, params)
        db.commit()
    
    return jsonify({"success": True})

# --- 第二步：初步评估 ---
@app.route('/api/cases/<case_id>/assessment', methods=['PUT'])
def submit_assessment(case_id):
    """提交初步评估"""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE cases SET
            assessor = ?,
            assessment_time = ?,
            assessment_result = ?,
            assessment_detail = ?,
            matched_patents = ?,
            competitor_monitor = ?,
            current_stage = 2,
            updated_at = ?
        WHERE id = ?
    ''', (
        data.get('assessor', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data.get('assessment_result', ''),
        data.get('assessment_detail', ''),
        json.dumps(data.get('matched_patents', []), ensure_ascii=False),
        json.dumps(data.get('competitor_monitor', []), ensure_ascii=False),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        case_id
    ))
    db.commit()
    
    add_timeline(case_id, 'assessment', '初步评估完成',
                 f'评估结论: {data.get("assessment_result", "")}',
                 data.get('assessor', '系统'))
    log_audit(case_id, 'assessment', f'评估结果: {data.get("assessment_result", "")}')
    
    return jsonify({"success": True})

# --- 第三步：决策审批 ---
@app.route('/api/cases/<case_id>/approval', methods=['PUT'])
def submit_approval(case_id):
    """提交决策审批"""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE cases SET
            approval_status = ?,
            approval_decision = ?,
            approval_comment = ?,
            approval_time = ?,
            approver = ?,
            estimated_cost = ?,
            suggested_plan = ?,
            current_stage = 3,
            stage_status = ?,
            updated_at = ?
        WHERE id = ?
    ''', (
        data.get('approval_status', 'approved'),
        data.get('approval_decision', ''),
        data.get('approval_comment', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data.get('approver', ''),
        data.get('estimated_cost', 0),
        data.get('suggested_plan', ''),
        'completed' if data.get('approval_decision') == 'approved' else 'rejected',
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        case_id
    ))
    db.commit()
    
    decision_map = {'approved': '批准启动', 'rejected': '驳回', 'returned': '退回修改'}
    decision_text = decision_map.get(data.get('approval_decision'), data.get('approval_decision', ''))
    add_timeline(case_id, 'approval', f'管理层审批: {decision_text}',
                 data.get('approval_comment', ''),
                 data.get('approver', '系统'))
    log_audit(case_id, 'approval', f'审批结果: {decision_text}')
    
    return jsonify({"success": True})

# --- 第四步：证据保全 ---
@app.route('/api/cases/<case_id>/evidence', methods=['POST'])
def add_evidence(case_id):
    """添加证据"""
    data = request.json
    db = get_db()
    ev_id = gen_id()
    
    db.execute('''
        INSERT INTO evidence (id, case_id, file_name, file_type, file_size,
            evidence_type, uploader, description)
        VALUES (?,?,?,?,?,?,?,?)
    ''', (
        ev_id, case_id,
        data.get('file_name', ''),
        data.get('file_type', ''),
        data.get('file_size', 0),
        data.get('evidence_type', ''),
        data.get('uploader', ''),
        data.get('description', '')
    ))
    db.commit()
    
    # 更新案件证据状态
    count = db.execute("SELECT COUNT(*) FROM evidence WHERE case_id = ?", (case_id,)).fetchone()[0]
    if count > 0:
        db.execute("UPDATE cases SET evidence_status = 'in_progress', current_stage = 4, updated_at = ? WHERE id = ?",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), case_id))
        db.commit()
    
    add_timeline(case_id, 'evidence', f'证据上传: {data.get("file_name", "")}',
                 data.get('description', ''), data.get('uploader', '系统'))
    log_audit(case_id, 'evidence_add', f'证据: {data.get("file_name", "")}')
    
    return jsonify({"id": ev_id}), 201

@app.route('/api/cases/<case_id>/evidence', methods=['GET'])
def list_evidence(case_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at DESC",
        (case_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

# --- 第五步：侵权比对 ---
@app.route('/api/cases/<case_id>/comparison', methods=['PUT'])
def submit_comparison(case_id):
    """提交侵权比对"""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE cases SET
            comparison_status = ?,
            comparison_report = ?,
            strategy_doc = ?,
            design_comparison = ?,
            current_stage = 5,
            updated_at = ?
        WHERE id = ?
    ''', (
        data.get('comparison_status', 'completed'),
        data.get('comparison_report', ''),
        data.get('strategy_doc', ''),
        data.get('design_comparison', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        case_id
    ))
    db.commit()
    
    add_timeline(case_id, 'comparison', '侵权比对完成', '比对报告已生成', data.get('operator', '系统'))
    log_audit(case_id, 'comparison', '侵权比对完成')
    
    return jsonify({"success": True})

# --- 第六步：法律行动 ---
@app.route('/api/cases/<case_id>/legal', methods=['PUT'])
def update_legal(case_id):
    """更新法律行动状态"""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE cases SET
            legal_status = ?,
            legal_stage = ?,
            legal_notes = ?,
            current_stage = 6,
            updated_at = ?
        WHERE id = ?
    ''', (
        data.get('legal_status', 'in_progress'),
        data.get('legal_stage', ''),
        data.get('legal_notes', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        case_id
    ))
    db.commit()
    
    add_timeline(case_id, 'legal', f'法律行动更新: {data.get("legal_stage", "")}',
                 data.get('legal_notes', ''), data.get('operator', '系统'))
    log_audit(case_id, 'legal_update', f'法律阶段: {data.get("legal_stage", "")}')
    
    return jsonify({"success": True})

# --- 文档管理 ---
@app.route('/api/cases/<case_id>/documents', methods=['POST'])
def add_document(case_id):
    data = request.json
    db = get_db()
    doc_id = gen_id()
    
    db.execute('''
        INSERT INTO documents (id, case_id, doc_name, doc_type, doc_category, uploader, description)
        VALUES (?,?,?,?,?,?,?)
    ''', (doc_id, case_id, data.get('doc_name',''), data.get('doc_type',''),
          data.get('doc_category',''), data.get('uploader',''), data.get('description','')))
    db.commit()
    
    add_timeline(case_id, 'document', f'文档上传: {data.get("doc_name", "")}', data.get('description',''), data.get('uploader',''))
    return jsonify({"id": doc_id}), 201

@app.route('/api/cases/<case_id>/documents', methods=['GET'])
def list_documents(case_id):
    db = get_db()
    rows = db.execute("SELECT * FROM documents WHERE case_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

# --- 期限管理 ---
@app.route('/api/cases/<case_id>/deadlines', methods=['POST'])
def add_deadline(case_id):
    data = request.json
    db = get_db()
    dl_id = gen_id()
    
    db.execute('''
        INSERT INTO deadlines (id, case_id, title, deadline_type, due_date, remind_days_before, responsible_person)
        VALUES (?,?,?,?,?,?,?)
    ''', (dl_id, case_id, data.get('title',''), data.get('deadline_type',''),
          data.get('due_date',''), data.get('remind_days_before',7), data.get('responsible_person','')))
    db.commit()
    return jsonify({"id": dl_id}), 201

@app.route('/api/cases/<case_id>/deadlines', methods=['GET'])
def list_deadlines(case_id):
    db = get_db()
    rows = db.execute("SELECT * FROM deadlines WHERE case_id = ? ORDER BY due_date ASC", (case_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/deadlines/urgent', methods=['GET'])
def urgent_deadlines():
    """获取即将到期的期限"""
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    week_later = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    rows = db.execute('''
        SELECT d.*, c.case_no, c.title as case_title
        FROM deadlines d JOIN cases c ON d.case_id = c.id
        WHERE d.due_date BETWEEN ? AND ? AND d.status = 'pending'
        ORDER BY d.due_date ASC
    ''', (today, week_later)).fetchall()
    return jsonify([dict(r) for r in rows])

# --- 专利库 ---
@app.route('/api/patents', methods=['GET'])
def list_patents():
    db = get_db()
    keyword = request.args.get('keyword', '')
    if keyword:
        rows = db.execute(
            "SELECT * FROM patents WHERE patent_name LIKE ? OR patent_no LIKE ? OR key_features LIKE ?",
            (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM patents ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/patents', methods=['POST'])
def add_patent():
    data = request.json
    db = get_db()
    patent_id = gen_id()
    
    db.execute('''
        INSERT INTO patents (id, patent_no, patent_name, patent_type, applicant, status,
            filing_date, grant_date, tech_field, key_features)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (patent_id, data.get('patent_no',''), data.get('patent_name',''),
          data.get('patent_type',''), data.get('applicant',''), data.get('status',''),
          data.get('filing_date',''), data.get('grant_date',''),
          data.get('tech_field',''), data.get('key_features','')))
    db.commit()
    return jsonify({"id": patent_id}), 201

# --- 竞对监控 ---
@app.route('/api/competitors', methods=['GET'])
def list_competitors():
    db = get_db()
    rows = db.execute("SELECT * FROM competitors ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/competitors', methods=['POST'])
def add_competitor():
    data = request.json
    db = get_db()
    comp_id = gen_id()
    
    db.execute('''
        INSERT INTO competitors (id, name, alias, products, monitor_keywords, alert_enabled)
        VALUES (?,?,?,?,?,?)
    ''', (comp_id, data.get('name',''), data.get('alias',''), data.get('products',''),
          data.get('monitor_keywords',''), data.get('alert_enabled',1)))
    db.commit()
    return jsonify({"id": comp_id}), 201

# --- 统计仪表盘 ---
@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    db = get_db()
    
    total = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    
    stage_counts = {}
    for i in range(1, 7):
        stage_counts[f'stage_{i}'] = db.execute(
            "SELECT COUNT(*) FROM cases WHERE current_stage = ?", (i,)
        ).fetchone()[0]
    
    status_counts = {}
    for s in ['pending', 'in_progress', 'completed', 'rejected']:
        status_counts[s] = db.execute(
            "SELECT COUNT(*) FROM cases WHERE stage_status = ?", (s,)
        ).fetchone()[0]
    
    urgent = db.execute('''
        SELECT COUNT(*) FROM deadlines
        WHERE due_date BETWEEN date('now','localtime') AND date('now','localtime','+7 days')
        AND status = 'pending'
    ''').fetchone()[0]
    
    # 本月新增
    this_month = datetime.now().strftime('%Y-%m')
    monthly_new = db.execute(
        "SELECT COUNT(*) FROM cases WHERE created_at LIKE ?", (f'{this_month}%',)
    ).fetchone()[0]
    
    return jsonify({
        'total_cases': total,
        'stage_distribution': stage_counts,
        'status_distribution': status_counts,
        'urgent_deadlines': urgent,
        'monthly_new': monthly_new
    })

# --- 最近动态 ---
@app.route('/api/dashboard/activities', methods=['GET'])
def recent_activities():
    db = get_db()
    limit = request.args.get('limit', 20)
    rows = db.execute('''
        SELECT t.*, c.case_no, c.title as case_title
        FROM case_timeline t JOIN cases c ON t.case_id = c.id
        ORDER BY t.created_at DESC LIMIT ?
    ''', (int(limit),)).fetchall()
    return jsonify([dict(r) for r in rows])

# ============ 智慧芽集成 ============

def get_patsnap_config():
    """读取智慧芽配置"""
    if os.path.exists(PATSNAP_CONFIG):
        with open(PATSNAP_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'api_key': '', 'auto_search_enabled': False}

def save_patsnap_config(config):
    """保存智慧芽配置"""
    with open(PATSNAP_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def patsnap_request(endpoint, params=None, method='GET', json_body=None):
    """调用智慧芽 API"""
    config = get_patsnap_config()
    api_key = config.get('api_key', '')
    if not api_key:
        raise ValueError('未配置智慧芽 API Key')
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    
    url = f'{PATSNAP_BASE_URL}{endpoint}'
    
    if method == 'GET':
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    else:
        resp = requests.post(url, headers=headers, json=json_body, params=params, timeout=30)
    
    resp.raise_for_status()
    return resp.json()

@app.route('/api/patsnap/config', methods=['GET'])
def get_config():
    """获取智慧芽配置状态"""
    config = get_patsnap_config()
    return jsonify({
        'configured': bool(config.get('api_key')),
        'api_key_masked': config.get('api_key', '')[:8] + '****' if config.get('api_key') else '',
        'auto_search_enabled': config.get('auto_search_enabled', False)
    })

@app.route('/api/patsnap/config', methods=['PUT'])
def update_config():
    """更新智慧芽配置"""
    data = request.json
    config = get_patsnap_config()
    if 'api_key' in data:
        config['api_key'] = data['api_key']
    if 'auto_search_enabled' in data:
        config['auto_search_enabled'] = data['auto_search_enabled']
    save_patsnap_config(config)
    return jsonify({'success': True, 'configured': bool(config.get('api_key'))})

@app.route('/api/patsnap/search', methods=['POST'])
def patsnap_patent_search():
    """代理智慧芽专利语义检索"""
    try:
        data = request.json
        query = data.get('query', '')
        if not query:
            return jsonify({'error': '请输入搜索关键词'}), 400
        
        # 调用智慧芽语义检索 API (v2)
        result = patsnap_request(
            '/search/patent/semantic-search-patent/v2',
            method='POST',
            json_body={
                'text': query,
                'limit': 20
            }
        )
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except requests.RequestException as e:
        return jsonify({'error': f'智慧芽API调用失败: {str(e)}'}), 502

@app.route('/api/patsnap/image-search', methods=['POST'])
def patsnap_image_search():
    """代理智慧芽外观专利图像检索"""
    try:
        data = request.json
        image_url = data.get('image_url', '')
        if not image_url:
            return jsonify({'error': '请提供图片URL'}), 400
        
        result = patsnap_request(
            '/image-search/search',
            params={'url': image_url, 'limit': 20}
        )
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except requests.RequestException as e:
        return jsonify({'error': f'智慧芽API调用失败: {str(e)}'}), 502

@app.route('/api/patsnap/legal-status', methods=['GET'])
def patsnap_legal_status():
    """查询专利法律状态"""
    try:
        patent_no = request.args.get('patent_no', '')
        if not patent_no:
            return jsonify({'error': '请提供专利号'}), 400
        
        result = patsnap_request(
            '/advanced-patent-data/legal-data',
            params={'patent_number': patent_no}
        )
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except requests.RequestException as e:
        return jsonify({'error': f'智慧芽API调用失败: {str(e)}'}), 502

@app.route('/api/patsnap/competitor', methods=['GET'])
def patsnap_competitor_search():
    """查询竞对公司专利布局"""
    try:
        company = request.args.get('company', '')
        if not company:
            return jsonify({'error': '请提供公司名称'}), 400
        
        result = patsnap_request(
            '/search/patent/query-search-patent/v2',
            method='POST',
            json_body={
                'query_text': f'AN: "{company}"',
                'page_size': 50
            }
        )
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except requests.RequestException as e:
        return jsonify({'error': f'智慧芽API调用失败: {str(e)}'}), 502

# --- 首页路由 ---

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
