import os
import argparse
from PIL import Image
import numpy as np

# --- 核心修正点 ---
# 在处理任何图像之前，提高或禁用Pillow的像素限制
# 将其设置为 None 可以完全禁用这个检查
Image.MAX_IMAGE_PIXELS = None

def crop_image_padding(input_image_path, output_image_path, threshold=10):
    """
    自动检测并裁剪图像周围的黑色（或接近黑色）的内边距。
    """
    print(f"--- Step 1: Opening image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return

    try:
        im = Image.open(input_image_path)
        im_gray = im.convert('L')
        im_array = np.array(im_gray)
        
        non_empty_coords = np.where(im_array > threshold)
        
        if non_empty_coords[0].size == 0:
            print("Warning: Image appears to be completely empty. No cropping performed.")
            im.save(output_image_path)
            return
            
        # 计算边界框，并确保它们是标准的 Python 整数
        top = int(np.min(non_empty_coords[0]))
        bottom = int(np.max(non_empty_coords[0]))
        left = int(np.min(non_empty_coords[1]))
        right = int(np.max(non_empty_coords[1]))
        
        # Pillow 的 crop 方法需要 (left, top, right_exclusive, bottom_exclusive)
        bbox = (left, top, right + 1, bottom + 1)
        
        print(f"Detected content bounding box: {bbox}")

        im_cropped = im.crop(bbox)
        
        print(f"Original size: {im.size}, Cropped size: {im_cropped.size}")
        
        im_cropped.save(output_image_path)
        
        print(f"--- Step 2: Saved cropped image to: {output_image_path} ---")
        
    except Exception as e:
        print(f"An error occurred during cropping: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automatically crops black padding from the borders of an image."
    )
    parser.add_argument(
        "input_image",
        type=str,
        help="Path to the input image file."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Path for the output cropped image file. (Optional)"
    )
    parser.add_argument(
        "-t", "--threshold",
        type=int,
        default=10,
        help="Brightness threshold (0-255) to consider a pixel as padding. Default is 10."
    )

    args = parser.parse_args()

    if args.output:
        output_path = args.output
    else:
        base_name = os.path.basename(args.input_image)
        name_without_ext, ext = os.path.splitext(base_name)
        output_path = f"{name_without_ext}_cropped{ext}"

    crop_image_padding(args.input_image, output_path, threshold=args.threshold)
    
    print(f"\n✅ Cropping done! Next step is to use this new file for georeferencing.")