"""
数据库迁移脚本 - 用于给 packed_cargos 表添加新字段
运行方式：python3 migrate_db.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stowage.db")


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("检查 packed_cargos 表迁移...")

    if not column_exists(cursor, "packed_cargos", "max_top_load"):
        cursor.execute("ALTER TABLE packed_cargos ADD COLUMN max_top_load FLOAT DEFAULT 0.0")
        print("  - 添加 max_top_load 字段")
    else:
        print("  - max_top_load 字段已存在")

    if not column_exists(cursor, "packed_cargos", "original_length"):
        cursor.execute("ALTER TABLE packed_cargos ADD COLUMN original_length FLOAT")
        print("  - 添加 original_length 字段")
    else:
        print("  - original_length 字段已存在")

    if not column_exists(cursor, "packed_cargos", "original_width"):
        cursor.execute("ALTER TABLE packed_cargos ADD COLUMN original_width FLOAT")
        print("  - 添加 original_width 字段")
    else:
        print("  - original_width 字段已存在")

    if not column_exists(cursor, "packed_cargos", "original_height"):
        cursor.execute("ALTER TABLE packed_cargos ADD COLUMN original_height FLOAT")
        print("  - 添加 original_height 字段")
    else:
        print("  - original_height 字段已存在")

    print()
    print("检查 stowage_reports 表...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stowage_reports'")
    if cursor.fetchone():
        print("  - stowage_reports 表已存在")
    else:
        print("  - stowage_reports 表不存在，将由应用启动时自动创建")

    conn.commit()
    conn.close()
    print()
    print("迁移完成!")


if __name__ == "__main__":
    migrate()
