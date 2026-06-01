# 企业售后工单系统 Docker 部署指南（Ubuntu）

## 一、安装 Docker 与 Docker Compose

```bash
# 1. 安装依赖
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# 2. 添加 Docker 官方 GPG 密钥
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. 添加 Docker APT 源
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. 安装 Docker Engine 和 Compose 插件
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 验证安装
docker --version
docker compose version

# 6. 将当前用户加入 docker 组（可选，避免每次 sudo）
sudo usermod -aG docker $USER
# 需要重新登录或执行 newgrp docker 生效
```

## 二、获取项目代码

### 方式 A：从 GitHub 克隆（推荐）

```bash
git clone https://github.com/zhouhongli/enterticketsystem.git
cd enterticketsystem
```

### 方式 B：本地已有代码

将项目目录复制到服务器上任意位置，进入项目根目录即可。

## 三、配置初始管理员账号

```bash
# 复制模板
cp .env.example .env

# 编辑配置
nano .env
```

修改 `.env` 文件中的管理员信息：

```ini
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@yourdomain.com
INITIAL_ADMIN_PASSWORD=YourStrongPassword123
```

> **安全提醒**：请使用强密码，不要使用 `.env.example` 中的默认值。

## 四、构建并启动

### 方式 A：使用一键脚本

```bash
chmod +x start.sh
./start.sh
```

### 方式 B：手动使用 docker compose

```bash
docker compose build
docker compose up -d
```

## 五、验证部署

```bash
# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f

# 测试 API 健康检查
curl http://localhost:8000/api/v1/health
# 预期返回: {"status":"ok","app":"企业售后工单系统"}
```

浏览器访问 `http://<服务器IP>:8000` 即可使用系统。

## 六、日常运维

```bash
# 查看实时日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止服务（保留数据）
docker compose down

# 停止并删除数据卷（清空所有数据）
docker compose down -v

# 更新代码后重新部署
git pull
docker compose build --no-cache
docker compose up -d

# 进入容器内部
docker compose exec ticket-system bash
```

## 七、HTTPS 反向代理（可选）

如果需要 HTTPS，推荐用 Nginx 做反向代理：

```bash
# 安装 Nginx 和 Certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 配置 Nginx（替换 /etc/nginx/sites-available/default）
cat > /etc/nginx/sites-available/default << 'EOF'
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo nginx -t && sudo systemctl reload nginx

# 申请 Let's Encrypt 证书
sudo certbot --nginx -d yourdomain.com
```

## 八、数据备份

```bash
# 备份数据卷
docker compose exec ticket-system cp /app/data/store.json /tmp/store_backup.json
docker cp enterticketsystem:/tmp/store_backup.json ./store_backup_$(date +%Y%m%d).json

# 或直接挂载宿主机目录后备份
cp /path/to/mounted/store.json ./store_backup_$(date +%Y%m%d).json
```

## 九、资源需求

| 资源 | 最低 | 推荐 | 说明 |
|---|---|---|---|
| CPU | 0.25 vCPU | 0.5 vCPU | 单进程 uvicorn，基本空闲 |
| 内存 | 128 MB | 256 MB | Python + FastAPI，无数据库 |
| 磁盘 | 200 MB | 500 MB | 镜像约 150 MB，数据按需增长 |
| 网络 | 8000 端口开放 | 80/443（Nginx） | 生产环境建议走反向代理 |

## 十、常见问题

**Q: 容器启动后立即退出？**

```bash
docker compose logs
# 检查是否缺少 INITIAL_ADMIN_USERNAME/EMAIL/PASSWORD 环境变量
```

**Q: 管理员登录失败？**

```bash
# 确认 .env 文件中三个 INITIAL_ADMIN_ 变量都已正确填写
# 停止并清理数据卷重新初始化
docker compose down -v
docker compose up -d
```

**Q: 端口 8000 已被占用？**

```bash
# 修改 docker-compose.yml 中的端口映射
# 例如改为 9000 端口:
#   ports:
#     - "9000:8000"
```
