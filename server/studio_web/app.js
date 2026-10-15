/* 漫画翻译工作台 — Vue 3（无构建） */
const { createApp, reactive, ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;

const STORE_KEY = 'mit-studio-options';
const IMAGE_RE = /\.(png|jpe?g|webp|bmp)$/i;

const STAGES = {
  running_pre_translation_hooks: ['准备中', 5],
  colorizing: ['上色中', 8],
  upscaling: ['放大中', 10],
  detection: ['检测文字', 15],
  ocr: ['识别文字', 30],
  textline_merge: ['整理文本', 38],
  translating: ['翻译中', 45],
  'after-translating': ['翻译完成', 75],
  'mask-generation': ['生成遮罩', 78],
  inpainting: ['去除原文', 82],
  rendering: ['嵌入译文', 92],
  downscaling: ['还原尺寸', 96],
  finished: ['完成', 100],
};

const LANGUAGES = [
  ['CHS', '简体中文'], ['CHT', '繁体中文'], ['JPN', '日语'], ['KOR', '韩语'], ['ENG', '英语'],
].map(([code, name]) => ({ code, name }));

const QUALITY = {
  fast: { label: '快速', size: 1536, hint: '适合小图或预览，速度最快' },
  standard: { label: '标准', size: 2048, hint: '大多数漫画的推荐设置' },
  fine: { label: '精细', size: 2560, hint: '高分辨率扫描图，文字很小时使用' },
};

const DEFAULT_OPTIONS = {
  translator: 'deepseek', targetLang: 'CHS', direction: 'auto', quality: 'standard',
  fontOffset: 0, inpainter: 'lama_large', ocr: '48px', noBorder: false, autoTranslate: true, thumb: 'm',
};

function loadOptions() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch {}
  const opts = { ...DEFAULT_OPTIONS, ...saved };
  if (!LANGUAGES.some((l) => l.code === opts.targetLang)) opts.targetLang = DEFAULT_OPTIONS.targetLang;
  return opts;
}

function todayName() {
  const d = new Date(), p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}${p(d.getMinutes())}`;
}

// 读取拖进来的文件夹（递归）
async function collectEntry(entry, out) {
  if (entry.isFile) {
    await new Promise((res) => entry.file((f) => { out.push(f); res(); }, res));
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    let batch;
    do {
      batch = await new Promise((res) => reader.readEntries(res, () => res([])));
      for (const e of batch) await collectEntry(e, out);
    } while (batch.length);
  }
}

// 解析 /translate/with-form/image/stream 的流：1 字节状态 + 4 字节长度 + 数据
async function translateStream(file, config, signal, onEvent) {
  const form = new FormData();
  form.append('image', file, file.name);
  form.append('config', JSON.stringify(config));
  const res = await fetch('/translate/with-form/image/stream', { method: 'POST', body: form, signal });
  if (!res.ok) throw new Error(`服务器返回 ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = new Uint8Array(0);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const merged = new Uint8Array(buf.length + value.length);
    merged.set(buf); merged.set(value, buf.length); buf = merged;
    while (buf.length >= 5) {
      const size = new DataView(buf.buffer, buf.byteOffset + 1, 4).getUint32(0);
      if (buf.length < 5 + size) break;
      const code = buf[0];
      const data = buf.slice(5, 5 + size);
      buf = buf.slice(5 + size);
      if (code === 0) return new Blob([data], { type: 'image/png' });
      if (code === 2) throw new Error(decoder.decode(data) || '翻译失败');
      onEvent(code, decoder.decode(data));
    }
  }
  throw new Error('连接意外中断');
}

function friendlyError(msg) {
  if (/401|API key|Authentication/i.test(msg)) return 'DeepSeek Key 无效，请在设置里检查';
  if (/model/i.test(msg) && /400/.test(msg)) return 'DeepSeek 模型名不可用，请在设置里重新选择';
  if (/Failed to fetch|NetworkError|连接/i.test(msg)) return '无法连接到翻译服务，请确认启动窗口还开着';
  return msg.replace(/^Translation failed:\s*/i, '').slice(0, 160);
}

