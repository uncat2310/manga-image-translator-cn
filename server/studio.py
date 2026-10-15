"""
翻译工作台（/studio）：面向桌面用户的网页前端及其配套接口。

页面本身是 server/studio_web 下的静态文件（Vue 3，无需构建）。
翻译仍走 /translate/with-form/image/stream；这里只提供工作台额外需要的能力：
引擎状态、DeepSeek 设置（写入 .env 并重启翻译引擎）、把结果保存到本地 output/ 目录、
打开该目录、打包下载。
"""
import io
import os
import re
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / 'studio_web'
OUTPUT_ROOT = ROOT / 'output'
ENV_FILE = ROOT / '.env'

DEEPSEEK_MODELS = ['deepseek-flash', 'deepseek-v4-pro']
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}

router = APIRouter(prefix='/studio', tags=['studio'])


class Engine:
    """Tracks the translator subprocess so settings changes can restart it."""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.start_fn: Optional[Callable[[], subprocess.Popen]] = None
        self.host = '127.0.0.1'
        self.port = 0
        self.use_gpu = False

    def attach(self, proc, start_fn, host: str, port: int, use_gpu: bool):
        self.proc, self.start_fn = proc, start_fn
        self.host, self.port, self.use_gpu = host, port, use_gpu

    def is_ready(self) -> bool:
        if not self.port:
            return False
        if self.proc is not None and self.proc.poll() is not None:
            return False
        try:
            with socket.create_connection((self.host, self.port), timeout=0.3):
                return True
        except OSError:
            return False

    def restart(self):
        if self.start_fn is None:
            raise HTTPException(409, detail='翻译引擎不是由本服务启动的，请手动重启。')
        from server.instance import executor_instances
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        # start_fn registers the new instance again; drop the stale one first
        executor_instances.list = [i for i in executor_instances.list
                                   if not (i.ip == self.host and i.port == self.port)]
        self.proc = self.start_fn()


engine = Engine()


def _check_origin(request: Request):
    # The API server allows any CORS origin; studio endpoints change local files,
    # so only accept requests coming from the studio page itself.
    origin = request.headers.get('origin')
    if origin and urlparse(origin).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise HTTPException(403, detail='Forbidden origin')


def _safe_name(name: str, fallback: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')
    return name[:120] or fallback


def _folder(name: str) -> Path:
    path = (OUTPUT_ROOT / _safe_name(name, 'untitled')).resolve()
    if OUTPUT_ROOT.resolve() not in path.parents:
        raise HTTPException(400, detail='Invalid folder')
    return path


def _read_env() -> dict:
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            m = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
            if m and not line.lstrip().startswith('#'):
                values[m.group(1)] = re.sub(r'\s+#.*$', '', m.group(2)).strip().strip('"\'')
    return values


def _write_env(updates: dict):
    lines = ENV_FILE.read_text(encoding='utf-8').splitlines() if ENV_FILE.exists() else []
    pending = dict(updates)
    for i, line in enumerate(lines):
        m = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        if m and m.group(1) in pending:
            lines[i] = f'{m.group(1)}={pending.pop(m.group(1))}'
    lines += [f'{k}={v}' for k, v in pending.items()]
    ENV_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # The engine subprocess inherits our environment, and load_dotenv() never
    # overrides existing variables, so update it here too.
    os.environ.update(updates)


def _gpu_name() -> Optional[str]:
    try:
        import torch
        if torch.xpu.is_available():
            return torch.xpu.get_device_name(0)
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


_GPU_NAME = None


@router.get('', include_in_schema=False)
@router.get('/', include_in_schema=False)
async def studio_page():
    return FileResponse(WEB_DIR / 'index.html', headers={'Cache-Control': 'no-cache'})


@router.get('/api/status')
async def status():
    global _GPU_NAME
    if _GPU_NAME is None:
        _GPU_NAME = _gpu_name() or ''
    env = _read_env()
    from server.myqueue import task_queue
    return {
        'engine_ready': engine.is_ready(),
        'use_gpu': engine.use_gpu,
        'gpu_name': _GPU_NAME,
        'deepseek_key_set': bool(env.get('DEEPSEEK_API_KEY')),
        'deepseek_model': env.get('DEEPSEEK_MODEL') or 'deepseek-flash',
        'deepseek_models': DEEPSEEK_MODELS,
        'queue': len(task_queue.queue),
        'output_root': str(OUTPUT_ROOT),
    }


class SettingsBody(BaseModel):
    deepseek_api_key: Optional[str] = None
    deepseek_model: Optional[str] = None


@router.post('/api/settings')
async def save_settings(body: SettingsBody, request: Request):
    _check_origin(request)
    updates = {}
    if body.deepseek_api_key is not None:
        key = body.deepseek_api_key.strip()
        if key and not re.fullmatch(r'[A-Za-z0-9_\-]{8,200}', key):
            raise HTTPException(400, detail='API Key 格式不正确')
        if key:
            updates['DEEPSEEK_API_KEY'] = key
    if body.deepseek_model:
        if body.deepseek_model not in DEEPSEEK_MODELS:
            raise HTTPException(400, detail='不支持的模型')
        updates['DEEPSEEK_MODEL'] = body.deepseek_model
    if updates:
        _write_env(updates)
        engine.restart()
    return {'restarted': bool(updates)}


@router.post('/api/save')
async def save_result(request: Request, folder: str = Form(...), name: str = Form(...),
                      image: UploadFile = File(...)):
    _check_origin(request)
    target = _folder(folder)
    target.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(Path(name).stem, 'page')
    path = target / f'{stem}.png'
    path.write_bytes(await image.read())
    return {'path': str(path), 'folder': str(target)}


class FolderBody(BaseModel):
    folder: Optional[str] = None


@router.post('/api/open-folder')
async def open_folder(body: FolderBody, request: Request):
    _check_origin(request)
    target = _folder(body.folder) if body.folder else OUTPUT_ROOT
    target.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(target)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(target)])
    else:
        subprocess.Popen(['xdg-open', str(target)])
    return {'folder': str(target)}


