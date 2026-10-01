<script lang="ts">
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		downloadVideo,
		videoStudio,
		videoPost,
		type VideoJob,
		type Receipt
	} from '$lib/apis/video-studio';
	import StudioMedia from './StudioMedia.svelte';
	import CaptionEditor from './CaptionEditor.svelte';
	let captionsOpen = false;
	let captionEditor: CaptionEditor;
	import VideoThumbnail from './VideoThumbnail.svelte';
	let expanded = false;
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let job: VideoJob;
	export let delivery: Receipt | undefined = undefined;
	export let captionDelivery: Receipt | undefined = undefined;
	export let isAdmin = false;
	export let hasFinal = false;
	export let refresh: () => Promise<void>;
	let busy = false;
	let editingTitle = false;
	let draftTitle = '';
	let editRevision = 0;
	let titleInput: HTMLInputElement;
	async function editTitle() {
		draftTitle = job.title;
		editRevision = job.revision;
		editingTitle = true;
		await tick();
		titleInput?.focus();
		titleInput?.select();
	}
	async function saveTitle() {
		if (busy || !draftTitle.trim()) return;
		busy = true;
		try {
			job = await videoStudio(`/jobs/${job.id}`, {
				method: 'PATCH',
				body: JSON.stringify({ title: draftTitle.trim(), revision: editRevision })
			});
			editingTitle = false;
			toast.success('视频名称已更新');
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}

	let externalId = '';
	const progressStages: Record<string, string> = {
		waiting_gpu: '等待 GPU',
		'Encoding prompt': '编码素材',
		Generating: '生成声画',
		'Decoding video': '解码视频',
		'Decoding audio': '解码音频',
		muxing: '合并视频'
	};
	$: working = [
		'queued',
		'preparing',
		'submitting',
		'processing',
		'downloading',
		'cancelling'
	].includes(job.status);
	$: captionWorking =
		job.status === 'completed' && ['queued', 'running'].includes(job.caption_status ?? '');
	$: captionPending = job.status === 'completed' && job.auto_captions && !job.caption_ready;
	$: chosenDelivery = job.caption_ready || job.auto_captions ? captionDelivery : delivery;
	const labels: Record<string, string> = {
		queued: '等待生成',
		preparing: '准备素材',
		submitting: '提交中',
		processing: '引擎生成中',
		downloading: '下载并检查视频',
		completed: '已完成',
		failed: '处理失败',
		cancelled: '已取消',
		cancelling: '正在取消',
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
	async function remove() {
		if (
			!confirm(
				`删除「${job.title}」这条视频记录？\n将清理本地视频、预览音频及无引用的素材，无法恢复。再次生成需要重新提交，云端引擎可能再次计费。`
			)
		)
			return;
		busy = true;
		try {
			const result = await videoStudio(`/jobs/${job.id}`, { method: 'DELETE' });
			if (result.cleanup_pending) toast.info('记录已删除，文件清理将在后台重试');
			else
				toast.success(`视频记录已删除，已释放 ${(result.freed_bytes / 1024 / 1024).toFixed(1)} MB`);
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
				`确认「${job.title}」预览中的人物、声音和口型效果？\n将使用同一素材生成 ${Math.ceil(job.full_duration)} 秒完整版，${job.provider_id === 'local_h3' ? '将在本机分段生成。' : 'HeyGen 会再次计费。'}`
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
	async function download(original = false) {
		busy = true;
		try {
			await downloadVideo(job, original);
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
	class="relative min-w-0 space-y-2 rounded-lg border border-gray-200 p-3 dark:border-gray-800"
	aria-busy={busy || working}
>
	<button
		type="button"
		on:click={remove}
		aria-label="删除视频"
		title="删除"
		disabled={busy ||
			!['completed', 'failed', 'cancelled'].includes(job.status) ||
			['sending', 'unknown'].includes(delivery?.status ?? '') ||
			['sending', 'unknown'].includes(captionDelivery?.status ?? '')}
		class="absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-red-950/30 dark:hover:text-red-400"
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
	<div class="!mt-0 flex flex-wrap items-start gap-2 pr-6">
		{#if job.status === 'completed'}{#key job.attempt}<VideoThumbnail
					id={job.id}
					title={job.title}
					{expanded}
					ontoggle={() => (expanded = !expanded)}
				/>{/key}{/if}
		<div class="min-w-0 flex-1">
			{#if editingTitle}
				<form class="flex flex-wrap items-center gap-2" on:submit|preventDefault={saveTitle}>
					<input
						bind:this={titleInput}
						bind:value={draftTitle}
						aria-label="视频名称"
						maxlength="100"
						required
						disabled={busy}
						on:keydown={(event) => {
							if (event.key === 'Escape' && !busy) editingTitle = false;
						}}
						class="min-w-0 w-full rounded-lg border border-gray-300 bg-transparent px-2 py-1 text-sm dark:border-gray-600"
					/>
					<button
						type="submit"
						disabled={busy || !draftTitle.trim()}
						class="text-sm underline disabled:opacity-40">保存</button
					>
					<button
						type="button"
						disabled={busy}
						on:click={() => (editingTitle = false)}
						class="text-sm text-gray-500">取消</button
					>
				</form>
			{:else}
				<div class="flex items-start gap-2">
					<h3 class="min-w-0 truncate text-sm font-medium" title={job.title}>{job.title}</h3>
					{#if job.status === 'completed'}<button
							type="button"
							disabled={busy}
							on:click={editTitle}
							title="改名"
							aria-label="修改视频名称"
							class="inline-flex size-6 shrink-0 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline focus-visible:outline-2 disabled:opacity-40 dark:hover:bg-gray-800 dark:hover:text-gray-200"
						>
							<svg
								aria-hidden="true"
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
								stroke-linecap="round"
								stroke-linejoin="round"><path d="m16 3 5 5L8 21H3v-5L16 3Zm-2 2 5 5" /></svg
							>
						</button>{/if}
				</div>
			{/if}
			{#if job.credit}<p class="text-xs text-gray-500">发布署名：{job.credit}</p>{/if}
			<p class="mt-1 text-xs text-gray-500">
				{job.stage === 'preview' ? '短预览' : '完整版'} · {job.portrait_name} · {job.resolution} · {job.aspect_ratio}
				· {Math.ceil(job.duration)} 秒{#if job.steps}
					· {job.steps} 步{/if}
				<span class="block mt-1 text-[11px] text-gray-400"
					>{new Date(job.created_at * 1000).toLocaleString()}</span
				>
			</p>
		</div>
		<span class="inline-flex items-center gap-2 text-xs text-gray-500" role="status"
			>{#if working || busy || captionWorking}<WorkingIndicator />{/if}{busy
				? '正在处理…'
				: captionWorking
					? job.caption_operation === 'render'
						? '正在烧录字幕…'
						: '正在生成字幕…'
					: captionPending
						? '字幕处理失败'
						: (labels[job.status] ?? job.status)}</span
		>
	</div>
	{#if job.provider_id === 'local_h3' && working}
		<div class="space-y-2 text-xs text-gray-500" role="status">
			{#if job.progress}<p>
					{progressStages[job.progress.stage ?? ''] ?? '准备生成'} · 片段 {job.progress.segment ??
						1}/{job.progress.segments ?? 1} · 步数 {job.progress.step ?? 0}/{job.steps}
				</p>{/if}
			{#if job.estimated_seconds}<p>
					预计生成约 {Math.ceil(job.estimated_seconds / 60)} 分钟（不含排队）
				</p>{/if}
			<button
				disabled={busy || job.status === 'cancelling'}
				class="underline disabled:opacity-40"
				on:click={() => action(`/jobs/${job.id}/cancel`)}>取消生成</button
			>
		</div>
	{/if}
	{#if job.error}<p role="alert" class="break-words text-sm text-red-600 dark:text-red-400">
			{job.error}
		</p>{/if}
	{#if job.caption_error}<p role="alert" class="text-xs text-red-600">
			字幕：{job.caption_error}
		</p>{/if}
	{#if job.status === 'completed' && job.caption_status === 'failed'}<button
			disabled={busy}
			class="text-xs underline"
			on:click={() => action(`/jobs/${job.id}/captions/automatic`)}>重试字幕（本地免费）</button
		>{/if}
	{#if job.status === 'completed'}
		{#if expanded && !captionPending}<StudioMedia
				path={`/jobs/${job.id}/video`}
				kind="video"
				version={`${job.attempt}:${job.caption_ready}:${job.caption_version}`}
				autoplay
				compact
			/>{/if}
		<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs">
			{#if job.stage === 'preview' && job.can_generate_final !== false}<button
					disabled={busy || hasFinal || captionPending}
					on:click={final}
					class="font-medium underline disabled:opacity-40"
					>{hasFinal
						? '已创建完整版'
						: job.provider_id === 'local_h3'
							? '确认预览，生成完整版'
							: '确认预览，付费生成完整版'}</button
				>{/if}
			<button
				disabled={busy || captionPending}
				on:click={() => download()}
				class="underline disabled:opacity-40"
				>{job.caption_ready ? '下载带字幕 MP4' : '下载 MP4'}</button
			>
			{#if job.auto_captions || job.caption_ready}<button
					disabled={busy}
					on:click={() => download(true)}
					class="text-gray-500 underline">下载原片</button
				>{/if}
			<button
				class="underline"
				on:click={() => {
					if (captionsOpen) captionEditor?.close();
					else captionsOpen = true;
				}}>字幕</button
			>
			{#if isAdmin}<button
					disabled={busy ||
						captionPending ||
						['sending', 'sent', 'unknown'].includes(chosenDelivery?.status ?? '')}
					on:click={() => action(`/jobs/${job.id}/telegram`)}
					class="underline disabled:opacity-40"
					>{chosenDelivery?.status === 'sent'
						? '已发送 TG'
						: chosenDelivery?.status === 'sending'
							? '正在发送…'
							: job.caption_ready
								? '发送字幕版 TG'
								: '发送 TG'}</button
				>{/if}
		</div>
		{#if captionsOpen}<CaptionEditor
				bind:this={captionEditor}
				receipt={captionDelivery}
				{job}
				{isAdmin}
				{refresh}
				onclose={() => (captionsOpen = false)}
			/>{/if}
	{:else if ['failed', 'cancelled'].includes(job.status)}
		<button disabled={busy} class="text-sm underline" on:click={retry}
			>{job.provider_id === 'local_h3'
				? '重试 / 继续未完成片段'
				: job.retry_requires_payment
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
