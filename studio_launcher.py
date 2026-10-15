"""
翻译工作台启动器：启动网页服务，就绪后自动打开浏览器。
由「启动翻译工作台.bat」调用；也可以直接运行 `python studio_launcher.py [--port 8000] [--cpu] [--redetect]`。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(ROOT, 'studio-settings.json')

# Banner printed by the bundled rusty_manga_image_translator module on import; not an error.
NOISE = ('experimental Python version', 'Rust rewrite', 'rust version is an early', 'manga-image-translator-rust')


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0


def studio_status(port: int):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/studio/api/status', timeout=2) as r:
            data = json.loads(r.read())
            return data if 'engine_ready' in data else None
    except Exception:
        return None


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data: dict):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def detect_gpu(redetect: bool) -> str:
    # Importing torch costs a few seconds, so remember the result.
    settings = load_settings()
    if not redetect and 'gpu' in settings:
        return settings['gpu']
    name = ''
    try:
        import torch
        if torch.xpu.is_available():
            name = torch.xpu.get_device_name(0)
        elif torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
    except Exception:
        pass
    settings['gpu'] = name
    save_settings(settings)
    return name


def forward_output(stream):
    for raw in iter(stream.readline, b''):
        line = raw.decode('utf-8', errors='replace').rstrip()
        if line and not any(n in line for n in NOISE):
            print(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--cpu', action='store_true', help='不使用显卡')
    parser.add_argument('--redetect', action='store_true', help='重新检测显卡')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    url = f'http://127.0.0.1:{args.port}/studio'

    print('=' * 52)
    print('  漫画翻译工作台')
    print('=' * 52)

    if studio_status(args.port):
        print(f'工作台已经在运行，直接打开：{url}')
        webbrowser.open(url)
        return 0
    if port_in_use(args.port) or port_in_use(args.port + 1):
        print(f'端口 {args.port} 或 {args.port + 1} 被其他程序占用，可以用 --port 换一个端口。')
        return 1

    gpu = '' if args.cpu else detect_gpu(args.redetect)
    print(f'计算设备：{gpu or "CPU"}')
    cmd = [sys.executable, os.path.join('server', 'main.py'), '--host', '127.0.0.1', '--port', str(args.port)]
    if gpu:
        cmd.append('--use-gpu')

    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    server = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    threading.Thread(target=forward_output, args=(server.stdout,), daemon=True).start()
    print('[1/2] 正在启动网页服务…')

    try:
        started = time.time()
        for _ in range(480):
            if server.poll() is not None:
                print('服务启动失败，请查看上面的错误信息。')
                return 1
            if studio_status(args.port):
                break
            time.sleep(0.5)
        print(f'      网页已就绪（{time.time() - started:.0f} 秒）：{url}')
        if not args.no_browser:
            webbrowser.open(url)
        print('[2/2] 正在加载翻译引擎和模型，通常需要 20–40 秒…')
        while server.poll() is None:
            status = studio_status(args.port)
            if status and status.get('engine_ready'):
                print(f'      翻译引擎已就绪（共 {time.time() - started:.0f} 秒），可以开始翻译了。')
                break
            time.sleep(1)
        print('\n使用期间请不要关闭这个窗口；关闭窗口即退出工作台。\n')
        return server.wait()
    except KeyboardInterrupt:
        print('正在退出…')
        server.terminate()
        return 0


if __name__ == '__main__':
    sys.exit(main())
