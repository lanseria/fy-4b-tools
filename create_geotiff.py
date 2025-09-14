import os
import sys
import argparse
from osgeo import gdal, osr

# --- 硬编码的默认裁剪范围 (WGS84 经纬度) ---
DEFAULT_BBOX = {
    "north": 55.0,
    "south": -55.0,
    "west": 60.0,
    "east": 150.0
}

def transform_bbox_4326_to_3857(bbox):
    """将WGS84经纬度边界框转换为Web墨卡托坐标。"""
    srs_4326 = osr.SpatialReference()
    srs_4326.ImportFromEPSG(4326)
    srs_3857 = osr.SpatialReference()
    srs_3857.ImportFromEPSG(3857)
    
    if hasattr(srs_4326, 'SetAxisMappingStrategy'):
        srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    transform = osr.CoordinateTransformation(srs_4326, srs_3857)
    
    min_x, min_y, _ = transform.TransformPoint(bbox["west"], bbox["south"])
    max_x, max_y, _ = transform.TransformPoint(bbox["east"], bbox["north"])
    
    return [min_x, min_y, max_x, max_y]

def create_geotiff_from_image(input_image_path, output_geotiff_path):
    """
    为PNG图像添加地理参考，并将其裁剪重投影为Web墨卡托GeoTIFF。
    返回 True 表示成功，False 表示失败。
    """
    print(f"--- Step 1: Processing image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return False

    src_ds = gdal.Open(input_image_path, gdal.GA_ReadOnly)
    if src_ds is None:
        print("Error: Could not open the input image with GDAL.")
        return False

    width = src_ds.RasterXSize
    height = src_ds.RasterYSize
    print(f"Image dimensions: {width}x{height}")

    srs_source = osr.SpatialReference()
    proj4_string = "+proj=geos +h=35785831 +lon_0=104.7 +sweep=x +datum=WGS84 +units=m"
    srs_source.ImportFromProj4(proj4_string)
    
    x_min, x_max, y_min, y_max = -5568748.0, 5568748.0, -5568748.0, 5568748.0
    geotransform = [x_min, (x_max - x_min) / width, 0, y_max, 0, (y_min - y_max) / height]

    vrt_path = "temp_georeferenced.vrt"
    driver = gdal.GetDriverByName('VRT')
    vrt_ds = driver.CreateCopy(vrt_path, src_ds)
    vrt_ds.SetProjection(srs_source.ExportToWkt())
    vrt_ds.SetGeoTransform(geotransform)
    vrt_ds.SetMetadataItem("SATELLITE", "Fengyun-4B (FY-4B)")
    vrt_ds = None
    src_ds = None
    print(f"--- Step 2: Created virtual georeferenced file at '{vrt_path}' ---")

    # 使用硬编码的默认裁剪范围
    output_bounds_mercator = transform_bbox_4326_to_3857(DEFAULT_BBOX)
    
    warp_options = gdal.WarpOptions(
        dstSRS='EPSG:3857',
        format='GTiff',
        resampleAlg=gdal.GRA_Bilinear,
        dstAlpha=True,
        creationOptions=['COMPRESS=LZW', 'TILED=YES'],
        outputBounds=output_bounds_mercator,
        width=4096  # 设置固定宽度以保持高清
    )
    
    print(f"Target extent (Lat/Lon): N={DEFAULT_BBOX['north']}, S={DEFAULT_BBOX['south']}, W={DEFAULT_BBOX['west']}, E={DEFAULT_BBOX['east']}")
    print(f"\n--- Step 3: Reprojecting and cropping to -> {output_geotiff_path} ---")
    
    success = False
    try:
        gdal.Warp(output_geotiff_path, vrt_path, options=warp_options)
        print("--- Reprojection successful! ---")
        success = True
    except Exception as e:
        print(f"An error occurred during reprojection: {e}")
    finally:
        if os.path.exists(vrt_path):
            os.remove(vrt_path)
            print(f"--- Step 4: Cleaned up temporary file '{vrt_path}' ---")
    
    return success

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Creates a cropped and georeferenced TIFF from a PNG based on a timestamp, then cleans up the source."
    )
    parser.add_argument(
        "timestamp",
        type=str,
        help="The timestamp of the image to process, in 'YYYYMMDDHHMMSS' format."
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default='./data',
        help="The base directory for input and output files. Default: './data'"
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="If specified, the original source file will not be deleted after processing."
    )

    args = parser.parse_args()

    # --- 自动构建文件路径 ---
    input_filename = f"fy4b_full_disk_{args.timestamp}_adjusted.png"
    input_filepath = os.path.join(args.data_dir, input_filename)
    
    output_filename = f"fy4b_full_disk_{args.timestamp}_adjusted_mercator.tif"
    output_filepath = os.path.join(args.data_dir, output_filename)

    # 检查输入文件是否存在
    if not os.path.exists(input_filepath):
        print(f"Error: Input file not found at '{input_filepath}'. Please run the adjustment script first.")
        sys.exit(1)
        
    # 调用核心处理函数
    success = create_geotiff_from_image(input_filepath, output_filepath)
    
    # --- 成功后自动删除源文件 ---
    if success:
        print(f"\n✅ GeoTIFF creation successful.")
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
        print(f"\n❌ GeoTIFF creation failed. Source file '{input_filepath}' has been kept for inspection.")