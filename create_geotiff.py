import os
import sys
import argparse
from osgeo import gdal, osr
from dotenv import load_dotenv

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

def create_geotiff_from_image(input_image_path, output_geotiff_path, bbox_config, output_width):
    """
    为PNG图像添加地理参考，并将其裁剪重投影为Web墨卡托GeoTIFF。
    返回 True 表示成功，False 表示失败。
    """
    print(f"--- Step 1: Processing image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return False

    src_ds = gdal.Open(input_image_path, gdal.GA_ReadOnly)
    if src_ds is None: return False

    width, height = src_ds.RasterXSize, src_ds.RasterYSize
    print(f"Image dimensions: {width}x{height}")

    srs_source = osr.SpatialReference()
    proj4_string = "+proj=geos +h=35785831 +lon_0=104.9 +sweep=x +datum=WGS84 +units=m"
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

    output_bounds_mercator = transform_bbox_4326_to_3857(bbox_config)
    
    warp_options = gdal.WarpOptions(
        dstSRS='EPSG:3857',
        format='GTiff',
        resampleAlg=gdal.GRA_Bilinear,
        dstAlpha=True,
        creationOptions=['COMPRESS=LZW', 'TILED=YES'],
        outputBounds=output_bounds_mercator,
        width=output_width
    )
    
    print(f"Target extent (Lat/Lon): N={bbox_config['north']}, S={bbox_config['south']}, W={bbox_config['west']}, E={bbox_config['east']}")
    print(f"Target output width: {output_width} pixels")
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
    # 在程序开始时加载 .env 文件
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Creates a cropped GeoTIFF from a PNG based on a timestamp, then cleans up the source."
    )
    parser.add_argument("timestamp", type=str, help="The timestamp of the image to process, in 'YYYYMMDDHHMMSS' format.")
    parser.add_argument("-d", "--data-dir", type=str, default='./data', help="The base directory for input and output files.")
    parser.add_argument("--keep-source", action="store_true", help="If specified, do not delete the source file.")
    args = parser.parse_args()

    # --- 核心改动：从环境变量读取配置，并提供默认值 ---
    bbox_config = {
        "north": float(os.getenv('GEOTIFF_BBOX_NORTH', 55.0)),
        "south": float(os.getenv('GEOTIFF_BBOX_SOUTH', -55.0)),
        "west": float(os.getenv('GEOTIFF_BBOX_WEST', 60.0)),
        "east": float(os.getenv('GEOTIFF_BBOX_EAST', 150.0))
    }
    output_width = int(os.getenv('GEOTIFF_OUTPUT_WIDTH', 4096))

    # --- 自动构建文件路径 ---
    input_filename = f"fy4b_full_disk_{args.timestamp}_adjusted.png"
    input_filepath = os.path.join(args.data_dir, input_filename)
    output_filename = f"fy4b_full_disk_{args.timestamp}_adjusted_mercator.tif"
    output_filepath = os.path.join(args.data_dir, output_filename)

    if not os.path.exists(input_filepath):
        print(f"Error: Input file not found at '{input_filepath}'.")
        sys.exit(1)
        
    # --- 调用核心函数，传入配置 ---
    success = create_geotiff_from_image(input_filepath, output_filepath, bbox_config, output_width)
    
    # --- 成功后自动删除源文件 ---
    if success:
        print(f"\n✅ GeoTIFF creation successful.")
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