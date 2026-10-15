"""
翻译工作台启动器：启动网页服务，就绪后自动打开浏览器。
由「启动翻译工作台.bat」调用；也可以直接运行 `python studio_launcher.py [--port 8000] [--cpu]`。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0


def studio_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/studio/api/status', timeout=2) as r:
            return 'engine_ready' in json.loads(r.read())
    except Exception:
        return False


def detect_gpu() -> str:
    try:
        import torch
        if torch.xpu.is_available():
            return torch.xpu.get_device_name(0)
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--cpu', action='store_true', help='不使用显卡')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    url = f'http://127.0.0.1:{args.port}/studio'

    print('=' * 52)
    print('  漫画翻译工作台')
    print('=' * 52)

    if studio_running(args.port):
        print(f'工作台已经在运行，直接打开：{url}')
        webbrowser.open(url)
        return 0
    if port_in_use(args.port) or port_in_use(args.port + 1):
        print(f'端口 {args.port} 或 {args.port + 1} 被其他程序占用，可以用 --port 换一个端口。')
        return 1

    gpu = '' if args.cpu else detect_gpu()
    print(f'计算设备：{gpu or "CPU"}')
    cmd = [sys.executable, os.path.join('server', 'main.py'), '--host', '127.0.0.1', '--port', str(args.port)]
    if gpu:
        cmd.append('--use-gpu')

    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    server = subprocess.Popen(cmd, cwd=ROOT, env=env)
    print('正在启动服务…')

    try:
        for _ in range(240):
            if server.poll() is not None:
                print('服务启动失败，请查看上面的错误信息。')
                return 1
            if studio_running(args.port):
                break
            time.sleep(0.5)
        print(f'\n已就绪：{url}')
        print('翻译引擎还会再加载几十秒，网页右上角变成绿色「引擎就绪」后即可开始。')
        print('使用期间请不要关闭这个窗口；关闭窗口即退出工作台。\n')
        if not args.no_browser:
            webbrowser.open(url)
        return server.wait()
    except KeyboardInterrupt:
        print('正在退出…')
        server.terminate()
        return 0


if __name__ == '__main__':
    sys.exit(main())
