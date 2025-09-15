import os
import sys
import argparse
from PIL import Image
import numpy as np
from dotenv import load_dotenv

# 禁用Pillow的像素限制，以处理大图
Image.MAX_IMAGE_PIXELS = None

def adjust_image_padding(input_image_path, output_image_path, threshold=10, crop_x=0, crop_y=0):
    """
    自动裁剪图像周围的黑色内边距，并根据用户输入进行额外的裁剪（正值）或填充（负值）。
    返回 True 表示成功，False 表示失败。
    """
    print(f"--- Step 1: Processing image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return False

    try:
        im = Image.open(input_image_path)
        
        # 1. 自动裁剪核心图像
        im_gray = im.convert('L')
        im_array = np.array(im_gray)
        non_empty_coords = np.where(im_array > threshold)
        
        if non_empty_coords[0].size == 0:
            print("Warning: Image appears to be completely empty.")
            im.save(output_image_path)
            return True
            
        top = int(np.min(non_empty_coords[0]))
        bottom = int(np.max(non_empty_coords[0]))
        left = int(np.min(non_empty_coords[1]))
        right = int(np.max(non_empty_coords[1]))
        
        bbox = (left, top, right + 1, bottom + 1)
        im_core = im.crop(bbox)
        print(f"Detected content image size: {im_core.size}")

        # 2. 应用额外调整
        im_final = im_core
        
        if crop_x > 0:
            print(f"Applying horizontal crop of {crop_x}px from each side.")
            w, h = im_final.size
            if 2 * crop_x >= w:
                print(f"Error: crop_x value ({crop_x}) is too large for image width ({w}).")
                return False
            im_final = im_final.crop((crop_x, 0, w - crop_x, h))
        elif crop_x < 0:
            pad_x = abs(crop_x)
            print(f"Adding horizontal padding of {pad_x}px to each side.")
            w, h = im_final.size
            new_canvas = Image.new(im_final.mode, (w + 2 * pad_x, h), (0, 0, 0))
            new_canvas.paste(im_final, (pad_x, 0))
            im_final = new_canvas

        if crop_y > 0:
            print(f"Applying vertical crop of {crop_y}px from each side.")
            w, h = im_final.size
            if 2 * crop_y >= h:
                print(f"Error: crop_y value ({crop_y}) is too large for image height ({h}).")
                return False
            im_final = im_final.crop((0, crop_y, w, h - crop_y))
        elif crop_y < 0:
            pad_y = abs(crop_y)
            print(f"Adding vertical padding of {pad_y}px to each side.")
            w, h = im_final.size
            new_canvas = Image.new(im_final.mode, (w, h + 2 * pad_y), (0, 0, 0))
            new_canvas.paste(im_final, (0, pad_y))
            im_final = new_canvas
            
        print(f"Original full size: {im.size}, Final adjusted size: {im_final.size}")
        
        im_final.save(output_image_path)
        
        print(f"--- Step 2: Saved adjusted image to: {output_image_path} ---")
        return True
        
    except Exception as e:
        print(f"An error occurred during adjustment: {e}")
        return False

if __name__ == "__main__":
    load_dotenv() # 加载 .env 文件
    parser = argparse.ArgumentParser(
        description="Crops or pads an image based on a timestamp, then cleans up the source file."
    )
    # --- 核心改动：输入参数变为 timestamp ---
    parser.add_argument(
        "timestamp",
        type=str,
        help="The timestamp of the image to process, in 'YYYYMMDDHHMMSS' format."
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default='./data',
        help="The base directory for input and output images. Default: './data'"
    )
    parser.add_argument(
        "--keep-source",
        action="store_true", # 这是一个布尔标志
        help="If specified, the original source file will not be deleted after processing."
    )

    args = parser.parse_args()


    # --- 核心改动：从环境变量读取配置 ---
    crop_x = int(os.getenv('ADJUST_CROP_X', -135))
    crop_y = int(os.getenv('ADJUST_CROP_Y', -162))
    threshold = int(os.getenv('ADJUST_THRESHOLD', 10)) # 顺便也将 threshold 设为可配置

    # --- 核心改动：自动构建文件路径 ---
    input_filename = f"fy4b_full_disk_{args.timestamp}.png"
    input_filepath = os.path.join(args.data_dir, input_filename)
    
    output_filename = f"fy4b_full_disk_{args.timestamp}_adjusted.png"
    output_filepath = os.path.join(args.data_dir, output_filename)
    
    # 检查输入文件是否存在
    if not os.path.exists(input_filepath):
        print(f"Error: Input file not found at '{input_filepath}'")
        sys.exit(1)

    # 调用核心处理函数
    success = adjust_image_padding(
        input_filepath, 
        output_filepath, 
        threshold=threshold,
        crop_x=crop_x,
        crop_y=crop_y
    )
    
    if success:
        print(f"\n✅ Padding adjustment successful.")
        # --- 核心修正：根据标志决定是否删除 ---
        if not args.keep_source:
            try:
                os.remove(input_filepath)
                print(f"Successfully deleted source file: {input_filepath}")
            except OSError as e:
                print(f"Error deleting source file {input_filepath}: {e}")
        else:
            print(f"Source file '{input_filepath}' has been kept as requested.")
    else:
        print(f"\n❌ Padding adjustment failed. Source file '{input_filepath}' has been kept for inspection.")