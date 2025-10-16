# Step 1: 使用一个稳定、兼容的基础镜像
FROM m.daocloud.io/docker.io/library/python:3.11-slim-bookworm

# Step 2: 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app

# Step 3: 设置工作目录
WORKDIR /app

# --- 配置 APT 镜像源  ---
# RUN echo "\
# Types: deb\n\
# URIs: https://mirror.nju.edu.cn/debian/\n\
# Suites: bookworm bookworm-updates bookworm-backports\n\
# Components: main contrib non-free non-free-firmware\n\
# Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\
# " > /etc/apt/sources.list.d/debian.sources

# Step 4: 安装系统级的核心依赖
# 这是第一个耗时操作。通过把它放在前面，并且不依赖任何项目文件，
# 只要这一层不改变，Docker 在后续构建中就会直接使用缓存。
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libproj-dev libgeos-dev build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Step 5: 安装 Python 依赖
# a. 先只复制 requirements.txt 文件。
# b. 运行 pip install。
# 这样，只有当 requirements.txt 文件发生变化时，这一层缓存才会失效，
# Docker 才需要重新运行这个耗时的 pip install 步骤。
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# Step 6: 复制你项目的所有源代码
# 因为你的 Python 脚本 (如 main_workflow.py) 是最常被修改的。
# 把它放在最后，意味着当你修改代码并重新构建时，
# 前面的所有步骤 (apt-get, pip install) 都会使用缓存，构建会瞬间完成。
COPY . .

# Step 7: 创建数据目录
RUN mkdir -p /app/data

# Step 8: 声明数据卷
VOLUME /app/data

# Step 9: 设置容器启动命令
ENTRYPOINT ["python", "main_workflow.py"]