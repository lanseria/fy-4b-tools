import os
import argparse
import subprocess
import shutil
import sys

def create_map_tiles(input_geotiff, output_dir, zoom_range='1-6'):
    """
    使用 GDAL 的 gdal2tiles.py 工具将 GeoTIFF 文件切片成地图瓦片。

    Args:
        input_geotiff (str): 输入的、带有 Web 墨卡托投影的 GeoTIFF 文件路径。
        output_dir (str): 用于存放所有瓦片和预览文件的输出文件夹路径。
        zoom_range (str): 要生成的缩放级别范围，格式为 'min-max' (例如 '1-6')。
    """
    print("--- Step 1: Checking for gdal2tiles.py command ---")
    
    # 检查 gdal2tiles.py 命令是否存在于系统的 PATH 中
    gdal2tiles_path = shutil.which('gdal2tiles.py')
    if not gdal2tiles_path:
        print("\nError: 'gdal2tiles.py' command not found.")
        print("Please ensure GDAL is installed correctly and your environment is activated.")
        print("If using Conda, run 'conda activate your_env_name'.")
        sys.exit(1) # 退出脚本
        
    print(f"Found gdal2tiles.py at: {gdal2tiles_path}")

    # --- Step 2: Preparing the command for gdal2tiles.py ---
    
    # 自动获取 CPU核心数以最大化并行处理能力
    try:
        cpu_cores = os.cpu_count()
        print(f"Using {cpu_cores} CPU cores for parallel processing.")
    except NotImplementedError:
        cpu_cores = 1
        print("Could not determine CPU count, using 1 core.")

    # 构建命令行参数列表
    command = [
        sys.executable,  # 使用当前环境的 Python 解释器来运行脚本
        gdal2tiles_path,
        '--profile', 'mercator',       # 必须为 'mercator' 以匹配 Web 地图
        '--zoom', zoom_range,
        '--processes', str(cpu_cores), # 使用所有核心进行并行处理
        '--webviewer', 'leaflet',      # 生成一个 Leaflet 预览网页
        '--title', 'FY-4B Satellite View', # 给预览网页设置标题
        '--quiet',                     # 减少不必要的输出，只显示进度条
        input_geotiff,
        output_dir
    ]
    
    print("\n--- Step 3: Starting the tiling process ---")
    print("This may take some time depending on the image size and zoom levels...")
    print(f"\nExecuting command:\n{' '.join(command)}\n")

    # --- Step 4: Executing the command ---
    try:
        # 实时执行命令，并将输出流打印到终端，这样你可以看到 gdal2tiles 的进度条
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
            
        process.wait()
        
        if process.returncode != 0:
            print(f"\nError: gdal2tiles.py exited with error code {process.returncode}.")
        else:
            print("\n--- Tiling process completed successfully! ---")

    except FileNotFoundError:
        print(f"Error: Could not execute command. Is '{sys.executable}' correct?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Creates map tiles from a georeferenced TIFF file using gdal2tiles.py."
    )
    parser.add_argument(
        "input_geotiff",
        type=str,
        help="Path to the input GeoTIFF file (e.g., 'image_cropped_mercator.tif')."
    )
    parser.add_argument(
        "output_dir",
        type=str,
        help="Path to the directory where tiles will be saved."
    )
    parser.add_argument(
        "-z", "--zoom",
        type=str,
        default="1-6",
        help="Zoom levels to generate, in 'min-max' format. Default: '1-6'."
    )
    
    args = parser.parse_args()
    
    # 创建输出目录（如果不存在）
    os.makedirs(args.output_dir, exist_ok=True)
    
    create_map_tiles(args.input_geotiff, args.output_dir, zoom_range=args.zoom)
    
    preview_file = os.path.join(args.output_dir, 'leaflet.html')
    if os.path.exists(preview_file):
        print(f"\n✅ All done! You can now view your tiles by opening this file in a web browser:")
        print(f"file://{os.path.abspath(preview_file)}")
    else:
        print("\n✅ All done! Tiles have been generated in the output directory.")