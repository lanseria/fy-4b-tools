裁剪
```
python crop_padding.py fy4b_full_disk_20250911023000.png
```
生成tif
```
python georeference_and_reproject.py fy4b_full_disk_20250911023000.png

python georeference_and_reproject.py fy4b_full_disk_20250911023000.png \
    --north 55.0 \
    --south -55.0 \
    --west 60.0 \
    --east 150.0 

python georeference_and_reproject.py fy4b_full_disk_20250911023000.png \
    --north 55.0 \
    --south 0.0 \
    --west 70.0 \
    --east 140.0 
```
添加边界
```
python add_boundaries.py fy4b_full_disk_20250911023000_cropped_mercator.tif
```