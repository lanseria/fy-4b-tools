下载拼接
```
python download_stitch.py
```
裁剪
```
python adjust_padding.py 20250912073000 --crop-x -135 --crop-y -162
```
生成tif
```
python create_geotiff.py 20250912073000

python georeference_and_reproject.py fy4b_full_disk_20250912060000_adjusted.png

python georeference_and_reproject.py fy4b_full_disk_20250912060000_adjusted.png \
    --north 55.0 \
    --south -55.0 \
    --west 60.0 \
    --east 150.0

python georeference_and_reproject.py fy4b_full_disk_20250912060000_adjusted.png \
    --north 55.0 \
    --south 0.0 \
    --west 70.0 \
    --east 140.0 
```
添加边界
```
python add_boundaries.py fy4b_full_disk_20250912060000_adjusted_cropped_mercator.tif
```
切图
```
python create_tiles.py 20250912073000
```
windows安装 gdal 编译包
https://github.com/cgohlke/geospatial-wheels