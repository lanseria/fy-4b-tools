import os
import shutil
import time
import requests
import argparse
from PIL import Image
from tqdm import tqdm
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

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
Image.MAX_IMAGE_PIXELS = None

def download_single_tile(session, timestamp, temp_dir, x, y):
    filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
    if os.path.exists(filepath) and os.path.getsize(filepath) > MIN_IMAGE_SIZE_BYTES:
        return f"Skipped ({x},{y})"
    url = BASE_URL_TEMPLATE.format(timestamp=timestamp, z=ZOOM_LEVEL, x=x, y=y)
    for attempt in range(3):
        try:
            response = session.get(url, timeout=15)
            content_type = response.headers.get('Content-Type', '')
            content_length = len(response.content)
            if response.status_code == 200 and 'image' in content_type and content_length > MIN_IMAGE_SIZE_BYTES:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return f"Downloaded ({x},{y})"
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    create_blank_tile(filepath)
    return f"Failed ({x},{y})"

def download_tiles(session, timestamp, temp_dir, concurrency):
    print(f"\n开始使用 {concurrency} 个并发线程下载或验证时间戳为 {timestamp} 的卫星瓦片...")
    os.makedirs(temp_dir, exist_ok=True)
    tasks = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH)]
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(download_single_tile, session, timestamp, temp_dir, x, y) for x, y in tasks]
        with tqdm(total=len(tasks), desc="下载进度") as pbar:
            for future in as_completed(futures):
                pbar.update(1)
    print("\n所有瓦片下载/验证完成。")
    return True

def create_blank_tile(filepath, size=(256, 256), color='black'):
    try:
        img = Image.new('RGB', size, color)
        img.save(filepath)
    except Exception as e:
        print(f"创建空白图片 {filepath} 失败: {e}")

def stitch_tiles(timestamp, temp_dir, data_dir):
    print("\n开始拼接瓦片...")
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
    print(f"画布尺寸: {full_width}x{full_height} 像素")
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
    output_filepath = os.path.join(data_dir, output_filename)
    full_image.save(output_filepath)
    print(f"\n拼接完成！完整图像已保存为: {output_filepath}")
    return True
def main():
    load_dotenv() # 加载 .env 文件
    parser = argparse.ArgumentParser(
        description="下载并拼接风云4B全圆盘卫星图像。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # --- 核心改动：将 timestamp 设为必需参数 ---
    parser.add_argument(
        '-t', '--timestamp',
        type=str,
        required=True, # 设为必需
        help="必须提供要下载的时间戳，格式为 YYYYMMDDHHMMSS。"
    )
    parser.add_argument(
        '-d', '--data-dir', type=str, default='./data', help="所有输出文件（临时瓦片、最终图像）的基础目录。默认为 './data'"
    )
    args = parser.parse_args()

    # --- 核心改动：从环境变量读取配置 ---
    concurrency = int(os.getenv('DOWNLOAD_CONCURRENCY', 10)) # 默认值为 10

    os.makedirs(args.data_dir, exist_ok=True)

    with requests.Session() as session:
        session.headers.update(HEADERS)
        
        target_timestamp = args.timestamp
        if not (len(target_timestamp) == 14 and target_timestamp.isdigit()):
            print(f"错误: 时间戳 '{target_timestamp}' 格式不正确。")
            return
        
        print(f"将使用时间戳: {target_timestamp}")
        
        temp_base_dir = os.path.join(args.data_dir, 'temp_tiles')
        temp_dir_for_timestamp = os.path.join(temp_base_dir, target_timestamp)
        
        try:
            download_success = download_tiles(session, target_timestamp, temp_dir_for_timestamp, concurrency)
            if not download_success: return

            stitch_success = stitch_tiles(target_timestamp, temp_dir_for_timestamp, args.data_dir)
            if not stitch_success: return
            
            print("\n任务成功完成！")
            shutil.rmtree(temp_dir_for_timestamp)
            print(f"临时文件夹 '{temp_dir_for_timestamp}' 已自动删除。")

        except Exception as e:
            print(f"\n脚本执行过程中发生未预料的错误: {e}")
            print(f"临时文件已保留在 '{temp_dir_for_timestamp}' 文件夹中，以便进行问题排查。")

if __name__ == "__main__":
    main()