import os
import argparse
import rasterio
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.feature import NaturalEarthFeature # 导入 NaturalEarthFeature 以使用高精度数据

def add_boundaries_to_geotiff(input_geotiff, output_png):
    """
    读取一个带有地理信息的GeoTIFF文件，在其上叠加高精度、带阴影的大陆海岸线，并保存为PNG图片。
    """
    print(f"--- Step 1: Reading GeoTIFF: {input_geotiff} ---")
    if not os.path.exists(input_geotiff):
        print(f"Error: Input file not found at '{input_geotiff}'")
        return

    try:
        with rasterio.open(input_geotiff) as src:
            if src.crs.to_epsg() != 3857:
                print(f"Error: Input GeoTIFF is not in Web Mercator (EPSG:3857) projection. Found: {src.crs.to_string()}")
                return

            image_data = src.read()
            # 检查是否有Alpha通道，如果有，则只使用RGB通道
            if image_data.shape[0] == 4:
                image_data = image_data[:3, :, :]

            image_for_plot = np.transpose(image_data, (1, 2, 0))
            
            bounds = src.bounds
            image_extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
            
            height, width = src.height, src.width
            print(f"Image dimensions: {width}x{height}")
            print(f"Image CRS: {src.crs.to_string()}")

    except Exception as e:
        print(f"Error reading GeoTIFF file: {e}")
        return

    print("--- Step 2: Creating map plot with Cartopy ---")

    map_projection = ccrs.Mercator()
    base_size = 12  # 稍微增大基础尺寸以容纳更多细节
    aspect_ratio = height / width
    fig = plt.figure(figsize=(base_size, base_size * aspect_ratio), frameon=False) # frameon=False 确保无边框

    ax = fig.add_axes([0, 0, 1, 1], projection=map_projection) # add_axes 替换 add_subplot 以完全控制位置
    ax.set_extent(image_extent, crs=map_projection)
    ax.imshow(image_for_plot, origin='upper', extent=image_extent, transform=map_projection)

    # --- 核心改进点 ---
    print("--- Step 3: Adding high-resolution boundaries with shadow effect ---")
    
    # 1. 定义高精度海岸线特征
    # 'physical', 'coastline', '10m' 分别代表 类别, 名称, 分辨率
    coastline_10m = NaturalEarthFeature('physical', 'coastline', '10m')

    # 2. 绘制阴影层 (底层)
    # 使用稍粗的黑色线条，并设置半透明 (alpha) 和 zorder 确保它在底层
    ax.add_feature(coastline_10m, 
                   edgecolor='black', 
                   facecolor='none',  # 确保不填充
                   linewidth=0.4,     # 阴影线条粗细
                   alpha=0.6,         # 阴影透明度
                   zorder=10)         # 绘制顺序，数字越大越靠上

    # 3. 绘制白色描边层 (顶层)
    # 使用稍细的白色线条，覆盖在阴影之上
    ax.add_feature(coastline_10m, 
                   edgecolor='white', 
                   facecolor='none', 
                   linewidth=0.2,     # 白色线条粗细
                   zorder=11)         # 确保在阴影之上绘制
    
    print(f"--- Step 4: Saving output PNG to: {output_png} ---")
    
    plt.savefig(
        output_png, 
        dpi=512,
        bbox_inches='tight',
        pad_inches=0,
        transparent=True
    )
    
    plt.close(fig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Overlays high-resolution, shadowed continental boundaries on a georeferenced TIFF and saves it as a PNG."
    )
    parser.add_argument(
        "input_geotiff",
        type=str,
        help="Path to the input GeoTIFF file (must be in EPSG:3857)."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Path for the output PNG file. (Optional)"
    )

    args = parser.parse_args()

    if args.output:
        output_path = args.output
    else:
        base_name = os.path.basename(args.input_geotiff)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = f"{name_without_ext}_with_hires_coastlines.png" # 更新默认输出文件名

    add_boundaries_to_geotiff(args.input_geotiff, output_path)

    print(f"\n✅ All done! Image with enhanced boundaries saved to: {os.path.abspath(output_path)}")