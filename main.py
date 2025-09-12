import os
import shutil
import time
import random
import requests
import argparse
from PIL import Image
from tqdm import tqdm
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置区 (无变动) ---
BASE_URL_TEMPLATE = "http://rsapp.nsmc.org.cn/swapQuery/public/tileServer/getTile/fy-4b/full_disk/NatureColor_NoLit/{timestamp}/jpg/{z}/{x}/{y}.png"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Referer': 'http://rsapp.nsmc.org.cn/geofy/',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
}
ZOOM_LEVEL = 4
GRID_WIDTH = 16
GRID_HEIGHT = 16
MIN_IMAGE_SIZE_BYTES = 1024

# --- 查找时间戳函数 (无变动) ---
def find_latest_available_timestamp(session):
    print("正在查找最新的可用数据时间戳...")
    now_utc = datetime.now(timezone.utc) - timedelta(minutes=15)
    for i in range(20):
        check_time = now_utc - timedelta(minutes=i * 15)
        minute = (check_time.minute // 15) * 15
        dt_valid = check_time.replace(minute=minute, second=0, microsecond=0)
        timestamp_to_check = dt_valid.strftime("%Y%m%d%H%M%S")
        test_url = BASE_URL_TEMPLATE.format(timestamp=timestamp_to_check, z=0, x=0, y=0)
        try:
            response = session.get(test_url, timeout=10)
            content_type = response.headers.get('Content-Type', '')
            if response.status_code == 200 and 'image' in content_type and len(response.content) > 500:
                print(f"成功找到可用时间戳: {timestamp_to_check}")
                return timestamp_to_check
            else:
                print(f"时间戳 {timestamp_to_check} 无效 (状态: {response.status_code}, 类型: {content_type}, 大小: {len(response.content)}B)，继续尝试...")
        except requests.exceptions.RequestException as e:
            print(f"时间戳 {timestamp_to_check} 网络请求失败: {e}，继续尝试...")
        time.sleep(0.5)
    return None

# --- 新的、用于并发的单瓦片下载函数 ---
def download_single_tile(session, timestamp, temp_dir, x, y):
    """下载单个瓦片，包含检查、下载、重试逻辑。"""
    filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")

    # 1. 检查文件是否已存在且有效
    if os.path.exists(filepath) and os.path.getsize(filepath) > MIN_IMAGE_SIZE_BYTES:
        return f"Skipped ({x},{y})"

    # 2. 如果不存在，则下载
    url = BASE_URL_TEMPLATE.format(timestamp=timestamp, z=ZOOM_LEVEL, x=x, y=y)
    for attempt in range(3):
        try:
            response = session.get(url, timeout=15)
            content_type = response.headers.get('Content-Type', '')
            content_length = len(response.content)
            if response.status_code == 200 and 'image' in content_type and content_length > MIN_IMAGE_SIZE_BYTES:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return f"Downloaded ({x},{y})" # 成功
        except requests.exceptions.RequestException:
            pass # 发生网络错误，继续重试
        time.sleep(1)
    
    # 3. 如果所有重试都失败，创建空白瓦片
    create_blank_tile(filepath)
    return f"Failed ({x},{y})"

# --- 重构后的并发下载函数 ---
def download_tiles(session, timestamp, temp_dir, concurrency):
    """使用线程池并发下载所有瓦片。"""
    print(f"\n开始使用 {concurrency} 个并发线程下载或验证时间戳为 {timestamp} 的卫星瓦片...")
    os.makedirs(temp_dir, exist_ok=True)

    # 创建所有任务的坐标列表
    tasks = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH)]

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # 提交所有任务到线程池
        futures = [executor.submit(download_single_tile, session, timestamp, temp_dir, x, y) for x, y in tasks]
        
        # 使用 tqdm 和 as_completed 来实时更新进度条
        with tqdm(total=len(tasks), desc="下载进度") as pbar:
            for future in as_completed(futures):
                # 每当一个任务完成（无论成功失败），进度条就更新一格
                pbar.update(1)
                # 可选：可以获取结果并打印，用于调试
                # result = future.result()
                # pbar.set_postfix_str(result)
    
    print("\n所有瓦片下载/验证完成。")
    return True

