# 8s. AI Studio — 部署说明

## 文件结构
```
8s-studio/
├── index.html        # 前端（单文件）
├── main.py           # FastAPI 后端
├── .env              # API Key（禁止提交到 git）
├── requirements.txt  # Python 依赖
└── README.md
```

## 部署步骤（VPS / Ubuntu）

### 1. 上传文件
```bash
scp -r ./8s-studio user@your-server:/var/www/8s-studio
```

### 2. 安装依赖
```bash
cd /var/www/8s-studio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置 .env
`.env` 已包含 API Key，确认内容正确：
```
GEMINI_API_KEY=你的密钥
```
**重要：** 确保 `.env` 不被公开访问，在 `.gitignore` 中添加：
```
.env
```

### 4. 启动服务
```bash
# 开发模式
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式（后台运行）
nohup uvicorn main:app --host 0.0.0.0 --port 8000 &
```

### 5. Nginx 反向代理（推荐）
```nginx
server {
    listen 80;
    server_name 8s.go2030.cc;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # SSE 必须配置（关闭缓冲）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        chunked_transfer_encoding on;
    }
}
```

### 6. 进程管理（推荐用 systemd）
```ini
# /etc/systemd/system/8s-studio.service
[Unit]
Description=8s AI Studio
After=network.target

[Service]
WorkingDirectory=/var/www/8s-studio
ExecStart=/var/www/8s-studio/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
EnvironmentFile=/var/www/8s-studio/.env

[Install]
WantedBy=multi-user.target
```
```bash
systemctl enable 8s-studio
systemctl start 8s-studio
```

## 注意事项
- Nginx 必须关闭 `proxy_buffering` 否则 SSE 流式输出会卡住
- 推荐配置 HTTPS（Let's Encrypt: `certbot --nginx`）
- API Key 切勿暴露在前端代码或公开仓库中
