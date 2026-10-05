<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { WEBUI_API_BASE_URL } from '$lib/constants';
  export let item;
  export let preview = false;
  let url = '';
  let error = '';
  let loading = false;
  const controller = new AbortController();
  async function load() {
    loading = true;
    error = '';
    try {
      const response = await fetch(`${WEBUI_API_BASE_URL}/files/${item.file_id}/content`, {
        headers: { Authorization: `Bearer ${localStorage.token}` }, signal: controller.signal
      });
      if (!response.ok) throw new Error('图片读取失败，请重试');
      const blob = await response.blob();
      if (!controller.signal.aborted) url = URL.createObjectURL(blob);
    } catch (e) {
      if (!controller.signal.aborted) error = `${e}`;
    } finally { loading = false; }
  }
  onMount(() => { if (preview) load(); });
  onDestroy(() => { controller.abort(); if (url) URL.revokeObjectURL(url); });
</script>

<article class="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
  {#if url}
    <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={item.prompt} class="max-h-96 w-full rounded-lg object-contain" /></a>
    <a class="inline-block text-sm underline" href={url} download={`qwen-${item.seed}.png`}>下载原图</a>
  {:else}
    <button class="w-full rounded-lg bg-gray-100 p-8 text-sm dark:bg-gray-800 disabled:opacity-50" disabled={loading} on:click={load}>{loading ? '正在加载图片…' : '查看图片'}</button>
  {/if}
  {#if error}<p role="alert" class="text-sm text-red-600">{error}</p>{/if}
  <p class="whitespace-pre-wrap break-words text-sm">{item.prompt}</p>
  <p class="text-xs text-gray-500">{item.model.endsWith('turbo6') ? 'Turbo · 6 步' : '基础版 · 40 步'} · {item.width} × {item.height} · {item.seconds.toFixed(1)} 秒 · seed {item.seed}</p>
</article>
