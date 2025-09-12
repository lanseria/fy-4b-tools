裁剪
```
python crop_padding.py fy4b_full_disk_20250912060000.png --crop-x -135 --crop-y -162
```
生成tif
```
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
python create_tiles.py fy4b_full_disk_20250912060000_adjusted_cropped_mercator.tif ./satellite_tiles_20250912060000
```