<script lang="ts">
	import { onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import WorkingIndicator from './WorkingIndicator.svelte';
	import { studio, post, type Job, type Delivery } from '$lib/apis/audio-studio';
	export let job: Job;
	export let canSend = false;
	export let delivery: Delivery | undefined = undefined;
	export let refresh: () => Promise<void>;
	export let onvideo: (job: Job) => void = () => {};
	let url = '';
	let busy = false;
	let sending = false;
	let disposed = false;
	const labels: Record<string, string> = {
		queued: '等待生成',
		running: '正在生成',
		completed: '已完成',
		failed: '生成失败',
		interrupted: '生成中断'
	};
	async function audio(download = false, format = 'mp3') {
		busy = true;
		try {
			const blob = await studio(`/jobs/${job.id}/audio?format=${format}`, {}, true);
			if (disposed) return;
			const next = URL.createObjectURL(blob);
			if (download) {
				const a = document.createElement('a');
				a.href = next;
				a.download = `${job.title}.${format}`;
				a.click();
				setTimeout(() => URL.revokeObjectURL(next), 10000);
			} else {
				if (url) URL.revokeObjectURL(url);
				url = next;
			}
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	async function send() {
		sending = true;
		try {
			const result = await post(`/jobs/${job.id}/telegram`, {});
			if (result.status === 'sent') toast.success('已发送到 Telegram');
			else toast.error(result.error || '发送失败');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			sending = false;
			await refresh();
		}
	}
	async function resolve(received: boolean) {
		if (!delivery) return;
		try {
			await post(`/deliveries/${delivery.id}/resolve`, { received });
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		}
	}
	async function retry() {
		busy = true;
		try {
			await post('/jobs', {
				text: job.text,
				voice_id: job.voice_id,
				speed: job.speed,
				title: job.title
			});
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	async function remove() {
		if (
			!confirm(
				`删除播报「${job.title}」及本地 WAV、MP3 文件？此操作无法恢复。已创建的视频使用独立素材副本，不受影响。`
			)
		)
			return;
		busy = true;
		try {
			const result = await studio(`/jobs/${job.id}`, { method: 'DELETE' });
			if (result.cleanup_pending) toast.info('播报已删除，磁盘清理将在后台重试');
			else toast.success(`播报已删除，释放 ${(result.freed_bytes / 1024 / 1024).toFixed(1)} MB`);
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}

	onDestroy(() => {
		disposed = true;
		if (url) URL.revokeObjectURL(url);
	});
</script>

<article class="relative space-y-3 border-b border-gray-100 py-5 dark:border-gray-800">
	<button
		type="button"
		on:click={remove}
		aria-label="删除播报"
		title="删除"
		disabled={busy ||
			sending ||
			!['completed', 'failed', 'interrupted'].includes(job.status) ||
			['sending', 'unknown'].includes(delivery?.status ?? '')}
		class="absolute right-0 top-3 inline-flex size-7 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-red-950/30 dark:hover:text-red-400"
	>
		<svg
			aria-hidden="true"
			class="size-4"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg
		>
	</button>
	<div class="!mt-0 flex items-start justify-between gap-3 pr-9">
		<div class="min-w-0">
			<h3 class="break-words font-medium">{job.title}</h3>
			<p class="mt-1 text-xs text-gray-500">
				{job.voice_name} · {job.speed}× · {new Date(job.created_at * 1000).toLocaleString()}
			</p>
		</div>
		<span class="inline-flex shrink-0 items-center gap-2 text-xs text-gray-500" role="status"
			>{#if ['queued', 'running'].includes(job.status)}<WorkingIndicator />{/if}{labels[
				job.status
			] || job.status}</span
		>
	</div>
	{#if job.credit}<p class="text-xs text-gray-500">发布署名：{job.credit}</p>{/if}
	{#if job.error}<p class="text-sm text-red-600 dark:text-red-400">{job.error}</p>{/if}
	{#if job.status === 'running'}<p class="text-xs text-gray-500">
			首次加载模型可能需要稍等，可以离开页面，稍后返回查看。
		</p>{/if}
	{#if url}<audio src={url} controls class="w-full"><track kind="captions" /></audio>{/if}
	{#if job.status === 'completed'}<div class="flex flex-wrap gap-x-4 gap-y-2 text-sm">
			<button on:click={() => onvideo(job)}>生成数字人视频</button>
			<button disabled={busy} on:click={() => audio()}>试听</button><button
				disabled={busy}
				on:click={() => audio(true)}>下载 MP3</button
			><button disabled={busy} on:click={() => audio(true, 'wav')}>下载 WAV</button
			>{#if canSend}<button
					disabled={sending ||
						delivery?.status === 'sent' ||
						delivery?.status === 'sending' ||
						delivery?.status === 'unknown'}
					on:click={send}
					>{sending || delivery?.status === 'sending'
						? '正在发送…'
						: delivery?.status === 'sent'
							? '已发送 TG'
							: '发送 Telegram'}</button
				>{/if}
		</div>{/if}
	{#if ['failed', 'interrupted'].includes(job.status)}<button
			class="text-sm underline"
			disabled={busy}
			on:click={retry}>重新生成</button
		>{/if}
	{#if delivery?.status === 'failed'}<p class="text-sm text-red-600">
			{delivery.error || '发送失败，可重试'}
		</p>{/if}
	{#if delivery?.status === 'unknown'}<div
			class="rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-900"
		>
			<p>上次发送结果待确认，请先查看 Telegram，避免重复发送。</p>
			<div class="mt-2 flex gap-4">
				<button class="underline" on:click={() => resolve(true)}>已收到</button><button
					class="underline"
					on:click={() => resolve(false)}>确认未收到，允许重试</button
				>
			</div>
		</div>{/if}
</article>
