"""启动脚本：python run.py

默认监听 0.0.0.0，同一局域网的同学也能访问。
只想本机用可以设环境变量 APP_HOST=127.0.0.1。
"""
import uvicorn

from app import config

if __name__ == "__main__":
    print(f"本机访问：http://127.0.0.1:{config.PORT}")
    print(f"局域网访问：http://<你的IP>:{config.PORT}")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)