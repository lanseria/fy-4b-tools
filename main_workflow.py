#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import requests
import json
import time
import schedule
from datetime import datetime, timedelta, timezone

# --- 配置区---
BASE_URL_TEMPLATE = "http://rsapp.nsmc.org.cn/swapQuery/public/tileServer/getTile/fy-4b/full_disk/NatureColor_NoLit/{timestamp}/jpg/0/0/0.png"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
DATA_DIR_DEFAULT = './data'
FAILED_LOG_FILENAME = 'failed_timestamps.json'

# --- 辅助函数---
def read_failed_log(data_dir):
    log_path = os.path.join(data_dir, FAILED_LOG_FILENAME)
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f: return json.load(f)
        except json.JSONDecodeError: return []
    return []

def write_failed_log(data_dir, timestamps):
    log_path = os.path.join(data_dir, FAILED_LOG_FILENAME)
    with open(log_path, 'w') as f: json.dump(timestamps, f, indent=2)

def find_latest_available_timestamp():
    print("--- 自动查找最新的可用数据时间戳 ---")
    now_utc = datetime.now(timezone.utc) - timedelta(minutes=15)
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for i in range(20):
            check_time = now_utc - timedelta(minutes=i * 15)
            minute = (check_time.minute // 15) * 15
            dt_valid = check_time.replace(minute=minute, second=0, microsecond=0)
            timestamp_to_check = dt_valid.strftime("%Y%m%d%H%M%S")
            test_url = BASE_URL_TEMPLATE.format(timestamp=timestamp_to_check)
            try:
                response = session.get(test_url, timeout=15)
                if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                    print(f"成功找到可用时间戳: {timestamp_to_check}")
                    return timestamp_to_check
            except requests.exceptions.RequestException as e:
                print(f"查找时间戳时网络错误: {e}。可能服务器暂时不可用。")
                return None
            time.sleep(0.5)
    return None

def run_step(step_name, command):
    print(f"\n{'='*20}\n--- STEP: {step_name} ---\n{'='*20}")
    print(f"Executing: {' '.join(command)}")
    try:
        subprocess.run(command, check=True, text=True)
        print(f"--- STEP '{step_name}' COMPLETED SUCCESSFULLY ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ERROR: Step '{step_name}' failed with exit code {e.returncode}.")
        return False
    except KeyboardInterrupt:
        print(f"\n🛑 Workflow interrupted by user at step '{step_name}'.")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during step '{step_name}': {e}")
        return False

def run_workflow_for_timestamp(timestamp, args):
    """为单个时间戳执行完整的处理流程，并根据 args.keep_files 决定是否清理。"""
    print(f"\n>>> Starting workflow for timestamp: {timestamp} <<<")
    
    python_executable = sys.executable
    data_dir_args = ['-d', args.data_dir]
    
    cmd_download = [python_executable, 'download_stitch.py', '-t', timestamp] + data_dir_args
    cmd_adjust = [python_executable, 'adjust_padding.py', timestamp] + data_dir_args
    cmd_geotiff = [python_executable, 'create_geotiff.py', timestamp] + data_dir_args
    cmd_tiles = [python_executable, 'create_tiles.py', timestamp] + data_dir_args

    if args.keep_files:
        cmd_adjust.append('--keep-source')
        cmd_geotiff.append('--keep-source')
        print("\n*** Keep files mode is ON. Intermediate files will not be deleted. ***")

    steps = [
        ("1. DOWNLOAD & STITCH", cmd_download),
        ("2. ADJUST PADDING", cmd_adjust),
        ("3. CREATE GEOTIFF", cmd_geotiff),
        ("4. CREATE TILES", cmd_tiles)
    ]

    for name, command in steps:
        if not run_step(name, command):
            return False
    
    print(f"\n🎉🎉🎉 Workflow completed successfully for timestamp: {timestamp}! 🎉🎉🎉")
    return True

# --- 将单次任务逻辑封装成一个函数 ---
def run_scheduled_task(args):
    """
    执行单次计划任务：优先处理失败的，若无失败则处理最新的。
    """
    print(f"\n{'='*50}\n--- 定时任务启动 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n{'='*50}")
    
    target_timestamp = None
    is_retry_task = False
    
    # 1. 检查并优先处理失败队列
    failed_timestamps = read_failed_log(args.data_dir)
    if failed_timestamps:
        target_timestamp = failed_timestamps[0]
        print(f"--- 发现失败队列任务，尝试回补: {target_timestamp} ---")
        is_retry_task = True
    
    # 2. 如果没有失败任务，则查找最新任务
    if not target_timestamp:
        latest = find_latest_available_timestamp()
        if latest:
            target_timestamp = latest
        else:
            print("当前无可用最新数据。")
            
    # 3. 如果有任务目标，则执行工作流
    if target_timestamp:
        success = run_workflow_for_timestamp(target_timestamp, args)
        
        # 4. 根据执行结果更新失败日志
        failed_timestamps = read_failed_log(args.data_dir) # 重新读取以防万一
        if success:
            if is_retry_task and target_timestamp in failed_timestamps:
                print(f"--- 成功回补任务 {target_timestamp}，将其从失败队列中移除 ---")
                failed_timestamps.remove(target_timestamp)
                write_failed_log(args.data_dir, failed_timestamps)
        else: # 如果失败了
            if target_timestamp not in failed_timestamps:
                print(f"--- 工作流失败，将时间戳 {target_timestamp} 添加到失败队列 ---")
                failed_timestamps.append(target_timestamp)
                write_failed_log(args.data_dir, failed_timestamps)
    
    print(f"\n--- 本轮计划任务执行完毕 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

def main():
    parser = argparse.ArgumentParser(
        description="守护进程：定时获取、处理并切片风云4B卫星图像，并处理失败任务。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-t', '--timestamp', type=str, help="【单次运行模式】只处理这一个时间戳，然后退出。")
    parser.add_argument('-d', '--data-dir', type=str, default=DATA_DIR_DEFAULT, help=f"数据文件的基础目录。默认为 '{DATA_DIR_DEFAULT}'")
    parser.add_argument(
        "--keep-files", action="store_true", help="保留所有中间生成的 PNG 和 TIF 文件。"
    )
    
    args = parser.parse_args()
    os.makedirs(args.data_dir, exist_ok=True)
    
    # --- 单次运行模式---
    if args.timestamp:
        print("--- 启动单次运行模式 ---")
        run_workflow_for_timestamp(args.timestamp, args)
        sys.exit(0)

    # --- 守护进程模式 -> 更改为每日调度模式 ---
    print("--- 启动每日调度模式 ---")
    print("任务将在每天 12:00 自动运行。按 Ctrl+C 停止。")
    
    # 设置调度任务
    schedule.every().day.at("12:00").do(run_scheduled_task, args=args)
    
    # (可选) 为了方便测试，可以取消下面这行的注释，让程序启动时立即执行一次任务
    # print("为了方便测试，将立即执行一次任务...")
    # run_scheduled_task(args)

    # 启动调度循环
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，正在优雅地关闭调度器...")
            sys.exit(0)
        except Exception as e:
            print(f"\n调度器主循环发生未预料的严重错误: {e}")
            print("将等待60秒后重试...")
            time.sleep(60)

if __name__ == "__main__":
    main()