@router.get('/api/zip')
async def download_zip(folder: str):
    target = _folder(folder)
    files = sorted(p for p in target.glob('*') if p.suffix.lower() in IMAGE_EXTS) if target.exists() else []
    if not files:
        raise HTTPException(404, detail='没有可下载的结果')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
        for p in files:
            zf.write(p, arcname=p.name)
    buf.seek(0)
    from urllib.parse import quote
    filename = quote(f'{target.name}.zip')
    return StreamingResponse(buf, media_type='application/zip',
                             headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


# ---------- 从网页链接导入（gallery-dl） ----------

DOWNLOAD_ROOT = ROOT / 'downloads'
_jobs: dict = {}


class ImportBody(BaseModel):
    url: str


def _gallery_dl(*args, timeout=None) -> subprocess.CompletedProcess:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    return subprocess.run([sys.executable, '-m', 'gallery_dl', *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout, creationflags=flags)


def _last_error(proc: subprocess.CompletedProcess) -> str:
    lines = [l.strip() for l in (proc.stderr or '').splitlines() if l.strip()]
    errors = [l for l in lines if 'error' in l.lower()] or lines
    return errors[-1][:300] if errors else f'gallery-dl 退出码 {proc.returncode}'


def _run_import(job: dict):
    import json
    url = job['url']
    try:
        probe = _gallery_dl('-j', url, timeout=120)
        try:
            messages = json.loads(probe.stdout or '[]')
        except json.JSONDecodeError:
            messages = []
        files = [m for m in messages if isinstance(m, list) and m and m[0] == 3]
        if not files:
            raise RuntimeError(_last_error(probe) if probe.returncode else '这个链接里没有找到图片')
        meta = next((m[1] for m in messages if m and m[0] == 2 and isinstance(m[1], dict)), files[0][2])
        title = meta.get('title') or meta.get('title_en') or meta.get('gallery_id') or 'web-import'
        job.update(title=_safe_name(str(title), 'web-import'), total=len(files), status='downloading')

        target = DOWNLOAD_ROOT / job['title']
        target.mkdir(parents=True, exist_ok=True)
        job['dir'] = target
        proc = subprocess.Popen([sys.executable, '-m', 'gallery_dl', '-D', str(target), url],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        _, err = proc.communicate(timeout=1800)
        names = sorted((p.name for p in target.iterdir() if p.suffix.lower() in IMAGE_EXTS),
                       key=lambda n: [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', n)])
        if not names:
            raise RuntimeError(_last_error(subprocess.CompletedProcess([], proc.returncode, '', err)))
        job.update(files=names, status='done')
    except subprocess.TimeoutExpired:
        job.update(status='error', error='下载超时')
    except Exception as e:  # noqa: BLE001 - reported to the page
        job.update(status='error', error=str(e))


@router.post('/api/import')
async def start_import(body: ImportBody, request: Request):
    _check_origin(request)
    url = body.url.strip()
    if urlparse(url).scheme not in ('http', 'https'):
        raise HTTPException(400, detail='请输入以 http:// 或 https:// 开头的网址')
    import secrets
    import threading
    job_id = secrets.token_hex(6)
    job = {'id': job_id, 'url': url, 'status': 'probing', 'title': '', 'total': 0, 'files': [], 'error': '', 'dir': None}
    _jobs[job_id] = job
    threading.Thread(target=_run_import, args=(job,), daemon=True).start()
    return {'id': job_id}


@router.get('/api/import/{job_id}')
async def import_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail='任务不存在')
    downloaded = 0
    if job['dir'] and job['dir'].exists():
        downloaded = sum(1 for p in job['dir'].iterdir() if p.suffix.lower() in IMAGE_EXTS)
    return {k: job[k] for k in ('id', 'status', 'title', 'total', 'files', 'error')} | {'downloaded': downloaded}


@router.get('/api/import/{job_id}/file/{name}')
async def import_file(job_id: str, name: str):
    job = _jobs.get(job_id)
    if not job or name not in job['files']:
        raise HTTPException(404)
    return FileResponse(job['dir'] / name)


class _QuietPolling:
    # The studio page polls these every few seconds; keep them out of the console.
    def filter(self, record) -> bool:
        msg = record.getMessage()
        return '/studio/api/status' not in msg and '/studio/api/import/' not in msg


def mount(app):
    import logging
    logging.getLogger('uvicorn.access').addFilter(_QuietPolling())
    app.include_router(router)
    app.mount('/studio/static', StaticFiles(directory=str(WEB_DIR)), name='studio-static')
