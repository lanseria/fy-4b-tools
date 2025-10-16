import os
import argparse
from PIL import Image
import numpy as np

# 禁用Pillow的像素限制，以处理大图
Image.MAX_IMAGE_PIXELS = None

def adjust_image_padding(input_image_path, output_image_path, threshold=10, crop_x=0, crop_y=0):
    """
    自动裁剪图像周围的黑色内边距，并根据用户输入进行额外的裁剪（正值）或填充（负值）。

    Args:
        input_image_path (str): 输入的PNG图像路径。
        output_image_path (str): 输出的裁剪后的PNG图像路径。
        threshold (int): 亮度阈值，低于此值的像素被视为空白边距。
        crop_x (int): 正值表示从左右两侧裁剪的像素数，负值表示添加的像素数。
        crop_y (int): 正值表示从上下两侧裁剪的像素数，负值表示添加的像素数。
    """
    print(f"--- Step 1: Opening image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return

    try:
        im = Image.open(input_image_path)
        
        # 1. 首先，执行自动裁剪，得到一个干净的“核心图像”
        im_gray = im.convert('L')
        im_array = np.array(im_gray)
        non_empty_coords = np.where(im_array > threshold)
        
        if non_empty_coords[0].size == 0:
            print("Warning: Image appears to be completely empty.")
            im.save(output_image_path)
            return
            
        top = int(np.min(non_empty_coords[0]))
        bottom = int(np.max(non_empty_coords[0]))
        left = int(np.min(non_empty_coords[1]))
        right = int(np.max(non_empty_coords[1]))
        
        bbox = (left, top, right + 1, bottom + 1)
        im_core = im.crop(bbox)
        print(f"Detected content image size: {im_core.size}")

        # 2. 初始化最终图像为核心图像
        im_final = im_core
        
        # 3. 根据 crop_x 和 crop_y 的值进行处理
        
        # --- 处理 X 轴 ---
        if crop_x > 0:  # 正值：向内裁剪
            print(f"Applying additional horizontal crop of {crop_x}px from each side.")
            w, h = im_final.size
            if 2 * crop_x >= w:
                print(f"Error: crop_x value ({crop_x}) is too large for image width ({w}).")
                return
            im_final = im_final.crop((crop_x, 0, w - crop_x, h))
        elif crop_x < 0:  # 负值：向外填充
            pad_x = abs(crop_x)
            print(f"Adding horizontal padding of {pad_x}px to each side.")
            w, h = im_final.size
            new_w = w + 2 * pad_x
            new_canvas = Image.new(im_final.mode, (new_w, h), (0, 0, 0))
            new_canvas.paste(im_final, (pad_x, 0))
            im_final = new_canvas

        # --- 处理 Y 轴 ---
        if crop_y > 0:  # 正值：向内裁剪
            print(f"Applying additional vertical crop of {crop_y}px from each side.")
            w, h = im_final.size
            if 2 * crop_y >= h:
                print(f"Error: crop_y value ({crop_y}) is too large for image height ({h}).")
                return
            im_final = im_final.crop((0, crop_y, w, h - crop_y))
        elif crop_y < 0:  # 负值：向外填充
            pad_y = abs(crop_y)
            print(f"Adding vertical padding of {pad_y}px to each side.")
            w, h = im_final.size
            new_h = h + 2 * pad_y
            new_canvas = Image.new(im_final.mode, (w, new_h), (0, 0, 0))
            new_canvas.paste(im_final, (0, pad_y))
            im_final = new_canvas
            
        print(f"Original size: {im.size}, Final adjusted size: {im_final.size}")
        
        im_final.save(output_image_path)
        
        print(f"--- Step 2: Saved adjusted image to: {output_image_path} ---")
        
    except Exception as e:
        print(f"An error occurred during adjustment: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automatically crops padding from an image, with optional extra cropping (positive values) or padding (negative values)."
    )
    parser.add_argument(
        "input_image",
        type=str,
        help="Path to the input image file."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Path for the output adjusted image file. (Optional)"
    )
    parser.add_argument(
        "-t", "--threshold",
        type=int,
        default=10,
        help="Brightness threshold (0-255) to consider a pixel as padding. Default is 10."
    )
    parser.add_argument(
        "--crop-x",
        type=int,
        default=0,
        help="Pixels to adjust from left/right. Positive values crop, negative values add padding. Default: 0."
    )
    parser.add_argument(
        "--crop-y",
        type=int,
        default=0,
        help="Pixels to adjust from top/bottom. Positive values crop, negative values add padding. Default: 0."
    )

    args = parser.parse_args()

    if args.output:
        output_path = args.output
    else:
        base_name = os.path.basename(args.input_image)
        name_without_ext, ext = os.path.splitext(base_name)
        output_path = f"{name_without_ext}_adjusted{ext}"

    adjust_image_padding(
        args.input_image, 
        output_path, 
        threshold=args.threshold,
        crop_x=args.crop_x,
        crop_y=args.crop_y
    )
    
    print(f"\n✅ Padding adjustment done!")