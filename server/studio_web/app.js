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
  ['CHS', '简体中文'], ['CHT', '繁体中文'], ['ENG', '英语'], ['JPN', '日语'], ['KOR', '韩语'],
  ['FRA', '法语'], ['DEU', '德语'], ['ESP', '西班牙语'], ['RUS', '俄语'], ['VIN', '越南语'], ['THA', '泰语'],
].map(([code, name]) => ({ code, name }));

const QUALITY = {
  fast: { label: '快速', size: 1536, hint: '适合小图或预览，速度最快' },
  standard: { label: '标准', size: 2048, hint: '大多数漫画的推荐设置' },
  fine: { label: '精细', size: 2560, hint: '高分辨率扫描图，文字很小时使用' },
};

const DEFAULT_OPTIONS = {
  translator: 'deepseek', targetLang: 'CHS', direction: 'auto', quality: 'standard',
  fontOffset: 0, inpainter: 'lama_large', ocr: '48px', noBorder: false, autoTranslate: true,
};

function loadOptions() {
  try {
    return { ...DEFAULT_OPTIONS, ...JSON.parse(localStorage.getItem(STORE_KEY) || '{}') };
  } catch { return { ...DEFAULT_OPTIONS }; }
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
    const settings = reactive({ open: false, key: '', showKey: false, model: 'deepseek-flash', saving: false });
    const fileInput = ref(null), folderInput = ref(null), stage = ref(null);
    const importUrl = ref('');
    const importJob = ref(null);
    const importing = computed(() => !!importJob.value && importJob.value.status !== 'error');
    let abort = null, nextId = 1, statusTimer = null, startedAt = 0, finishedInRun = 0;

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
    function addFiles(files, fromFolder) {
      const imgs = [...files].filter((f) => IMAGE_RE.test(f.name))
        .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name, 'zh', { numeric: true }));
      if (!imgs.length) { toast('没有找到图片文件（支持 PNG / JPG / WEBP / BMP）', 'error'); return; }
      if (!pages.length && fromFolder) folderName.value = fromFolder;
      for (const f of imgs) {
        pages.push({ id: nextId++, file: f, name: f.name, srcUrl: URL.createObjectURL(f), resultUrl: '',
          status: 'queued', stageText: '', progress: 0, error: '', ms: 0 });
      }
      toast(`已添加 ${imgs.length} 页`);
    }

    async function onDrop(e) {
      dragging.value = false;
      if (running.value) { toast('正在翻译，请稍后再添加', 'error'); return; }
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
      folderName.value = todayName();
    }

    /* ---------- 从网页链接导入 ---------- */
    async function importFromUrl() {
      const url = importUrl.value;
      if (!url || importing.value || running.value) return;
      if (!/^https?:\/\//i.test(url)) { toast('请输入以 http:// 或 https:// 开头的网址', 'error'); return; }
      importJob.value = { status: 'probing', title: '', total: 0, downloaded: 0, error: '' };
      try {
        const r = await fetch('/studio/api/import', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || '无法开始下载');
        let job;
        for (;;) {
          await new Promise((res) => setTimeout(res, 1000));
          const s = await fetch('/studio/api/import/' + data.id);
          if (!s.ok) throw new Error('下载任务丢失，请重试');
          job = await s.json();
          importJob.value = job;
          if (job.status === 'done') break;
          if (job.status === 'error') return;
        }
        importJob.value = { ...job, status: 'loading' };
        const files = [];
        for (const name of job.files) {
          const b = await fetch(`/studio/api/import/${data.id}/file/${encodeURIComponent(name)}`).then((x) => x.blob());
          files.push(new File([b], name, { type: b.type }));
        }
        if (!pages.length) folderName.value = job.title;
        addFiles(files);
        importJob.value = null;
        importUrl.value = '';
        if (options.autoTranslate) {
          if (!status.engine_ready) toast('翻译引擎还在启动，就绪后点「开始翻译」即可', 'info', 5000);
          else start();
        }
      } catch (err) {
        importJob.value = { status: 'error', error: String(err.message || err) };
      }
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
      form.append('folder', folderName.value || todayName());
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

    async function start() {
      if (options.translator === 'deepseek' && !status.deepseek_key_set) { openSettings(); return; }
      running.value = true; stopping.value = false;
      startedAt = performance.now(); finishedInRun = 0;
      try {
        for (const p of pages) {
          if (stopping.value) break;
          if (p.status === 'queued' || p.status === 'error') await translatePage(p);
        }
      } finally {
        running.value = false;
        const failed = counts.value.error;
        if (stopping.value) toast('已停止');
        else if (failed) toast(`完成，但有 ${failed} 页失败，可点卡片右上角 ↻ 重试`, 'error', 6000);
        else if (finishedInRun) toast(`全部完成！已保存到「${folderName.value}」`, 'ok', 5000);
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
      start();
    }

    /* ---------- 文件夹 ---------- */
    async function openFolder() {
      const r = await fetch('/studio/api/open-folder', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder: folderName.value }),
      });
      if (!r.ok) toast('打开文件夹失败', 'error');
    }

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
    const canStart = computed(() => pending.value > 0 && status.engine_ready);
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
      fileInput, folderInput, stage, importUrl, importJob, importing, importFromUrl, current, counts, overallProgress, etaText, canStart, startLabel, startHint,
      engineChip, qualityHint, outputPath, zipUrl,
      languages: LANGUAGES,
      directions: [{ value: 'auto', label: '自动' }, { value: 'vertical', label: '竖排' }, { value: 'horizontal', label: '横排' }],
      qualities: Object.entries(QUALITY).map(([value, q]) => ({ value, label: q.label, hint: q.hint })),
      onDrop, onPick, pickFiles, pickFolder, removePage, clearAll, start, stop, retry, openFolder,
      openViewer, closeViewer, step, dragSplit, downloadName, openSettings, saveSettings,
    };
  },
}).mount('#app');
