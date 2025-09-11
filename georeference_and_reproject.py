import os
import argparse
from osgeo import gdal, osr

def transform_bbox_4326_to_3857(north, south, west, east):
    """将WGS84 (EPSG:4326)经纬度边界框转换为Web墨卡托 (EPSG:3857)坐标。"""
    srs_4326 = osr.SpatialReference()
    srs_4326.ImportFromEPSG(4326)
    
    srs_3857 = osr.SpatialReference()
    srs_3857.ImportFromEPSG(3857)
    
    # 确保轴序为 (经度, 纬度)
    if hasattr(srs_4326, 'SetAxisMappingStrategy'):
        srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    transform = osr.CoordinateTransformation(srs_4326, srs_3857)
    
    # --- 核心修正点 ---
    # 修正了参数顺序，应为 (经度, 纬度)
    # 左下角 (west, south)
    # 右上角 (east, north)
    min_x_mercator, min_y_mercator, _ = transform.TransformPoint(west, south)
    max_x_mercator, max_y_mercator, _ = transform.TransformPoint(east, north)
    
    return [min_x_mercator, min_y_mercator, max_x_mercator, max_y_mercator]

def georeference_and_reproject(input_image_path, output_geotiff_path, bbox_4326=None):
    """
    为无地理信息的风云4B全圆盘图像添加地理参考，并将其重投影为Web墨卡托。
    支持可选的地理范围裁剪。
    """
    print(f"--- Step 1: Opening input image: {input_image_path} ---")
    if not os.path.exists(input_image_path):
        print(f"Error: Input file not found at '{input_image_path}'")
        return

    src_ds = gdal.Open(input_image_path, gdal.GA_ReadOnly)
    if src_ds is None:
        print("Error: Could not open the input image with GDAL.")
        return

    width = src_ds.RasterXSize
    height = src_ds.RasterYSize
    print(f"Image dimensions: {width}x{height}")

    srs_source = osr.SpatialReference()
    proj4_string = "+proj=geos +h=35786000 +lon_0=105 +sweep=x +a=6378137 +b=6356752.314245"
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

    warp_options_dict = {
        'dstSRS': 'EPSG:3857',
        'format': 'GTiff',
        'resampleAlg': gdal.GRA_Bilinear,
        'dstAlpha': True,
        'creationOptions': ['COMPRESS=LZW', 'TILED=YES']
    }

    if bbox_4326:
        print("\n--- Cropping mode enabled ---")
        print(f"Target extent (Lat/Lon): N={bbox_4326['north']}, S={bbox_4326['south']}, W={bbox_4326['west']}, E={bbox_4326['east']}")
        
        output_bounds_mercator = transform_bbox_4326_to_3857(**bbox_4326)
        warp_options_dict['outputBounds'] = output_bounds_mercator
        
        warp_options_dict['width'] = 4096 # 增加分辨率以获得更清晰的裁剪图
        
        print(f"Calculated output bounds (Web Mercator): {output_bounds_mercator}")
        print(f"Setting output width to {warp_options_dict['width']} pixels to preserve detail.")

    else:
        print("\n--- Full disk mode enabled (no cropping) ---")

    warp_options = gdal.WarpOptions(**warp_options_dict)
    
    print(f"\n--- Step 3: Reprojecting to Web Mercator -> {output_geotiff_path} ---")
    try:
        gdal.Warp(output_geotiff_path, vrt_path, options=warp_options)
        print("--- Reprojection successful! ---")
    except Exception as e:
        print(f"An error occurred during reprojection: {e}")
    finally:
        if os.path.exists(vrt_path):
            os.remove(vrt_path)
            print(f"--- Step 4: Cleaned up temporary file '{vrt_path}' ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Georeference a FY-4B image and reproject to Web Mercator, with optional cropping."
    )
    parser.add_argument(
        "input_image", type=str, help="Path to the input stitched PNG image file."
    )
    parser.add_argument(
        "-o", "--output", type=str, help="Path for the output Web Mercator GeoTIFF file. (Optional)"
    )
    
    bbox_group = parser.add_argument_group('Cropping Options (all four must be provided to enable cropping)')
    bbox_group.add_argument("--north", type=float, help="Northern boundary latitude (e.g., 55.0)")
    bbox_group.add_argument("--south", type=float, help="Southern boundary latitude (e.g., 15.0)")
    bbox_group.add_argument("--west", type=float, help="Western boundary longitude (e.g., 70.0)")
    bbox_group.add_argument("--east", type=float, help="Eastern boundary longitude (e.g., 140.0)")

    args = parser.parse_args()

    bbox_4326 = None
    if all(arg is not None for arg in [args.north, args.south, args.west, args.east]):
        bbox_4326 = {
            "north": args.north,
            "south": args.south,
            "west": args.west,
            "east": args.east
        }
    
    if args.output:
        output_path = args.output
    else:
        base_name = os.path.basename(args.input_image)
        name_without_ext = os.path.splitext(base_name)[0]
        suffix = "_cropped_mercator" if bbox_4326 else "_mercator"
        output_path = f"{name_without_ext}{suffix}.tif"

    georeference_and_reproject(args.input_image, output_path, bbox_4326=bbox_4326)

    print(f"\n✅ All done! The final file is saved at: {os.path.abspath(output_path)}")