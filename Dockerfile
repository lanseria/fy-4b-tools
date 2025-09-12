FROM m.daocloud.io/ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 设置容器内的工作目录
WORKDIR /app

# --- 1. 配置 APT 镜像源  ---
RUN echo "\
Types: deb\n\
URIs: https://mirrors.tuna.tsinghua.edu.cn/debian/\n\
Suites: bookworm bookworm-updates bookworm-backports\n\
Components: main contrib non-free non-free-firmware\n\
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\
" > /etc/apt/sources.list.d/debian.sources

# --- 关键修复 2: 创建用户时，为其指定一个有效的主目录 ---
# 使用 --home /app 将用户的主目录设置为工作目录 /app

# 这是最关键的一步，它为 GDAL, Rasterio, Cartopy 等库提供了所需的 C/C++ 核心库
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # GDAL 核心库和命令行工具 (如 gdal2tiles.py)
    gdal-bin \
    libgdal-dev \
    # Cartopy 和 Rasterio 的依赖
    libproj-dev \
    libgeos-dev \
    # 编译 Python 包可能需要的构建工具
    build-essential && \
    # 清理 APT 缓存以减小镜像体积
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
# Enable bytecode compilation
    UV_COMPILE_BYTECODE=1 \
# Copy from the cache instead of linking since it's a mounted volume
    PYTHONUNBUFFERED=1 \
    HOME=/app \
    PYTHONPATH=/app/src \
    MPLCONFIGDIR=/app/config/matplotlib \
    CARTOPY_DATA_DIR=/app/data/cartopy_data \
# Ensure installed tools can be executed out of the box
    UV_TOOL_BIN_DIR=/usr/local/bin

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 安装 Python 依赖
COPY . /app
RUN mkdir -p /app/config/matplotlib /app/data/cartopy_data /app/data
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# 预下载 Cartopy 数据到我们指定的新目录
RUN python -c "from cartopy.feature import NaturalEarthFeature; NaturalEarthFeature('physical', 'coastline', '10m')"

# --- 新增: 为数据和输出目录声明卷 ---
# 这明确表示这些目录用于存储持久化数据
VOLUME /app/data

# 容器启动时运行的命令
ENTRYPOINT ["python", "main_workflow.py"]