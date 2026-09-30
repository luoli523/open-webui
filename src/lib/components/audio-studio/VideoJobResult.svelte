<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { downloadVideo, videoPost, type VideoJob, type Receipt } from '$lib/apis/video-studio';
	import StudioMedia from './StudioMedia.svelte';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let job: VideoJob;
	export let delivery: Receipt | undefined = undefined;
	export let isAdmin = false;
	export let hasFinal = false;
	export let refresh: () => Promise<void>;
	let busy = false;
	let externalId = '';
	$: working = ['queued', 'preparing', 'submitting', 'processing', 'downloading'].includes(
		job.status
	);
	const labels: Record<string, string> = {
		queued: '等待生成',
		preparing: '准备素材',
		submitting: '提交中',
		processing: '引擎生成中',
		downloading: '下载并检查视频',
		completed: '已完成',
		failed: '处理失败',
		submission_unknown: '提交结果待核实'
	};
	async function action(path: string, data: unknown = {}) {
		busy = true;
		try {
			await videoPost(path, data);
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	async function final() {
		if (
			!confirm(
				`确认「${job.title}」预览中的人物、声音和口型效果？\n将使用同一素材生成 ${Math.ceil(job.full_duration)} 秒完整版，HeyGen 会再次计费。`
			)
		)
			return;
		await action(`/jobs/${job.id}/final`, { fingerprint: job.fingerprint, consent: true });
	}
	async function retry() {
		if (
			job.retry_requires_payment &&
			!confirm('重新提交视频生成可能再次产生费用。请先核对引擎后台的失败原因和扣费，确认继续？')
		)
			return;
		await action(`/jobs/${job.id}/retry`, { consent: job.retry_requires_payment });
	}
	async function download() {
		busy = true;
		try {
			await downloadVideo(job);
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	async function notCreated() {
		if (
			!confirm(
				`请先在 HeyGen 后台搜索 OWUI-${job.id}-${job.attempt}。\n确定没有创建这个任务？确认后才允许重新生成，以免重复计费。`
			)
		)
			return;
		await action(`/jobs/${job.id}/resolve`, { confirmed_not_created: true });
	}
</script>

<article
	class="min-w-0 space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-800"
	aria-busy={busy || working}
>
	<div class="flex flex-wrap items-start justify-between gap-2">
		<div class="min-w-0">
			<h3 class="break-words font-medium">{job.title}</h3>
			{#if job.credit}<p class="text-xs text-gray-500">发布署名：{job.credit}</p>{/if}
			<p class="mt-1 text-xs text-gray-500">
				{job.stage === 'preview' ? '短预览' : '完整版'} · {job.portrait_name} · {job.resolution} · {job.aspect_ratio}
				· {Math.ceil(job.duration)} 秒
			</p>
		</div>
		<span class="inline-flex items-center gap-2 text-xs text-gray-500" role="status"
			>{#if working || busy}<WorkingIndicator />{/if}{busy
				? '正在处理…'
				: (labels[job.status] ?? job.status)}</span
		>
	</div>
	<p class="text-xs text-gray-500">
		{job.provider_id} · {new Date(job.created_at * 1000).toLocaleString()}
	</p>
	{#if job.error}<p role="alert" class="break-words text-sm text-red-600 dark:text-red-400">
			{job.error}
		</p>{/if}
	{#if job.status === 'completed'}
		<StudioMedia path={`/jobs/${job.id}/video`} kind="video" version={String(job.attempt)} />
		<div class="flex flex-wrap gap-4 text-sm">
			{#if job.stage === 'preview'}<button
					disabled={busy || hasFinal}
					on:click={final}
					class="font-medium underline disabled:opacity-40"
					>{hasFinal ? '已创建完整版' : '确认预览，付费生成完整版'}</button
				>{/if}
			<button disabled={busy} on:click={download} class="underline">下载 MP4</button>
			{#if isAdmin}<button
					disabled={busy || ['sending', 'sent', 'unknown'].includes(delivery?.status ?? '')}
					on:click={() => action(`/jobs/${job.id}/telegram`)}
					class="underline disabled:opacity-40"
					>{delivery?.status === 'sent'
						? '已发送 TG'
						: delivery?.status === 'sending'
							? '正在发送…'
							: '发送 TG'}</button
				>{/if}
		</div>
	{:else if job.status === 'failed'}
		<button disabled={busy} class="text-sm underline" on:click={retry}
			>{job.retry_requires_payment
				? '确认费用后重新生成'
				: '继续查询 / 重试下载（不重新生成）'}</button
		>
	{:else if job.status === 'submission_unknown'}
		<div class="space-y-3 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
			<p>
				为避免重复扣费，此任务不会自动重提。{isAdmin
					? '请在 HeyGen 后台核对。'
					: '请联系管理员核对。'}
			</p>
			<p class="break-all text-xs">后台任务标题：OWUI-{job.id}-{job.attempt}</p>
			{#if isAdmin}
				<label class="block"
					>已创建的视频 ID<input
						bind:value={externalId}
						class="mt-1 w-full rounded border border-gray-300 bg-transparent p-2 dark:border-gray-700"
					/></label
				>
				<div class="flex flex-wrap gap-4">
					<button
						disabled={busy || !externalId.trim()}
						class="underline"
						on:click={() => action(`/jobs/${job.id}/resolve`, { external_id: externalId.trim() })}
						>关联并继续查询</button
					><button disabled={busy} class="underline" on:click={notCreated}
						>已核对，确实未创建</button
					>
				</div>
			{/if}
		</div>
	{:else}<p class="text-xs leading-5 text-gray-500">
			可以离开页面，稍后返回查看。已提交的云端任务无法在此取消。
		</p>{/if}
	{#if delivery?.error}<p class="text-sm text-amber-700 dark:text-amber-400">
			{delivery.error}
		</p>{/if}
	{#if isAdmin && delivery?.status === 'unknown'}
		<div class="flex flex-wrap gap-4 text-sm">
			<button
				disabled={busy}
				class="underline"
				on:click={() => action(`/deliveries/${delivery!.id}/resolve`, { received: true })}
				>TG 已收到</button
			><button
				disabled={busy}
				class="underline"
				on:click={() => {
					if (confirm('已在 Telegram 核对，确定未收到此视频？'))
						action(`/deliveries/${delivery!.id}/resolve`, { received: false });
				}}>确认未收到，允许重发</button
			>
		</div>
	{/if}
</article>
