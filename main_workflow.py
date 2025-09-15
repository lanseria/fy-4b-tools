#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# --- 配置区 (无变动) ---
BASE_URL_TEMPLATE = "http://rsapp.nsmc.org.cn/swapQuery/public/tileServer/getTile/fy-4b/full_disk/NatureColor_NoLit/{timestamp}/jpg/0/0/0.png"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
DATA_DIR_DEFAULT = './data'
FAILED_LOG_FILENAME = 'failed_timestamps.json'

# --- 辅助函数和核心函数 (无变动) ---
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
        # 恢复为不捕获输出，让子脚本的打印信息实时显示
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

# --- 核心改动：修改 run_workflow_for_timestamp 函数 ---
def run_workflow_for_timestamp(timestamp, args):
    """为单个时间戳执行完整的处理流程，并根据 args.keep_files 决定是否清理。"""
    print(f"\n>>> Starting workflow for timestamp: {timestamp} <<<")
    
    python_executable = sys.executable
    data_dir_args = ['-d', args.data_dir]
    
    # 构建基础命令
    cmd_download = [python_executable, 'download_stitch.py', '-t', timestamp] + data_dir_args
    cmd_adjust = [python_executable, 'adjust_padding.py', timestamp] + data_dir_args
    cmd_geotiff = [python_executable, 'create_geotiff.py', timestamp] + data_dir_args
    cmd_tiles = [python_executable, 'create_tiles.py', timestamp] + data_dir_args

    # 如果 --keep-files 标志被设置，则向子脚本传递 --keep-source 指令
    if args.keep_files:
        cmd_adjust.append('--keep-source')
        cmd_geotiff.append('--keep-source')
        print("\n*** Keep files mode is ON. Intermediate files will not be deleted. ***")

    # 定义最终的工作流步骤
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

# --- 核心改动：修改 main 函数的 argparse ---
def main():
    parser = argparse.ArgumentParser(
        description="守护进程：定时获取、处理并切片风云4B卫星图像，并处理失败任务。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-t', '--timestamp', type=str, help="【单次运行模式】只处理这一个时间戳，然后退出。")
    parser.add_argument('-d', '--data-dir', type=str, default=DATA_DIR_DEFAULT, help=f"数据文件的基础目录。默认为 '{DATA_DIR_DEFAULT}'")
    
    # --- 新增的参数 ---
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="保留所有中间生成的 PNG 和 TIF 文件，而不是在处理后删除它们。"
    )
    
    args = parser.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    
    if args.timestamp:
        print("--- 启动单次运行模式 ---")
        run_workflow_for_timestamp(args.timestamp, args)
        sys.exit(0)

    # --- 守护进程模式 (无变动) ---
    print("--- 启动守护进程模式 (每15分钟检查一次) ---")
    print("按 Ctrl+C 停止。")
    
    processed_this_cycle = set()
    while True:
        try:
            target_timestamp = None
            is_retry_task = False
            failed_timestamps = read_failed_log(args.data_dir)
            if failed_timestamps:
                target_timestamp = failed_timestamps[0]
                if target_timestamp in processed_this_cycle:
                    print(f"时间戳 {target_timestamp} 在本轮已尝试失败，跳过以避免死循环。")
                    target_timestamp = None
                else:
                    print(f"--- 发现失败队列任务，尝试回补: {target_timestamp} ---")
                    is_retry_task = True
            
            if not target_timestamp:
                latest = find_latest_available_timestamp()
                if latest and latest not in processed_this_cycle:
                    target_timestamp = latest
                else:
                    if not latest: print("当前无可用最新数据。")
                    else: print(f"最新时间戳 {latest} 在本轮已处理过，跳过。")
            
            if target_timestamp:
                processed_this_cycle.add(target_timestamp)
                success = run_workflow_for_timestamp(target_timestamp, args)
                
                failed_timestamps = read_failed_log(args.data_dir)
                if success:
                    if is_retry_task:
                        print(f"--- 成功回补任务 {target_timestamp}，将其从失败队列中移除 ---")
                        if target_timestamp in failed_timestamps:
                            failed_timestamps.remove(target_timestamp)
                            write_failed_log(args.data_dir, failed_timestamps)
                else:
                    if target_timestamp not in failed_timestamps:
                        print(f"--- 工作流失败，将时间戳 {target_timestamp} 添加到失败队列 ---")
                        failed_timestamps.append(target_timestamp)
                        write_failed_log(args.data_dir, failed_timestamps)
            
            print("\n--- 本轮检查结束，等待15分钟... ---")
            time.sleep(15 * 60)
            processed_this_cycle.clear()
            
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，正在优雅地关闭守护进程...")
            sys.exit(0)
        except Exception as e:
            print(f"\n发生未预料的严重错误: {e}")
            print("将等待15分钟后重试...")
            time.sleep(15 * 60)

if __name__ == "__main__":
    main()