createApp({
  setup() {
    const pages = reactive([]);
    const options = reactive(loadOptions());
    const folderName = ref(todayName());
    const status = reactive({ loaded: false, engine_ready: false, use_gpu: false, gpu_name: '', deepseek_key_set: false,
      deepseek_model: 'deepseek-flash', deepseek_models: ['deepseek-flash', 'deepseek-v4-pro'], queue: 0, output_root: '' });
    const running = ref(false);
    const stopping = ref(false);
    const dragging = ref(false);
    const toasts = reactive([]);
    const viewer = reactive({ open: false, index: 0, mode: 'compare', split: 50 });
    const settings = reactive({ open: false, key: '', showKey: false, model: 'deepseek-flash', saving: false, picking: false });
    const fileInput = ref(null), folderInput = ref(null), stage = ref(null), gridScroll = ref(null);
    const filter = ref('all');
    const stamp = ref(false);
    const theme = ref(document.documentElement.dataset.theme === 'comic' ? 'comic' : 'island');
    const mode = ref(['light', 'dark'].includes(document.documentElement.dataset.mode) ? document.documentElement.dataset.mode : 'auto');
    const darkQuery = matchMedia('(prefers-color-scheme: dark)');
    function applyScheme() {
      document.documentElement.dataset.mode = mode.value;
      document.documentElement.dataset.scheme = mode.value === 'auto' ? (darkQuery.matches ? 'dark' : 'light') : mode.value;
    }
    watch(mode, (m) => {
      applyScheme();
      try { localStorage.setItem('mit-studio-mode', m); } catch {}
    });
    darkQuery.addEventListener('change', applyScheme);
    const MODES = { light: '白天', dark: '夜间', auto: '跟随系统' };
    const modeLabel = computed(() => MODES[mode.value]);
    function cycleMode() {
      mode.value = mode.value === 'light' ? 'dark' : mode.value === 'dark' ? 'auto' : 'light';
      toast('外观：' + modeLabel.value);
    }
    const clock = reactive({ week: '', date: '', time: '' });
    function tick() {
      const d = new Date(), p = (n) => String(n).padStart(2, '0');
      clock.week = '星期' + '日一二三四五六'[d.getDay()];
      clock.date = `${d.getMonth() + 1}月${d.getDate()}日`;
      clock.time = `${p(d.getHours())}:${p(d.getMinutes())}`;
    }
    tick();
    setInterval(tick, 10000);
    watch(theme, (t) => {
      document.documentElement.dataset.theme = t;
      try { localStorage.setItem('mit-studio-theme', t); } catch {}
    });
    const importUrl = ref('');
    const imports = reactive([]);
    const sites = reactive({ pixiv: false, pixiv_mode: null, exhentai: false });
    const eh = reactive({ open: false, member_id: '', pass_hash: '', igneous: '', busy: false });
    const pixiv = reactive({ open: false, step: 1, code: '', token: '', cookie: '', busy: false });
    let abort = null, nextId = 1, statusTimer = null, startedAt = 0, finishedInRun = 0, importBusy = false;

    watch(options, (v) => { try { localStorage.setItem(STORE_KEY, JSON.stringify(v)); } catch {} }, { deep: true });

    function toast(text, type = 'info', ms = 3500) {
      const t = { id: nextId++, text, type };
      toasts.push(t);
      setTimeout(() => { const i = toasts.indexOf(t); if (i >= 0) toasts.splice(i, 1); }, ms);
    }

    async function refreshStatus() {
      try {
        const r = await fetch('/studio/api/status');
        if (!r.ok) throw new Error();
        Object.assign(status, await r.json(), { loaded: true });
      } catch {
        status.engine_ready = false;
        status.loaded = true;
        status.offline = true;
        return;
      }
      status.offline = false;
    }

    /* ---------- 文件 ---------- */
    function addFiles(files, fromFolder, folder) {
      const imgs = [...files].filter((f) => IMAGE_RE.test(f.name))
        .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name, 'zh', { numeric: true }));
      if (!imgs.length) { toast('没有找到图片文件（支持 PNG / JPG / WEBP / BMP）', 'error'); return 0; }
      if (!folder) {
        if (!pages.length && fromFolder) folderName.value = fromFolder;
        folder = fromFolder || folderName.value || todayName();
      }
      let num = pages.filter((x) => x.folder === folder).length;
      for (const f of imgs) {
        pages.push({ id: nextId++, file: f, name: f.name, folder, num: ++num, srcUrl: URL.createObjectURL(f), resultUrl: '',
          status: 'queued', stageText: '', progress: 0, error: '', ms: 0 });
      }
      toast(`已添加 ${imgs.length} 页到「${folder}」`);
      return imgs.length;
    }

    async function onDrop(e) {
      dragging.value = false;
      const items = [...(e.dataTransfer.items || [])].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
      if (items.length) {
        const out = [];
        for (const entry of items) await collectEntry(entry, out);
        const folder = items.length === 1 && items[0].isDirectory ? items[0].name : '';
        addFiles(out, folder);
      } else {
        addFiles(e.dataTransfer.files);
      }
    }

    function onPick(e) {
      const files = [...e.target.files];
      const rel = files[0] && files[0].webkitRelativePath;
      addFiles(files, rel ? rel.split('/')[0] : '');
      e.target.value = '';
    }
    const pickFiles = () => fileInput.value.click();
    const pickFolder = () => folderInput.value.click();

    function releasePage(p) {
      URL.revokeObjectURL(p.srcUrl);
      if (p.resultUrl) URL.revokeObjectURL(p.resultUrl);
    }
    function removePage(i) { releasePage(pages[i]); pages.splice(i, 1); }
    function clearAll() {
      if (!confirm('清空当前列表？已保存到文件夹的结果不会被删除。')) return;
      pages.splice(0).forEach(releasePage);
      for (let k = imports.length - 1; k >= 0; k--) if (['done', 'error', 'queued'].includes(imports[k].status)) imports.splice(k, 1);
      folderName.value = todayName();
    }

    /* ---------- 从网页链接导入：排队依次下载 ---------- */
    const ACTIVE_IMPORT = ['probing', 'downloading', 'loading'];
    function importFromUrl() {
      const urls = importUrl.value.split(/\s+/).filter(Boolean);
      if (!urls.length) return;
      const bad = urls.filter((u) => !/^https?:\/\//i.test(u));
      if (bad.length) { toast('请输入以 http:// 或 https:// 开头的网址', 'error'); return; }
      let added = 0;
      for (const url of urls) {
        if (imports.some((j) => j.url === url && j.status !== 'error' && j.status !== 'done')) continue;
        imports.push({ id: nextId++, url, status: 'queued', title: '', total: 0, downloaded: 0, error: '' });
        added++;
      }
      importUrl.value = '';
      if (added > 1 || imports.length > 1) toast(`已加入下载队列（${imports.filter((j) => j.status === 'queued').length} 个等待中）`);
      pumpImports();
    }

    async function runImport(job) {
      job.status = 'probing'; job.error = '';
      const r = await fetch('/studio/api/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: job.url }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || '无法开始下载');
      let info;
      for (;;) {
        await new Promise((res) => setTimeout(res, 1000));
        const st = await fetch('/studio/api/import/' + data.id);
        if (!st.ok) throw new Error('下载任务丢失，请重试');
        info = await st.json();
        Object.assign(job, { status: info.status === 'done' ? 'loading' : info.status, title: info.title || job.title,
          total: info.total, downloaded: info.downloaded });
        if (info.status === 'done') break;
        if (info.status === 'error') throw new Error(info.error || '下载失败');
      }
      const files = [];
      for (const name of info.files) {
        const b = await fetch(`/studio/api/import/${data.id}/file/${encodeURIComponent(name)}`).then((x) => x.blob());
        files.push(new File([b], name, { type: b.type }));
      }
      addFiles(files, '', info.title || todayName());
      job.status = 'done';
      setTimeout(() => { const k = imports.indexOf(job); if (k >= 0 && job.status === 'done') imports.splice(k, 1); }, 4000);
      if (options.autoTranslate) {
        if (!status.engine_ready) toast('翻译引擎还在启动，就绪后点「开始翻译」即可', 'info', 5000);
        else start(false);
      }
    }

    async function pumpImports() {
      if (importBusy) return;
      importBusy = true;
      try {
        for (;;) {
          const job = imports.find((j) => j.status === 'queued');
          if (!job) break;
          try { await runImport(job); } catch (err) { job.status = 'error'; job.error = String(err.message || err); }
        }
      } finally {
        importBusy = false;
      }
    }
    function retryImport(job) { job.status = 'queued'; job.error = ''; pumpImports(); }
    function removeImport(job) { const k = imports.indexOf(job); if (k >= 0) imports.splice(k, 1); }
    function importText(j) {
      if (j.status === 'queued') return '排队中';
      if (j.status === 'probing') return '正在读取图集信息…';
      if (j.status === 'downloading') return j.total ? `正在下载 ${j.downloaded} / ${j.total}` : `正在下载，已下载 ${j.downloaded} 张`;
      if (j.status === 'loading') return '正在载入图片…';
      if (j.status === 'done') return `已加入翻译队列（${j.total} 页）`;
      return '下载失败：' + j.error;
    }

    /* ---------- 翻译 ---------- */
    function buildConfig() {
      const size = QUALITY[options.quality].size;
      return {
        translator: { translator: options.translator, target_lang: options.translator === 'deepseek' ? options.targetLang : 'CHS' },
        detector: { detector: 'default', detection_size: size },
        ocr: { ocr: options.ocr },
        inpainter: { inpainter: options.inpainter, inpainting_size: size, inpainting_precision: 'bf16' },
        render: { direction: options.direction, font_size_offset: options.fontOffset, disable_font_border: options.noBorder },
      };
    }

    async function saveResult(p, blob) {
      const form = new FormData();
      form.append('folder', p.folder || folderName.value || todayName());
      form.append('name', p.name);
      form.append('image', blob, p.name);
      const r = await fetch('/studio/api/save', { method: 'POST', body: form });
      if (!r.ok) throw new Error('结果保存失败');
    }

    async function translatePage(p) {
      p.status = 'running'; p.stageText = '排队中'; p.progress = 2; p.error = '';
      const t0 = performance.now();
      abort = new AbortController();
      let skipped = false;
      try {
        const blob = await translateStream(p.file, buildConfig(), abort.signal, (code, text) => {
          if (code === 3) { p.stageText = Number(text) > 0 ? `排队中（前面还有 ${text} 页）` : '排队中'; return; }
          if (code === 4) { p.stageText = '等待翻译引擎'; return; }
          if (code !== 1 || text.startsWith('rendering_folder')) return;
          if (text === 'skip-no-text' || text === 'skip-no-regions') skipped = true;
          if (text === 'error-translating') { p.stageText = '翻译出错，重试中'; return; }
          const s = STAGES[text];
          if (s) { p.stageText = s[0]; p.progress = Math.max(p.progress, s[1]); }
        });
        if (p.resultUrl) URL.revokeObjectURL(p.resultUrl);
        p.resultUrl = URL.createObjectURL(blob);
        p.ms = performance.now() - t0;
        await saveResult(p, blob);
        p.status = skipped ? 'skipped' : 'done';
        p.progress = 100;
        finishedInRun++;
      } catch (err) {
        if (err.name === 'AbortError') { p.status = 'queued'; p.stageText = ''; p.progress = 0; return; }
        p.status = 'error';
        p.error = friendlyError(String(err.message || err));
      } finally {
        abort = null;
      }
    }

    function folderFinished(folder) {
      return !pages.some((x) => x.folder === folder && (x.status === 'queued' || x.status === 'running'));
    }

    // Keeps taking the next queued page, so pages added during a run (drops, links, retries) are picked up too.
    async function start(retryErrors = true) {
      if (running.value) return;
      if (options.translator === 'deepseek' && !status.deepseek_key_set) { openSettings(); return; }
      if (retryErrors) pages.forEach((p) => { if (p.status === 'error') { p.status = 'queued'; p.error = ''; p.progress = 0; } });
      running.value = true; stopping.value = false;
      startedAt = performance.now(); finishedInRun = 0;
      const doneFolders = [];
      try {
        while (!stopping.value) {
          const p = pages.find((x) => x.status === 'queued');
          if (!p) break;
          await translatePage(p);
          if (p.status !== 'queued' && folderFinished(p.folder) && !doneFolders.includes(p.folder)) {
            doneFolders.push(p.folder);
            const failed = pages.filter((x) => x.folder === p.folder && x.status === 'error').length;
            if (failed) toast(`「${p.folder}」完成，但有 ${failed} 页失败`, 'error', 5000);
            else toast(`「${p.folder}」翻译完成`, 'ok', 4000);
          }
        }
      } finally {
        running.value = false;
        const failed = counts.value.error;
        const moreComing = imports.some((j) => j.status === 'queued' || ACTIVE_IMPORT.includes(j.status));
        if (stopping.value) toast('已停止');
        else if (failed) toast(`有 ${failed} 页失败，可点卡片右上角 ↻ 重试`, 'error', 6000);
        else if (finishedInRun && moreComing) toast('当前作品已完成，等待下一个作品下载…');
        else if (finishedInRun) {
          toast(doneFolders.length > 1 ? `全部 ${doneFolders.length} 部作品翻译完成！` : `全部完成！已保存到「${doneFolders[0] || folderName.value}」`, 'ok', 5000);
          stamp.value = true;
          setTimeout(() => { stamp.value = false; }, theme.value === 'island' ? 2600 : 1600);
        }
        stopping.value = false;
      }
    }

    function stop() {
      stopping.value = true;
      if (abort) abort.abort();
    }

    function retry(i) {
      const p = pages[i];
      p.status = 'queued'; p.progress = 0; p.error = '';
      start(false);
    }

    /* ---------- 文件夹 ---------- */
    async function openFolder(folder) {
      const r = await fetch('/studio/api/open-folder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(folder ? { folder } : {}),
      });
      if (!r.ok) toast('打开文件夹失败', 'error');
    }
    const zipHref = (folder) => '/studio/api/zip?folder=' + encodeURIComponent(folder);

    /* ---------- 查看 ---------- */
    const current = computed(() => pages[viewer.index] || {});
    function openViewer(i) {
      viewer.index = i; viewer.open = true; viewer.split = 50;
      viewer.mode = pages[i].resultUrl ? 'compare' : 'original';
    }
    const closeViewer = () => { viewer.open = false; };
    function step(d) {
      const i = viewer.index + d;
      if (i < 0 || i >= pages.length) return;
      viewer.index = i;
      if (!pages[i].resultUrl) viewer.mode = 'original';
      else if (viewer.mode === 'original') viewer.mode = 'compare';
    }
    function dragSplit(e) {
      const frame = e.currentTarget;
      const move = (ev) => {
        const r = frame.getBoundingClientRect();
        viewer.split = Math.min(100, Math.max(0, ((ev.clientX - r.left) / r.width) * 100));
      };
      move(e);
      frame.setPointerCapture(e.pointerId);
      frame.onpointermove = move;
      frame.onpointerup = () => { frame.onpointermove = null; frame.onpointerup = null; };
    }
    const downloadName = (p) => (p.name || 'page').replace(/\.[^.]+$/, '') + '_译.png';

    function onKey(e) {
      if (settings.open && e.key === 'Escape') { settings.open = false; return; }
      if (!viewer.open) return;
      if (e.key === 'Escape') closeViewer();
      else if (e.key === 'ArrowLeft') step(-1);
      else if (e.key === 'ArrowRight') step(1);
      else if (e.key === ' ' && current.value.resultUrl) {
        e.preventDefault();
        viewer.mode = viewer.mode === 'original' ? 'result' : 'original';
      }
    }

    /* ---------- 设置 ---------- */
    function openSettings() {
      settings.key = ''; settings.showKey = false; settings.model = status.deepseek_model; settings.open = true;
      refreshSites();
    }
    async function saveSettings() {
      settings.saving = true;
      try {
        const body = { deepseek_model: settings.model };
        if (settings.key) body.deepseek_api_key = settings.key;
        const r = await fetch('/studio/api/settings', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || '保存失败');
        settings.open = false; settings.key = '';
        toast(data.restarted ? '已保存，翻译引擎正在重启…' : '设置没有变化', 'ok');
        status.engine_ready = false;
        await refreshStatus();
      } catch (err) {
        toast(String(err.message || err), 'error');
      } finally {
        settings.saving = false;
      }
    }

    /* ---------- 网站账号：Pixiv ---------- */
    async function refreshSites() {
      try { Object.assign(sites, await (await fetch('/studio/api/sites')).json()); } catch {}
    }
    async function postJson(url, body) {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || '操作失败');
      return data;
    }
    async function pixivOpenLogin() {
      pixiv.busy = true;
      try {
        const data = await postJson('/studio/api/pixiv/start');
        window.open(data.url, '_blank', 'noopener');
        pixiv.step = 2;
      } catch (err) { toast(String(err.message || err), 'error'); } finally { pixiv.busy = false; }
    }
    async function pixivFinish() {
      if (!pixiv.code.trim()) return;
      pixiv.busy = true;
      try {
        await postJson('/studio/api/pixiv/finish', { code: pixiv.code });
        Object.assign(pixiv, { open: false, step: 1, code: '' });
        await refreshSites();
        toast('Pixiv 授权成功', 'ok');
        imports.forEach((j) => { if (j.status === 'error' && /Pixiv/.test(j.error)) retryImport(j); });
      } catch (err) { toast(String(err.message || err), 'error', 6000); } finally { pixiv.busy = false; }
    }
    async function pixivSaveToken() {
      if (!pixiv.token.trim()) return;
      pixiv.busy = true;
      try {
        await postJson('/studio/api/pixiv/token', { token: pixiv.token });
        Object.assign(pixiv, { open: false, token: '' });
        await refreshSites();
        toast('Pixiv 授权成功', 'ok');
      } catch (err) { toast(String(err.message || err), 'error'); } finally { pixiv.busy = false; }
    }
    async function pixivSaveCookie() {
      if (!pixiv.cookie.trim()) return;
      pixiv.busy = true;
      try {
        await postJson('/studio/api/pixiv/cookie', { cookie: pixiv.cookie });
        Object.assign(pixiv, { open: false, cookie: '' });
        await refreshSites();
        toast('Pixiv Cookie 已保存', 'ok');
        imports.forEach((j) => { if (j.status === 'error' && /Pixiv/.test(j.error)) retryImport(j); });
      } catch (err) { toast(String(err.message || err), 'error'); } finally { pixiv.busy = false; }
    }
    async function ehSave() {
      eh.busy = true;
      try {
        await postJson('/studio/api/eh/cookie', { member_id: eh.member_id, pass_hash: eh.pass_hash, igneous: eh.igneous });
        Object.assign(eh, { open: false, member_id: '', pass_hash: '', igneous: '' });
        await refreshSites();
        toast('E 站 Cookie 已保存', 'ok');
        imports.forEach((j) => { if (j.status === 'error' && /E 站/.test(j.error)) retryImport(j); });
      } catch (err) { toast(String(err.message || err), 'error'); } finally { eh.busy = false; }
    }
    async function ehRemove() {
      try { await postJson('/studio/api/eh/cookie', {}); await refreshSites(); toast('已移除 E 站 Cookie'); }
      catch (err) { toast(String(err.message || err), 'error'); }
    }
    async function pixivRemove() {
      try { await postJson('/studio/api/pixiv/token', { token: null }); await refreshSites(); toast('已移除 Pixiv 授权'); }
      catch (err) { toast(String(err.message || err), 'error'); }
    }

    /* ---------- 保存位置 ---------- */
    async function setOutputRoot(path) {
      const r = await fetch('/studio/api/output-root', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || '设置失败');
      status.output_root = data.output_root;
      toast(path ? '保存位置已更新' : '已恢复默认保存位置', 'ok');
    }
    async function pickOutputRoot() {
      settings.picking = true;
      try {
        const r = await fetch('/studio/api/pick-folder', { method: 'POST' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || '无法打开选择窗口');
        if (data.path) await setOutputRoot(data.path);
      } catch (err) {
        toast(String(err.message || err), 'error');
      } finally {
        settings.picking = false;
      }
    }
    async function resetOutputRoot() {
      try { await setOutputRoot(null); } catch (err) { toast(String(err.message || err), 'error'); }
    }
    async function openFolderRoot() {
      const r = await fetch('/studio/api/open-folder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
      if (!r.ok) toast('打开文件夹失败', 'error');
    }

    /* ---------- 派生状态 ---------- */
    const counts = computed(() => {
      const c = { queued: 0, running: 0, done: 0, skipped: 0, error: 0 };
      pages.forEach((p) => { c[p.status]++; });
      c.done += c.skipped;
      return c;
    });
    const overallProgress = computed(() => {
      if (!pages.length) return 0;
      const sum = pages.reduce((s, p) => s + (p.status === 'done' || p.status === 'skipped' ? 100 : p.status === 'running' ? p.progress : 0), 0);
      return sum / pages.length;
    });
    const etaText = computed(() => {
      const left = counts.value.queued + counts.value.running;
      if (!finishedInRun || !left) return '';
      const per = (performance.now() - startedAt) / finishedInRun / 1000;
      const sec = Math.round(per * left);
      return sec >= 60 ? `预计还需 ${Math.ceil(sec / 60)} 分钟` : `预计还需 ${sec} 秒`;
    });
    const pending = computed(() => counts.value.queued + counts.value.error);
    const pendingCount = computed(() => counts.value.queued + counts.value.running + counts.value.error);
    const groups = computed(() => {
      const map = new Map();
      for (const p of pages) {
        if (!map.has(p.folder)) map.set(p.folder, { folder: p.folder, total: 0, done: 0, error: 0, active: 0 });
        const g = map.get(p.folder);
        g.total++;
        if (p.status === 'done' || p.status === 'skipped') g.done++;
        else if (p.status === 'error') g.error++;
        else g.active++;
      }
      return [...map.values()];
    });
    const groupOf = (folder) => groups.value.find((g) => g.folder === folder) || { total: 0, done: 0, error: 0, active: 0 };
    const summaryTitle = computed(() => (groups.value.length > 1 ? `翻译队列 · ${groups.value.length} 部作品` : (groups.value[0] || {}).folder || folderName.value));
    const visiblePages = computed(() => pages.map((p, i) => ({ p, i })).filter(({ p }) =>
      filter.value === 'all' ? true
        : filter.value === 'error' ? p.status === 'error'
        : p.status !== 'done' && p.status !== 'skipped'));
    watch([() => counts.value.error, pendingCount], ([err, pend]) => {
      if ((filter.value === 'error' && !err) || (filter.value === 'pending' && !pend)) filter.value = 'all';
    });
    function scrollToRunning() {
      const i = pages.findIndex((p) => p.status === 'running');
      if (i < 0 || !gridScroll.value) return;
      filter.value = 'all';
      nextTick(() => {
        const el = gridScroll.value.querySelector(`[data-index="${i}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
    const canStart = computed(() => pending.value > 0 && status.engine_ready);
    const importActive = computed(() => imports.some((j) => j.status === 'queued' || ACTIVE_IMPORT.includes(j.status)));
    const startLabel = computed(() => {
      if (!pages.length) return '开始翻译';
      if (!pending.value) return '全部完成';
      return counts.value.error && !counts.value.queued ? `重试失败的 ${counts.value.error} 页` : `开始翻译（${pending.value} 页）`;
    });
    const startHint = computed(() => {
      if (status.offline) return '连接不到翻译服务，请重新运行启动程序';
      if (status.loaded && !status.engine_ready) return '翻译引擎正在启动，通常需要 30–60 秒';
      if (!pages.length) return '先在左侧添加要翻译的图片';
      return '';
    });
    const engineChip = computed(() => {
      const dev = status.use_gpu ? (status.gpu_name || 'GPU') : 'CPU';
      if (!status.loaded) return { cls: 'wait', text: '连接中…', title: '' };
      if (status.offline) return { cls: 'down', text: '服务未运行', title: '请重新运行启动程序' };
      if (!status.engine_ready) return { cls: 'wait', text: '引擎启动中…', title: '首次加载模型需要一点时间' };
      return { cls: 'ok', text: `引擎就绪 · ${dev}`, title: `计算设备：${dev}` };
    });
    const qualityHint = computed(() => QUALITY[options.quality].hint);
    const outputPath = computed(() => {
      const root = status.output_root || 'output';
      const sep = root.includes('\\') ? '\\' : '/';
      return root + sep + (folderName.value || todayName());
    });
    const zipUrl = computed(() => counts.value.done ? '/studio/api/zip?folder=' + encodeURIComponent(folderName.value) : undefined);

    onMounted(() => {
      refreshStatus();
      statusTimer = setInterval(refreshStatus, 3000);
      window.addEventListener('keydown', onKey);
      window.addEventListener('beforeunload', (e) => { if (running.value) { e.preventDefault(); e.returnValue = ''; } });
    });
    onBeforeUnmount(() => { clearInterval(statusTimer); window.removeEventListener('keydown', onKey); });

    return {
      pages, options, folderName, status, running, stopping, dragging, toasts, viewer, settings,
      fileInput, folderInput, stage, gridScroll, filter, stamp, theme, clock, mode, modeLabel, cycleMode, pendingCount, visiblePages, scrollToRunning, importUrl, imports, importActive, importFromUrl, importText, retryImport, removeImport, groups, groupOf, summaryTitle, zipHref, sites, pixiv, pixivOpenLogin, pixivFinish, pixivSaveToken, pixivSaveCookie, pixivRemove, eh, ehSave, ehRemove, current, counts, overallProgress, etaText, canStart, startLabel, startHint,
      engineChip, qualityHint, outputPath, zipUrl,
      languages: LANGUAGES,
      thumbSizes: [{ value: 's', label: '小' }, { value: 'm', label: '中' }, { value: 'l', label: '大' }],
      directions: [{ value: 'auto', label: '自动' }, { value: 'vertical', label: '竖排' }, { value: 'horizontal', label: '横排' }],
      qualities: Object.entries(QUALITY).map(([value, q]) => ({ value, label: q.label, hint: q.hint })),
      onDrop, onPick, pickFiles, pickFolder, removePage, clearAll, start, stop, retry, openFolder,
      openViewer, closeViewer, step, dragSplit, downloadName, openSettings, saveSettings,
      pickOutputRoot, resetOutputRoot, openFolderRoot,
    };
  },
}).mount('#app');
