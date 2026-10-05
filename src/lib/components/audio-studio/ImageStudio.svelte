<script lang="ts">
  import { onMount } from 'svelte';
  import { WEBUI_API_BASE_URL } from '$lib/constants';
  import ImageStudioResult from './ImageStudioResult.svelte';
  let prompt = '';
  let model = 'qwen-image-2.1-turbo6';
  let seed = '';
  let reference: File | null = null;
  let config = {base_url: 'http://127.0.0.1:28093', enabled: false, configured: false, online: false, busy: false};
  let apiKey = '';
  let results: {id: string; file_id: string; prompt: string; model: string; seed: number; width: number; height: number; seconds: number}[] = [];
  let error = '';
  let loading = true;
  let generating = false;
  let saving = false;
  let started = 0;
  let elapsed = 0;
  async function api(path: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${localStorage.token}`);
    if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
    const response = await fetch(`${WEBUI_API_BASE_URL}/image-studio${path}`, {...options, headers});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请检查输入后重试');
    return data;
  }
  async function refresh() {
    error = '';
    try { [config, results] = await Promise.all([api('/config'), api('/images')]); }
    catch (e) { error = `${e}`; }
    finally { loading = false; }
  }
  async function save() {
    saving = true; error = '';
    try {
      config = await api('/config', {method: 'PUT', body: JSON.stringify({base_url: config.base_url, enabled: config.enabled, ...(apiKey ? {api_key: apiKey} : {})})});
      apiKey = '';
    } catch (e) { error = `${e}`; }
    finally { saving = false; }
  }
  function choose(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    error = '';
    if (file && file.size > 10*1024*1024) { error = '参考图不能超过 10 MB'; input.value = ''; reference = null; return; }
    reference = file || null;
  }
  async function generate() {
    generating = true; error = ''; started = Date.now(); elapsed = 0;
    const timer = setInterval(() => elapsed = Math.floor((Date.now()-started)/1000), 1000);
    try {
      const data = new FormData();
      data.set('prompt', prompt.trim()); data.set('model', model);
      if (seed !== '') data.set('seed', seed);
      if (reference) data.set('image', reference);
      const image = await api('/images', {method: 'POST', body: data});
      results = [image, ...results].slice(0, 50);
    } catch (e) { error = `${e}`; }
    finally { clearInterval(timer); generating = false; }
  }
  onMount(() => { refresh(); });
</script>

<section class="space-y-6">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div><h2 class="font-semibold">4090 图像工作台</h2><p class="mt-1 text-sm text-gray-500">输入描述生成图片，或上传一张参考图修改背景、服装等内容。</p></div>
    <button class="rounded-lg border px-3 py-2 text-sm disabled:opacity-50" disabled={generating} on:click={refresh}>刷新连接</button>
  </div>
  <p role="status" class="text-sm text-gray-500">{loading ? '正在连接…' : config.online ? '4090 已连接' + (config.busy ? ' · 图像任务执行中' : '') : config.enabled ? '4090 暂时不可用，请检查连接设置' : '4090 图像服务尚未启用'}</p>
  <details class="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
    <summary class="cursor-pointer text-sm">4090 连接设置</summary>
    <div class="mt-4 space-y-3">
      <label class="block text-sm">服务地址<input class="mt-1 w-full rounded-lg border bg-transparent p-2" bind:value={config.base_url} /></label>
      <label class="block text-sm">API 密钥<input type="password" autocomplete="new-password" class="mt-1 w-full rounded-lg border bg-transparent p-2" placeholder={config.configured ? '已配置，留空保留' : '输入远端服务密钥'} bind:value={apiKey} /></label>
      <label class="flex items-center gap-2 text-sm"><input type="checkbox" bind:checked={config.enabled} />启用 4090 图像服务</label>
      <button class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-black disabled:opacity-50" disabled={saving || generating} on:click={save}>{saving ? '正在保存…' : '保存连接'}</button>
    </div>
  </details>
  <form class="space-y-4" on:submit|preventDefault={generate}>
    <label class="block text-sm">生成模式<select class="mt-2 w-full rounded-lg border bg-white p-3 dark:bg-gray-900" bind:value={model} disabled={generating}>
      <option value="qwen-image-2.1-turbo6">4090 · Viggle Turbo · 6 步（默认）</option>
      <option value="qwen-image-2.1-base40">4090 · Qwen Image · 40 步</option>
    </select></label>
    <label class="block text-sm">描述你想要的画面<textarea class="mt-2 w-full rounded-lg border bg-transparent p-3" rows="5" maxlength="4000" required bind:value={prompt} disabled={generating} placeholder="例如：设计一张米白色咖啡海报，标题写‘慢下来，喝杯咖啡’。上传参考图后，可写‘保留人物，将背景换成花园’。"></textarea></label>
    <div class="grid gap-4 md:grid-cols-2">
      <label class="block text-sm">参考图（可选，一张，最多 10 MB）<input class="mt-2 block w-full text-sm" type="file" accept="image/png,image/jpeg,image/webp" disabled={generating} on:change={choose} /></label>
      <label class="block text-sm">随机种子（留空自动随机）<input class="mt-2 w-full rounded-lg border bg-transparent p-2" type="text" inputmode="numeric" pattern="[0-9]*" bind:value={seed} disabled={generating} placeholder="例如 42，便于比较两种模式" /></label>
    </div>
    <p class="text-xs text-gray-500">文生图为 1024 × 1024；参考图编辑约 100 万像素，保持参考图宽高比。GPU 与视频任务共用，忙时会提示重试。</p>
    <button class="rounded-lg bg-gray-900 px-5 py-3 text-sm font-medium text-white dark:bg-white dark:text-black disabled:opacity-50" disabled={loading || generating || !config.enabled || !config.online || !prompt.trim()}>{generating ? `正在生成 · ${elapsed} 秒` : reference ? '根据参考图生成' : '生成图片'}</button>
  </form>
  {#if error}<p role="alert" class="rounded-lg border border-red-200 p-3 text-sm text-red-600 dark:text-red-400">{error}</p>{/if}
  <div><h3 class="mb-3 font-medium">最近生成</h3>
    {#if results.length}<ul class="divide-y divide-gray-200 dark:divide-gray-800">{#each results as item (item.id)}<ImageStudioResult {item} ondelete={() => results = results.filter((image) => image.id !== item.id)} />{/each}</ul>
    {:else}<p class="text-sm text-gray-500">生成的图片会保存在这里，支持查看和下载原图。</p>{/if}
  </div>
</section>
