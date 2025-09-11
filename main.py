import os
import shutil
import time
import random
import requests
import argparse # 导入 argparse 模块
from PIL import Image
from tqdm import tqdm
from datetime import datetime, timedelta, timezone

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

# --- 其他函数 (无变动) ---
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

def download_tiles(session, timestamp, temp_dir):
    print(f"\n开始下载或验证时间戳为 {timestamp} 的卫星瓦片...")
    os.makedirs(temp_dir, exist_ok=True)
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    with tqdm(total=total_tiles, desc="处理进度") as pbar:
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
                if os.path.exists(filepath) and os.path.getsize(filepath) > MIN_IMAGE_SIZE_BYTES:
                    pbar.update(1)
                    pbar.set_postfix_str(f"瓦片({x},{y})已存在, 跳过")
                    continue
                url = BASE_URL_TEMPLATE.format(timestamp=timestamp, z=ZOOM_LEVEL, x=x, y=y)
                downloaded_successfully = False
                for attempt in range(3):
                    try:
                        response = session.get(url, timeout=15)
                        content_type = response.headers.get('Content-Type', '')
                        content_length = len(response.content)
                        if response.status_code == 200 and 'image' in content_type and content_length > MIN_IMAGE_SIZE_BYTES:
                            with open(filepath, 'wb') as f:
                                f.write(response.content)
                            downloaded_successfully = True
                            break
                        else:
                            pbar.set_postfix_str(f"瓦片({x},{y})无效(状态:{response.status_code},大小:{content_length}B),重试{attempt+1}")
                    except requests.exceptions.RequestException:
                        pbar.set_postfix_str(f"瓦片({x},{y})网络错误,重试{attempt+1}")
                    time.sleep(1)
                if not downloaded_successfully:
                    create_blank_tile(filepath)
                pbar.update(1)
                time.sleep(random.uniform(0.05, 0.2))
    print("\n所有瓦片下载/验证完成。")
    return True

def create_blank_tile(filepath, size=(256, 256), color='black'):
    try:
        img = Image.new('RGB', size, color)
        img.save(filepath)
    except Exception as e:
        print(f"创建空白图片 {filepath} 失败: {e}")

def stitch_tiles(timestamp, temp_dir):
    """
    拼接所有下载的瓦片。
    已根据正确的坐标系进行修正，解决图像旋转问题。
    """
    print("\n开始拼接瓦片 (已修正旋转问题)...")
    
    try:
        # 寻找一个有效的瓦片来确定尺寸
        sample_tile_path = next(os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith('.png'))
        with Image.open(sample_tile_path) as sample_tile:
            tile_width, tile_height = sample_tile.size
    except (StopIteration, FileNotFoundError, Image.UnidentifiedImageError) as e:
        print(f"错误: 无法确定瓦片尺寸，可能是所有瓦片都下载失败了。错误: {e}")
        return False

    # --- 核心修正 1: 交换画布的宽和高 ---
    # 宽度由 y 瓦片数量 (GRID_HEIGHT) 决定
    # 高度由 x 瓦片数量 (GRID_WIDTH) 决定
    full_width = tile_width * GRID_HEIGHT
    full_height = tile_height * GRID_WIDTH
    full_image = Image.new('RGB', (full_width, full_height))
    
    print(f"画布尺寸 (已修正): {full_width}x{full_height} 像素")
    
    # 循环遍历所有瓦片文件名
    # 外层循环遍历 x 坐标 (0 -> 12)
    # 内层循环遍历 y 坐标 (0 -> 14)
    for x in range(GRID_WIDTH):
        for y in range(GRID_HEIGHT):
            filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
            try:
                with Image.open(filepath) as tile:
                    # --- 核心修正 2: 交换粘贴坐标 ---
                    # 瓦片的 y 文件名坐标决定其水平位置
                    # 瓦片的 x 文件名坐标决定其垂直位置
                    paste_x = y * tile_width
                    paste_y = x * tile_height
                    full_image.paste(tile, (paste_x, paste_y))
            except (FileNotFoundError, Image.UnidentifiedImageError):
                # 警告信息可以保持不变
                print(f"警告: 瓦片 {filepath} 无效或不存在，该区域将留空。")

    output_filename = f"fy4b_full_disk_{timestamp}.png"
    full_image.save(output_filename)
    print(f"\n拼接完成！完整图像已保存为: {output_filename}")
    return True

# --- 修改后的 main 函数 ---
def main():
    # 1. 设置命令行参数解析器
    parser = argparse.ArgumentParser(
        description="下载并拼接风云4B全圆盘卫星图像。",
        formatter_class=argparse.RawTextHelpFormatter # 保持帮助信息格式
    )
    parser.add_argument(
        '-t', '--timestamp',
        type=str,
        help="指定要下载的时间戳，格式为 YYYYMMDDHHMMSS。\n"
            "例如: '20231027120000'\n"
            "如果未提供，脚本将自动查找最新的可用时间戳。"
    )
    args = parser.parse_args()

    # 2. 创建会话和决定使用哪个时间戳
    with requests.Session() as session:
        session.headers.update(HEADERS)
        
        target_timestamp = None
        if args.timestamp:
            # 如果用户提供了时间戳，进行基本格式验证
            if len(args.timestamp) == 14 and args.timestamp.isdigit():
                target_timestamp = args.timestamp
                print(f"使用指定的时间戳: {target_timestamp}")
            else:
                print(f"错误: 时间戳 '{args.timestamp}' 格式不正确。请使用 YYYYMMDDHHMMSS 格式。")
                return
        else:
            # 如果用户未提供，则自动查找
            target_timestamp = find_latest_available_timestamp(session)

        # 3. 检查是否成功获取到时间戳
        if not target_timestamp:
            print("错误：无法确定有效的时间戳以下载数据。脚本退出。")
            return
        
        # 后续逻辑不变，使用 target_timestamp
        temp_dir = f"temp_tiles_{target_timestamp}"
        try:
            download_success = download_tiles(session, target_timestamp, temp_dir)
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