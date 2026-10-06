<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { WEBUI_API_BASE_URL } from '$lib/constants';
  import Modal from '$lib/components/common/Modal.svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import type { Props } from 'tippy.js';
  export let item;
  export let ondelete: () => void;
  let thumb = '', url = '', error = '', thumbError = '', imageError = '';
  let show = false, loading = false, deleting = false;
  let promptExpanded = false;
  const promptTooltip: Partial<Props> = {
    content: item.prompt,
    maxWidth: 360,
    onShow(instance) {
      const content = instance.popper.querySelector<HTMLElement>('.tippy-content');
      if (content) {
        content.style.whiteSpace = 'pre-wrap';
        content.style.overflowWrap = 'anywhere';
        content.style.maxHeight = '240px';
        content.style.overflowY = 'auto';
      }
    }
  };
  const controller = new AbortController();
  async function readImage(path: string) {
    const response = await fetch(`${WEBUI_API_BASE_URL}${path}`, {
      headers: { Authorization: `Bearer ${localStorage.token}` }, signal: controller.signal
    });
    if (!response.ok) throw new Error('图片读取失败，请重试');
    const blob = await response.blob();
    return controller.signal.aborted ? '' : URL.createObjectURL(blob);
  }
  async function loadThumbnail() {
    thumbError = '';
    try { thumb = await readImage(`/image-studio/images/${item.id}/thumbnail`); }
    catch { if (!controller.signal.aborted) thumbError = '缩略图不可用'; }
  }
  async function open() {
    show = true;
    if (url || loading) return;
    loading = true; imageError = '';
    try { url = await readImage(`/files/${item.file_id}/content`); }
    catch { if (!controller.signal.aborted) imageError = '图片读取失败，请重试'; }
    finally { loading = false; }
  }
  async function remove() {
    if (deleting) return;
    deleting = true; error = '';
    try {
      const response = await fetch(`${WEBUI_API_BASE_URL}/image-studio/images/${item.id}`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${localStorage.token}` }
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(typeof data.detail === 'string' ? data.detail : '删除失败，请重试');
      }
      show = false;
      ondelete();
    } catch (e) { error = e instanceof Error ? e.message : '删除失败，请重试'; }
    finally { deleting = false; }
  }
  onMount(() => { loadThumbnail(); });
  onDestroy(() => {
    controller.abort();
    if (thumb) URL.revokeObjectURL(thumb);
    if (url) URL.revokeObjectURL(url);
  });
</script>

<li class="min-w-0 border-b border-gray-200 py-2 dark:border-gray-800">
  <div class="flex items-center justify-between gap-3">
    <Tooltip content={item.prompt} allowHTML={false} touch={false} className="shrink-0" interactive={true} tippyOptions={promptTooltip}>
    <button type="button" class="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-100 text-xs focus-visible:ring-2 focus-visible:ring-blue-500 dark:bg-gray-800" aria-label="查看大图和提示词" on:click={open}>
      {#if thumb}<img src={thumb} alt="生成图片缩略图" class="h-full w-full object-contain" />
      {:else}<span>{thumbError || '加载中…'}</span>{/if}
    </button>
    </Tooltip>
    <div class="flex flex-wrap items-center justify-end gap-1">
    <button type="button" class="rounded-lg px-2 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800" aria-expanded={promptExpanded} aria-controls={`image-prompt-${item.id}`} on:click={() => promptExpanded = !promptExpanded}>{promptExpanded ? '收起 Prompt' : 'Prompt'}</button>
    <button type="button" class="rounded-lg px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-gray-800" title="从磁盘永久删除原图和生成记录" disabled={deleting} on:click={remove}>{deleting ? '删除中…' : '删除'}</button>
    </div>
  </div>
  <div id={`image-prompt-${item.id}`} hidden={!promptExpanded} class="mt-2 whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-850">{item.prompt}</div>
  {#if error}<p role="alert" class="mt-2 text-sm text-red-600">{error}</p>{/if}
</li>

<Modal bind:show size="lg">
  <div class="space-y-4 p-4 sm:p-6">
    <div class="flex items-center justify-between gap-4"><h3 class="font-medium">图片与提示词</h3><button type="button" class="rounded-lg px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => show = false}>关闭</button></div>
    {#if url}<a href={url} target="_blank" rel="noreferrer" aria-label="打开原图"><img src={url} alt={item.prompt} class="max-h-[65vh] w-full rounded-lg object-contain" /></a>
    {:else if loading}<p role="status" class="py-10 text-center text-sm text-gray-500">正在加载原图…</p>
    {:else if imageError}<div role="alert" class="text-sm text-red-600">{imageError}<button type="button" class="ml-3 underline" on:click={open}>重试</button></div>{/if}
    <p class="whitespace-pre-wrap break-words text-sm">{item.prompt}</p>
    <p class="text-xs text-gray-500">{item.model.endsWith('turbo6') ? 'Turbo · 6 步' : '基础版 · 40 步'} · {item.width} × {item.height} · {item.seconds.toFixed(1)} 秒 · seed {item.seed}</p>
    {#if url}<a class="inline-block text-sm underline" href={url} download={`qwen-${item.seed}.png`}>下载原图</a>{/if}
  </div>
</Modal>
