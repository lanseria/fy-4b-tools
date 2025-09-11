import os
import argparse
import rasterio
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.feature import NaturalEarthFeature

def add_boundaries_to_geotiff(input_geotiff, output_png):
    """
    读取GeoTIFF，在其上叠加高精度海岸线，并保存为与其具有相同分辨率的PNG。
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
            if image_data.shape[0] == 4:
                image_data = image_data[:3, :, :]
            
            image_for_plot = np.transpose(image_data, (1, 2, 0))
            
            bounds = src.bounds
            image_extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
            
            height, width = src.height, src.width
            print(f"Input Image Dimensions: {width}x{height}")

    except Exception as e:
        print(f"Error reading GeoTIFF file: {e}")
        return

    # --- 核心改进：精确控制输出分辨率 ---
    print("--- Step 2: Preparing high-fidelity plot ---")
    
    # 1. 设置一个固定的DPI
    dpi = 100  # 使用一个简单的整数便于计算

    # 2. 根据输入图像的像素尺寸和DPI，反向计算出 Matplotlib 的 figsize (英寸)
    # figsize = (width_pixels / dpi, height_pixels / dpi)
    figsize = (width / dpi, height / dpi)
    
    print(f"Calculated figure size: {figsize[0]:.2f}x{figsize[1]:.2f} inches at {dpi} DPI.")

    # 3. 创建图形，确保它没有默认的边框和填充
    fig = plt.figure(figsize=figsize, dpi=dpi, frameon=False)

    # 4. 创建一个填满整个图形的地图轴 (axes)
    # [0, 0, 1, 1] 表示从左下角(0,0)开始，宽度和高度都占100%
    map_projection = ccrs.Mercator()
    ax = fig.add_axes([0, 0, 1, 1], projection=map_projection)

    # 5. 移除轴本身的所有边框和填充
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.get_xaxis().set_visible(False)
    ax.get_yaxis().set_visible(False)

    # 6. 设置地图的地理范围
    ax.set_extent(image_extent, crs=map_projection)
    
    # 7. 绘制原始图像，数据未经任何改动
    ax.imshow(image_for_plot, origin='upper', extent=image_extent, transform=map_projection)

    # 8. 添加高精度海岸线
    print("--- Step 3: Adding high-resolution boundaries ---")
    coastline_10m = NaturalEarthFeature('physical', 'coastline', '10m')

    # 绘制阴影层
    ax.add_feature(coastline_10m, edgecolor='black', facecolor='none', linewidth=1.5, alpha=0.6, zorder=10)
    # 绘制白色描边层
    ax.add_feature(coastline_10m, edgecolor='white', facecolor='none', linewidth=0.8, zorder=11)
    
    print(f"--- Step 4: Saving output PNG with original resolution to: {output_png} ---")
    
    # 9. 保存PNG，使用与计算figsize时相同的DPI
    # bbox_inches='tight' 和 pad_inches=0 是双重保险，确保无白边
    plt.savefig(
        output_png, 
        dpi=dpi,
        bbox_inches='tight',
        pad_inches=0,
        transparent=True
    )
    
    plt.close(fig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Overlays high-resolution boundaries on a georeferenced TIFF and saves it as a PNG with the same resolution."
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
        output_path = f"{name_without_ext}_with_hires_coastlines.png"

    add_boundaries_to_geotiff(args.input_geotiff, output_path)

    print(f"\n✅ All done! High-fidelity image with boundaries saved to: {os.path.abspath(output_path)}")