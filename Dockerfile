# 使用官方 Python 3.10 slim 版本
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（OpenCV 需要）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    git \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔
COPY requirements.txt .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 複製整個專案
COPY . .

# 設定 Flask 環境變數
ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# 開放 5000 port
EXPOSE 5000

# 啟動 Flask
CMD ["flask", "run"]
