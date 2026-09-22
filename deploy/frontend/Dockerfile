# 前端镜像：构建静态资源，由容器内 nginx 托管 SPA 并反向代理 API。
#
# 构建上下文约定：**仓库根目录**（不是 frontend/）。
#   docker build -f deploy/frontend/Dockerfile -t library-frontend .
# 接入 compose 时在 services 下加：
#   frontend:
#     build: { context: ., dockerfile: deploy/frontend/Dockerfile }
#     ports: ['127.0.0.1:8081:80']
#     depends_on: [api]
#
# 为什么不直接 COPY frontend/ ：宿主机的 node_modules 里是 Windows 原生二进制
# （esbuild / rolldown 等），拷进 Linux 镜像会让构建失败；靠 .dockerignore 排除
# 又需要在仓库根加文件。这里改为显式列出需要参与构建的路径，结果确定且不依赖外部配置。
# 注意：以后在 frontend/ 顶层新增配置文件（如 .env.example 之外的新配置）要同步加进来。

FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig.json frontend/tsconfig.node.json ./
COPY frontend/src ./src
RUN npm run build

FROM nginx:alpine
COPY deploy/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
# 健康检查打静态首页，不经过 API，避免后端未就绪时把前端判为不健康
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
