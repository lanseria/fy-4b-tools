#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# --- 配置区 ---
BASE_URL_TEMPLATE = "http://rsapp.nsmc.org.cn/swapQuery/public/tileServer/getTile/fy-4b/full_disk/NatureColor_NoLit/{timestamp}/jpg/0/0/0.png"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
DATA_DIR_DEFAULT = './data'
FAILED_LOG_FILENAME = 'failed_timestamps.json'

# --- 辅助函数：读写失败日志 ---
def read_failed_log(data_dir):
    """读取失败的时间戳队列。"""
    log_path = os.path.join(data_dir, FAILED_LOG_FILENAME)
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def write_failed_log(data_dir, timestamps):
    """写入失败的时间戳队列。"""
    log_path = os.path.join(data_dir, FAILED_LOG_FILENAME)
    with open(log_path, 'w') as f:
        json.dump(timestamps, f, indent=2)

# --- 核心函数 ---
def find_latest_available_timestamp():
    """查找最新的可用数据时间戳。如果服务器无响应，则返回 None。"""
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
                return None # 关键：返回None表示暂时无法连接
            time.sleep(0.5)
    return None

def run_step(step_name, command):
    """执行一个工作流步骤，并检查其是否成功。"""
    print(f"\n{'='*20}\n--- STEP: {step_name} ---\n{'='*20}")
    print(f"Executing: {' '.join(command)}")
    try:
        subprocess.run(command, check=True, text=True, capture_output=True) # capture_output 避免打印过多信息
        print(f"--- STEP '{step_name}' COMPLETED SUCCESSFULLY ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ERROR: Step '{step_name}' failed with exit code {e.returncode}.")
        print("--- STDOUT ---")
        print(e.stdout)
        print("--- STDERR ---")
        print(e.stderr)
        return False
    except KeyboardInterrupt:
        print(f"\n🛑 Workflow interrupted by user at step '{step_name}'.")
        raise # 将中断传递出去以停止整个脚本
    except Exception as e:
        print(f"An unexpected error occurred during step '{step_name}': {e}")
        return False


def run_workflow_for_timestamp(timestamp, args):
    """为单个时间戳执行完整的处理流程。"""
    print(f"\n>>> Starting workflow for timestamp: {timestamp} <<<")
    python_executable = sys.executable
    steps = [
        ("1. DOWNLOAD & STITCH", [
            python_executable, 'download_stitch.py', '-t', timestamp, '-d', args.data_dir, '-c', str(args.concurrency)
        ]),
        ("2. ADJUST PADDING", [
            python_executable, 'adjust_padding.py', timestamp, '-d', args.data_dir, '--crop-x', str(args.crop_x), '--crop-y', str(args.crop_y)
        ]),
        ("3. CREATE GEOTIFF", [
            python_executable, 'create_geotiff.py', timestamp, '-d', args.data_dir
        ]),
        ("4. CREATE TILES", [
            python_executable, 'create_tiles.py', timestamp, '-d', args.data_dir, '-z', args.zoom
        ])
    ]

    for name, command in steps:
        if not run_step(name, command):
            return False # 任何一步失败，则整个工作流失败
    
    print(f"\n🎉🎉🎉 Workflow completed successfully for timestamp: {timestamp}! 🎉🎉🎉")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="守护进程：定时获取、处理并切片风云4B卫星图像，并处理失败任务。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # 所有参数现在都是可选的，因为守护进程模式是默认的
    parser.add_argument('-t', '--timestamp', type=str, help="【单次运行模式】只处理这一个时间戳，然后退出。")
    parser.add_argument('-d', '--data-dir', type=str, default=DATA_DIR_DEFAULT, help=f"数据文件的基础目录。默认为 '{DATA_DIR_DEFAULT}'")
    parser.add_argument('--concurrency', type=int, default=10, help="下载并发数。默认: 10")
    parser.add_argument('--crop-x', type=int, default=-135, help="X轴边距调整。默认: -135")
    parser.add_argument('--crop-y', type=int, default=-162, help="Y轴边距调整。默认: -162")
    parser.add_argument('--zoom', type=str, default='1-6', help="瓦片缩放级别。默认: '1-6'")
    args = parser.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    
    # --- 单次运行模式 ---
    if args.timestamp:
        print("--- 启动单次运行模式 ---")
        run_workflow_for_timestamp(args.timestamp, args)
        sys.exit(0)

    # --- 守护进程模式 ---
    print("--- 启动守护进程模式 (每15分钟检查一次) ---")
    print("按 Ctrl+C 停止。")
    
    processed_this_cycle = set() # 跟踪本轮已尝试处理的时间戳，避免重复处理
    
    while True:
        try:
            target_timestamp = None
            is_retry_task = False
            
            # 1. 优先处理失败队列
            failed_timestamps = read_failed_log(args.data_dir)
            if failed_timestamps:
                target_timestamp = failed_timestamps[0] # 取最旧的一个任务
                if target_timestamp in processed_this_cycle:
                    print(f"时间戳 {target_timestamp} 在本轮已尝试失败，跳过以避免死循环。")
                    target_timestamp = None
                else:
                    print(f"--- 发现失败队列任务，尝试回补: {target_timestamp} ---")
                    is_retry_task = True

            # 2. 如果失败队列为空，则获取最新数据
            if not target_timestamp:
                latest = find_latest_available_timestamp()
                if latest and latest not in processed_this_cycle:
                    target_timestamp = latest
                else:
                    if not latest:
                        print("当前无可用最新数据。")
                    else:
                        print(f"最新时间戳 {latest} 在本轮已处理过，跳过。")
            
            # 3. 执行工作流
            if target_timestamp:
                processed_this_cycle.add(target_timestamp) # 标记为本轮已尝试
                success = run_workflow_for_timestamp(target_timestamp, args)
                
                # 4. 根据结果更新失败队列
                failed_timestamps = read_failed_log(args.data_dir) # 重新读取以防其他进程修改
                if success:
                    if is_retry_task:
                        print(f"--- 成功回补任务 {target_timestamp}，将其从失败队列中移除 ---")
                        if target_timestamp in failed_timestamps:
                            failed_timestamps.remove(target_timestamp)
                            write_failed_log(args.data_dir, failed_timestamps)
                else: # 如果处理失败
                    if target_timestamp not in failed_timestamps:
                        print(f"--- 工作流失败，将时间戳 {target_timestamp} 添加到失败队列 ---")
                        failed_timestamps.append(target_timestamp)
                        write_failed_log(args.data_dir, failed_timestamps)

            # 5. 等待下一个周期
            print("\n--- 本轮检查结束，等待15分钟... ---")
            time.sleep(15 * 60)
            processed_this_cycle.clear() # 新的一轮循环，清空标记
            
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，正在优雅地关闭守护进程...")
            sys.exit(0)
        except Exception as e:
            print(f"\n发生未预料的严重错误: {e}")
            print("将等待15分钟后重试...")
            time.sleep(15 * 60)

if __name__ == "__main__":
    main()