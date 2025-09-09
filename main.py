import os
import shutil
import time
import requests
from PIL import Image
from tqdm import tqdm
from datetime import datetime, timedelta, timezone

# --- 配置区 ---

BASE_URL_TEMPLATE = "http://rsapp.nsmc.org.cn/swapQuery/public/tileServer/getTile/fy-4b/full_disk/NatureColor_NoLit/{timestamp}/jpg/{z}/{x}/{y}.png"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
}
ZOOM_LEVEL = 4
GRID_WIDTH = 13
GRID_HEIGHT = 15

# --- 脚本主逻辑 ---

def find_latest_available_timestamp():
    """从当前真实 UTC 时间开始，向前查找最近的可用数据时间戳。"""
    print("正在查找最新的可用数据时间戳...")
    now_utc = datetime.now(timezone.utc)
    # 适当回退几分钟，给数据传输留出延迟时间
    now_utc -= timedelta(minutes=15)

    for i in range(20): # 增加尝试范围，最多回溯 20 * 15 = 300 分钟（5小时）
        check_time = now_utc - timedelta(minutes=i * 15)
        minute = (check_time.minute // 15) * 15
        dt_valid = check_time.replace(minute=minute, second=0, microsecond=0)
        timestamp_to_check = dt_valid.strftime("%Y%m%d%H%M%S")
        
        test_url = BASE_URL_TEMPLATE.format(timestamp=timestamp_to_check, z=0, x=0, y=0) # 使用 z=0 瓦片测试，请求量最小
        try:
            response = requests.get(test_url, headers=HEADERS, timeout=10)
            content_type = response.headers.get('Content-Type', '')
            if response.status_code == 200 and 'image' in content_type:
                print(f"成功找到可用时间戳: {timestamp_to_check}")
                return timestamp_to_check
            else:
                print(f"时间戳 {timestamp_to_check} 无效 (状态: {response.status_code}, 类型: {content_type})，继续尝试...")
        except requests.exceptions.RequestException as e:
            print(f"时间戳 {timestamp_to_check} 网络请求失败: {e}，继续尝试...")
        time.sleep(0.5)
    return None

def download_tiles(timestamp, temp_dir):
    """根据给定的时间戳，下载所有瓦片到指定的临时文件夹"""
    print(f"\n开始下载时间戳为 {timestamp} 的卫星瓦片...")
    os.makedirs(temp_dir, exist_ok=True)
    
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    
    with tqdm(total=total_tiles, desc="下载进度") as pbar:
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                url = BASE_URL_TEMPLATE.format(timestamp=timestamp, z=ZOOM_LEVEL, x=x, y=y)
                filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
                
                retries = 3
                for attempt in range(retries):
                    try:
                        response = requests.get(url, headers=HEADERS, stream=True, timeout=15)
                        content_type = response.headers.get('Content-Type', '')
                        
                        if response.status_code == 200 and 'image' in content_type:
                            with open(filepath, 'wb') as f:
                                shutil.copyfileobj(response.raw, f)
                            break
                        else:
                            # 即使是200，如果不是图片也要算作失败
                            status_info = f"状态: {response.status_code}, 类型: {content_type}"
                            if attempt < retries - 1:
                                pbar.set_postfix_str(f"瓦片({x},{y})获取失败 ({status_info}), 重试中...")
                            else:
                                pbar.set_postfix_str(f"瓦片({x},{y})最终失败 ({status_info})")
                    except requests.exceptions.RequestException as e:
                        if attempt < retries - 1:
                            pbar.set_postfix_str(f"瓦片({x},{y})网络错误, 重试中...")
                        else:
                             pbar.set_postfix_str(f"瓦片({x},{y})网络最终失败")

                    time.sleep(1)
                else: # 如果重试次数用尽
                    create_blank_tile(filepath)
                
                pbar.update(1)
    print("\n所有瓦片下载尝试完成。")
    return True

def create_blank_tile(filepath, size=(256, 256), color='black'):
    """如果瓦片下载失败，创建一个黑色空白图片代替"""
    try:
        img = Image.new('RGB', size, color)
        img.save(filepath)
    except Exception as e:
        print(f"创建空白图片 {filepath} 失败: {e}")

def stitch_tiles(timestamp, temp_dir):
    """拼接所有下载的瓦片"""
    print("\n开始拼接瓦片...")
    
    try:
        # 寻找一个有效的瓦片来确定尺寸
        sample_tile_path = None
        for f in os.listdir(temp_dir):
            if f.endswith('.png'):
                try:
                    full_path = os.path.join(temp_dir, f)
                    with Image.open(full_path) as img:
                        img.verify() # 验证图片数据是否完整
                    sample_tile_path = full_path
                    break # 找到一个好的就够了
                except (IOError, SyntaxError, Image.UnidentifiedImageError):
                    continue # 这个文件坏了，找下一个

        if not sample_tile_path:
            print("错误: 临时文件夹中找不到任何有效的瓦片图片，无法拼接。")
            return False

        with Image.open(sample_tile_path) as sample_tile:
            tile_width, tile_height = sample_tile.size
    except Exception as e:
        print(f"错误: 确定瓦片尺寸时出错: {e}")
        return False

    full_width = tile_width * GRID_WIDTH
    full_height = tile_height * GRID_HEIGHT
    full_image = Image.new('RGB', (full_width, full_height))
    
    print(f"画布尺寸: {full_width}x{full_height} 像素")
    
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            filepath = os.path.join(temp_dir, f"tile_{x}_{y}.png")
            try:
                with Image.open(filepath) as tile:
                    full_image.paste(tile, (x * tile_width, y * tile_height))
            except FileNotFoundError:
                print(f"警告: 找不到瓦片 {filepath}，该区域将留空。")
            except Image.UnidentifiedImageError:
                print(f"警告: 瓦片 {filepath} 已损坏，无法识别，该区域将留空。")

    output_filename = f"fy4b_full_disk_{timestamp}.png"
    full_image.save(output_filename)
    print(f"\n拼接完成！完整图像已保存为: {output_filename}")
    return True

def main():
    latest_timestamp = find_latest_available_timestamp()
    
    if not latest_timestamp:
        print("错误：在指定范围内未能找到任何可用的数据。请检查网络或稍后再试。")
        return

    # 创建一个带时间戳的临时文件夹
    temp_dir = f"temp_tiles_{latest_timestamp}"
    
    try:
        # 下载和拼接
        download_success = download_tiles(latest_timestamp, temp_dir)
        if not download_success:
            print("下载过程出现问题，拼接中止。")
            return

        stitch_success = stitch_tiles(latest_timestamp, temp_dir)
        if not stitch_success:
            print("拼接过程出现问题。")
            return
            
        # 只有完全成功才提示删除
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