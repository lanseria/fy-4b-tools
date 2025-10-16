# --- File: cleanup_noon_only.py ---
import os
import json
import shutil
import argparse
from datetime import datetime, timezone, timedelta

def cleanup_timestamps(target_dir, timezone_offset, execute=False):
    """
    清理指定目录下的时间戳数据，只保留指定时区中午12点的数据。

    Args:
        target_dir (str): 包含 timestamps.json 和时间戳文件夹的目录。
        timezone_offset (int): 用于判断“中午”的时区偏移量（小时）。
        execute (bool): 是否真实执行删除操作。False表示演习模式。
    """
    json_path = os.path.join(target_dir, 'timestamps.json')
    if not os.path.exists(json_path):
        print(f"❌ 错误: 在目录 '{target_dir}' 中未找到 'timestamps.json' 文件。")
        return

    print(f"--- 正在处理目录: {target_dir} ---")
    print(f"--- 操作模式: {'🔴 真实执行' if execute else '🟡 演习模式 (不删除任何文件)'} ---")
    print(f"--- 时区标准: UTC{'+' if timezone_offset >= 0 else ''}{timezone_offset} ---")

    try:
        with open(json_path, 'r') as f:
            all_timestamps = json.load(f)
        if not isinstance(all_timestamps, list):
            print(f"❌ 错误: 'timestamps.json' 的内容不是一个列表。")
            return
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"❌ 错误: 读取或解析 'timestamps.json' 失败: {e}")
        return

    timestamps_to_keep = []
    timestamps_to_remove = []
    target_tz = timezone(timedelta(hours=timezone_offset))

    # 1. 分类所有时间戳
    for ts in all_timestamps:
        try:
            # 将Unix时间戳（UTC）转换为指定时区的datetime对象
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_local = dt_utc.astimezone(target_tz)
            
            # 检查是否为中午12:00:00
            if dt_local.hour == 12 and dt_local.minute == 0 and dt_local.second == 0:
                timestamps_to_keep.append(ts)
            else:
                timestamps_to_remove.append(ts)
        except (ValueError, TypeError) as e:
            print(f"⚠️ 警告: 跳过无效的时间戳 '{ts}': {e}")
            
    print("\n--- 分析完成 ---")
    print(f"🔵 将保留 {len(timestamps_to_keep)} 个时间戳 (中午12点)。")
    print(f"🟡 将移除 {len(timestamps_to_remove)} 个时间戳 (非中午12点)。")
    if not timestamps_to_remove:
        print("\n无需清理，所有时间戳均符合保留条件。")
        return

    # 2. 移除对应的文件夹
    print("\n--- 开始处理文件夹 ---")
    for ts in timestamps_to_remove:
        folder_path = os.path.join(target_dir, str(ts))
        if os.path.isdir(folder_path):
            if execute:
                try:
                    shutil.rmtree(folder_path)
                    print(f"🗑️ 已删除文件夹: {folder_path}")
                except OSError as e:
                    print(f"❌ 删除失败: {folder_path} - {e}")
            else:
                print(f"模拟删除文件夹: {folder_path}")
        else:
            print(f"ℹ️  文件夹不存在，无需删除: {folder_path}")

    # 3. 更新 timestamps.json 文件
    if execute:
        print("\n--- 正在更新 timestamps.json 文件 ---")
        try:
            timestamps_to_keep.sort()
            with open(json_path, 'w') as f:
                json.dump(timestamps_to_keep, f, indent=2)
            print("✅ 'timestamps.json' 文件更新成功。")
        except IOError as e:
            print(f"❌ 写入 'timestamps.json' 失败: {e}")
    else:
        print("\n--- (演习模式) 未修改 'timestamps.json' 文件 ---")

    print("\n✅ 清理任务完成！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="清理卫星瓦片数据，只保留每天中午12点的时间戳和对应文件夹。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "target_dir",
        type=str,
        help="包含 'timestamps.json' 和瓦片数据文件夹的目标目录。\n"
            "例如: /home/bmc-r1/share/data/zoom-earth-tiles/fy-4b"
    )
    parser.add_argument(
        "-tz", "--timezone",
        type=int,
        default=8,
        help="用于判断'中午12点'的时区，以小时为单位相对UTC的偏移量。\n"
            "例如: 8 代表北京时间 (UTC+8)。默认为 8。"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除操作。如果没有此标志，脚本将只进行演习，报告将要执行的操作而不修改任何文件。"
    )

    args = parser.parse_args()

    cleanup_timestamps(args.target_dir, args.timezone, args.execute)