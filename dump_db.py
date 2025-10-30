import sqlite3
import json

def main():
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for table in ('users', 'tasks'):
        try:
            rows = cur.execute(f'SELECT * FROM {table}').fetchall()
        except Exception as e:
            print(f'[{table}] ERROR: {e}')
            continue
        print(f'[{table}] count={len(rows)}')
        for r in rows:
            print(json.dumps({k: r[k] for k in r.keys()}, ensure_ascii=False))
    conn.close()

if __name__ == '__main__':
    main()


