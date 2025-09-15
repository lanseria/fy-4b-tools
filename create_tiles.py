import os
import argparse
import subprocess
import shutil
import sys
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

def process_and_tile_by_timestamp(timestamp_str, data_dir, zoom_range='1-7', gdal2tiles_path_arg=None):
    """
    根据时间戳自动查找GeoTIFF，切片为XYZ标准的瓦片，并更新timestamps.json。
    """
    # --- 路径和文件名推断 ---
    print(f"--- Processing timestamp: {timestamp_str} ---")
    input_filename = f"fy4b_full_disk_{timestamp_str}_adjusted_mercator.tif"
    input_geotiff = os.path.join(data_dir, input_filename)
    if not os.path.exists(input_geotiff):
        print(f"\nError: Input GeoTIFF file not found at '{input_geotiff}'")
        sys.exit(1)
        
    # --- 时间戳转换与输出目录设置 ---
    try:
        dt_object = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        unix_timestamp = int(dt_object.timestamp())
    except ValueError:
        print(f"Error: Invalid timestamp format '{timestamp_str}'. Please use YYYYMMDDHHMMSS.")
        sys.exit(1)
    base_output_dir = os.path.join(data_dir, 'satellite_tiles')
    os.makedirs(base_output_dir, exist_ok=True)
    tile_output_dir = os.path.join(base_output_dir, str(unix_timestamp))
    # 如果目录已存在，先清空，确保是全新的切片
    if os.path.exists(tile_output_dir):
        shutil.rmtree(tile_output_dir)
    os.makedirs(tile_output_dir, exist_ok=True)
    print(f"Input GeoTIFF: {input_geotiff}")
    print(f"Output Tile Directory: {tile_output_dir}")

    # --- 更新 timestamps.json ---
    json_path = os.path.join(base_output_dir, 'timestamps.json')
    timestamps = []
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r') as f: timestamps = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): timestamps = []
    if unix_timestamp not in timestamps:
        timestamps.append(unix_timestamp)
        timestamps.sort()
        with open(json_path, 'w') as f: json.dump(timestamps, f, indent=2)
        print(f"Added timestamp {unix_timestamp} to 'timestamps.json'.")
    else:
        print(f"Timestamp {unix_timestamp} already exists in 'timestamps.json'.")

    # --- gdal2tiles.py 路径查找逻辑 ---
    print("\n--- Locating gdal2tiles.py ---")
    gdal2tiles_path = None
    if gdal2tiles_path_arg:
        if os.path.isfile(gdal2tiles_path_arg): gdal2tiles_path = gdal2tiles_path_arg
        else:
            print(f"\nError: Path provided via --gdal2tiles-path is not a valid file: {gdal2tiles_path_arg}")
            sys.exit(1)
    if not gdal2tiles_path:
        env_path = os.getenv('GDAL2TILES_PATH')
        if env_path:
            if os.path.isfile(env_path): gdal2tiles_path = env_path
            else: print(f"\nWarning: Path in GDAL2TILES_PATH is not a valid file: {env_path}. Falling back to system PATH.")
    if not gdal2tiles_path:
        gdal2tiles_path = shutil.which('gdal2tiles.py')
    if not gdal2tiles_path:
        print("\nError: Could not locate 'gdal2tiles.py'.")
        sys.exit(1)
    print(f"Successfully located gdal2tiles.py at: {gdal2tiles_path}")
        
    # --- 执行 gdal2tiles.py ---
    try: cpu_cores = os.cpu_count()
    except NotImplementedError: cpu_cores = 1
    
    # --- 核心修正点 1: 在命令中添加 --xyz 标志 ---
    command = [
        sys.executable, gdal2tiles_path,
        '--profile', 'mercator',
        '--xyz',  # <--- 添加此标志以使用 XYZ 瓦片标准
        '--zoom', zoom_range,
        '--processes', str(cpu_cores),
        '--webviewer', 'leaflet',
        '--title', f'FY-4B View - {timestamp_str}',
        input_geotiff,
        tile_output_dir
    ]
    
    print("\n--- Starting the tiling process (XYZ standard) ---")
    print(f"Executing command:\n{' '.join(command)}\n")
    try:
        my_env = os.environ.copy()
        my_env["PYTHONWARNINGS"] = "ignore:FutureWarning"
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=my_env)
        for line in iter(process.stdout.readline, ''): print(line, end='')
        process.wait()
        if process.returncode == 0: print("\n--- Tiling process completed successfully! ---")
        else: print(f"\nError: gdal2tiles.py exited with error code {process.returncode}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Creates map tiles from a georeferenced TIFF file based on a timestamp."
    )
    parser.add_argument("timestamp", type=str, help="The timestamp of the data to process, in 'YYYYMMDDHHMMSS' format.")
    parser.add_argument("-d", "--data-dir", type=str, default="data", help="The base directory for input TIFFs and output tiles. Default: 'data'")
    
    # --- 核心修正点 2: 修改 zoom 的默认值和帮助文本 ---
    parser.add_argument(
        "-z", "--zoom",
        type=str,
        default="1-7", # <--- 修改默认值
        help="Zoom levels to generate, in 'min-max' format. Default: '1-7'." # <--- 更新帮助文本
    )
    
    parser.add_argument(
        "--gdal2tiles-path",
        type=str,
        help="Explicit path to gdal2tiles.py. Overrides environment variables and system PATH."
    )
    
    args = parser.parse_args()
    
    process_and_tile_by_timestamp(
        args.timestamp, 
        args.data_dir, 
        zoom_range=args.zoom, 
        gdal2tiles_path_arg=args.gdal2tiles_path
    )
    
    print(f"\n✅ All done! Check the output in '{os.path.join(args.data_dir, 'satellite_tiles')}' directory.")