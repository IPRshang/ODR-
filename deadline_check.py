"""
期限监控检查脚本
用法：
  python deadline_check.py          # 终端输出报告
  python deadline_check.py --json   # JSON 格式输出（供自动化消费）
  python deadline_check.py --mark   # 标记已提醒（避免重复提醒）
"""
import sqlite3
import os
import sys
import json
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), 'ip_protection.db')

def get_upcoming_deadlines():
    """查询即将到期的期限（含逾期）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    today = date.today()

    # 查询所有 pending 状态的期限，联表查案件信息
    cur.execute('''
        SELECT d.id, d.title, d.due_date, d.status, d.remind_days_before,
               d.reminded, d.responsible_person, d.deadline_type,
               c.case_no, c.title as case_title, c.current_stage
        FROM deadlines d
        LEFT JOIN cases c ON d.case_id = c.id
        WHERE d.status = 'pending'
        ORDER BY d.due_date ASC
    ''')

    upcoming = []
    overdue = []
    today_items = []

    for row in cur.fetchall():
        due_date = datetime.strptime(row['due_date'], '%Y-%m-%d').date()
        days_left = (due_date - today).days
        remind_before = row['remind_days_before'] or 7

        item = {
            'id': row['id'],
            'title': row['title'],
            'due_date': row['due_date'],
            'days_left': days_left,
            'remind_days_before': remind_before,
            'responsible_person': row['responsible_person'] or '未指定',
            'deadline_type': row['deadline_type'] or '',
            'case_no': row['case_no'] or '',
            'case_title': row['case_title'] or '',
            'current_stage': row['current_stage'],
            'reminded': row['reminded'],
        }

        if days_left < 0:
            item['level'] = 'overdue'
            overdue.append(item)
        elif days_left == 0:
            item['level'] = 'today'
            today_items.append(item)
        elif days_left <= remind_before:
            item['level'] = 'upcoming'
            upcoming.append(item)

    conn.close()
    return upcoming, today_items, overdue

def mark_reminded(ids):
    """将指定期限标记为已提醒"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for id_ in ids:
        cur.execute(
            'UPDATE deadlines SET reminded = 1 WHERE id = ?',
            (id_,)
        )
        # 同时记录提醒日志到 audit_log
        cur.execute(
            'INSERT INTO audit_log (case_id, action, operator, detail, created_at) '
            'SELECT case_id, ?, ?, ?, ? FROM deadlines WHERE id = ?',
            ('system_remind', '自动化', f'期限监控自动提醒 [{now}]', now, id_)
        )
    conn.commit()
    conn.close()

def main():
    json_mode = '--json' in sys.argv
    mark_mode = '--mark' in sys.argv

    upcoming, today_items, overdue = get_upcoming_deadlines()
    all_items = overdue + today_items + upcoming  # 按严重程度排序
    all_ids = [item['id'] for item in all_items]

    if json_mode:
        result = {
            'check_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total': len(all_items),
            'overdue': overdue,
            'today': today_items,
            'upcoming': upcoming,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 终端友好输出
    print('=' * 60)
    print(f'  期限监控检查报告 - {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 60)

    if not all_items:
        print('\n  ✅ 暂无即将到期的期限，一切正常。')
        return

    print(f'\n  ⚠️ 共发现 {len(all_items)} 条需关注的期限:\n')

    sections = [
        ('🔴 已逾期', overdue, lambda x: f'已逾期 {abs(x["days_left"])} 天'),
        ('🟡 今日到期', today_items, lambda x: '今天到期'),
        ('🟢 即将到期', upcoming, lambda x: f'距截止 {x["days_left"]} 天'),
    ]

    for label, items, desc_fn in sections:
        if not items:
            continue
        print(f'  {label} ({len(items)}条):')
        print(f'  {"─" * 50}')
        for item in items:
            desc = desc_fn(item)
            print(f'    📋 {item["title"]}')
            print(f'       案件: {item["case_no"]} {item["case_title"]}')
            print(f'       截止: {item["due_date"]} ({desc})')
            print(f'       负责人: {item["responsible_person"]}')
            print()
        print()

    print('  💡 提示：可在系统中查看详情或更新期限状态。')
    print('=' * 60)

    if mark_mode:
        mark_reminded(all_ids)
        print(f'\n  ✅ 已将 {len(all_ids)} 条期限标记为"已提醒"。')
        print('=' * 60)

if __name__ == '__main__':
    main()