# --- 创建空白瓦片和拼接函数 (无变动) ---
def create_blank_tile(filepath, size=(256, 256), color='black'):
    try:
        img = Image.new('RGB', size, color)
        img.save(filepath)
    except Exception as e:
        print(f"创建空白图片 {filepath} 失败: {e}")

def stitch_tiles(timestamp, temp_dir):
    print("\n开始拼接瓦片 (已修正旋转问题)...")
    try:
        sample_tile_path = next(os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith('.png'))
        with Image.open(sample_tile_path) as sample_tile:
            tile_width, tile_height = sample_tile.size
    except (StopIteration, FileNotFoundError, Image.UnidentifiedImageError) as e:
        print(f"错误: 无法确定瓦片尺寸，可能是所有瓦片都下载失败了。错误: {e}")
        return False
    full_width = tile_width * GRID_HEIGHT
    full_height = tile_height * GRID_WIDTH
    full_image = Image.new('RGB', (full_width, full_height))
    print(f"画布尺寸 (已修正): {full_width}x{full_height} 像素")
    for x in range(GRID_WIDTH):
        for y in range(GRID_HEIGHT):
            filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
            try:
                with Image.open(filepath) as tile:
                    paste_x = y * tile_width
                    paste_y = x * tile_height
                    full_image.paste(tile, (paste_x, paste_y))
            except (FileNotFoundError, Image.UnidentifiedImageError):
                print(f"警告: 瓦片 {filepath} 无效或不存在，该区域将留空。")
    output_filename = f"fy4b_full_disk_{timestamp}.png"
    Image.MAX_IMAGE_PIXELS = None # 确保可以保存大图
    full_image.save(output_filename)
    print(f"\n拼接完成！完整图像已保存为: {output_filename}")
    return True

# --- 修改后的 main 函数 ---
def main():
    parser = argparse.ArgumentParser(
        description="下载并拼接风云4B全圆盘卫星图像。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-t', '--timestamp',
        type=str,
        help="指定要下载的时间戳，格式为 YYYYMMDDHHMMSS。\n"
             "如果未提供，将自动查找最新时间戳。"
    )
    # --- 新增并发参数 ---
    parser.add_argument(
        '-c', '--concurrency',
        type=int,
        default=10,
        help="并发下载线程数。默认为 10。"
    )
    args = parser.parse_args()

    with requests.Session() as session:
        session.headers.update(HEADERS)
        
        target_timestamp = args.timestamp
        if not target_timestamp:
            target_timestamp = find_latest_available_timestamp(session)
        elif not (len(target_timestamp) == 14 and target_timestamp.isdigit()):
            print(f"错误: 时间戳 '{target_timestamp}' 格式不正确。请使用 YYYYMMDDHHMMSS 格式。")
            return
        
        if not target_timestamp:
            print("错误：无法确定有效的时间戳以下载数据。脚本退出。")
            return
        
        print(f"将使用时间戳: {target_timestamp}")
        
        temp_dir = f"temp_tiles_{target_timestamp}"
        try:
            # 将并发数传递给 download_tiles 函数
            download_success = download_tiles(session, target_timestamp, temp_dir, args.concurrency)
            if not download_success: return

            stitch_success = stitch_tiles(target_timestamp, temp_dir)
            if not stitch_success: return
            
            print("\n任务成功完成！")
            choice = input(f"是否删除临时文件夹 '{temp_dir}'? (y/n, 默认 n): ").lower()
            if choice == 'y':
                shutil.rmtree(temp_dir)
                print(f"临时文件夹 '{temp_dir}' 已删除。")
            else:
                print(f"临时文件夹 '{temp_dir}' 已保留。")
        except Exception as e:
            print(f"\n脚本执行过程中发生未预料的错误: {e}")
            print(f"临时文件已保留在 '{temp_dir}' 文件夹中，以便进行问题排查。")

if __name__ == "__main__":
    main()