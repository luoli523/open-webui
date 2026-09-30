<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		videoStudio,
		videoPost,
		downloadCaption,
		type VideoJob,
		type VideoCaption,
		type CaptionCue,
		type CaptionStyle,
		type Receipt
	} from '$lib/apis/video-studio';
	import WorkingIndicator from './WorkingIndicator.svelte';
	import StudioMedia from './StudioMedia.svelte';
	export let job: VideoJob;
	export let isAdmin = false;
	export let onclose: () => void;
	export let refresh: () => Promise<void>;
	let caption: VideoCaption | null = null;
	let cues: CaptionCue[] = [];
	let style: CaptionStyle = {
		size: 42,
		color: '#FFFFFF',
		position: 'bottom',
		margin: 48,
		background: false
	};
	let sourceText = '';
	let language = '';
	let busy = false;
	let loading = true;
	let error = '';
	let dirty = false;
	let disposed = false;
	let polling = false;
	let movieUrl = '';
	let vttUrl = '';
	let player: HTMLVideoElement;
	let currentTime = 0;
	let playerHeight = 240;
	let renderedPreview = false;
	export let receipt: Receipt | undefined = undefined;
	const controller = new AbortController();
	let timer: ReturnType<typeof setInterval>;
	$: active = !!caption && ['queued', 'running'].includes(caption.status);
	$: locked = busy || loading || active;
	$: rendered = !!caption && caption.version === caption.rendered_version && !dirty;
	$: currentCue = cues.find((c) => c.start <= currentTime && currentTime < c.end);
	$: if (cues) updateTrack(cues);
	function updateTrack(items: CaptionCue[]) {
		if (vttUrl) URL.revokeObjectURL(vttUrl);
		const time = (seconds: number) => {
			if (!Number.isFinite(seconds) || seconds < 0) return '00:00:00.000';
			const ms = Math.round(seconds * 1000);
			return `${String(Math.floor(ms / 3600000)).padStart(2, '0')}:${String(Math.floor(ms / 60000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
		};
		const text =
			'WEBVTT\n\n' +
			items
				.map(
					(c) =>
						`${time(c.start)} --> ${time(c.end)}\n${c.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}\n`
				)
				.join('\n');
		vttUrl = URL.createObjectURL(new Blob([text], { type: 'text/vtt' }));
	}
	function adopt(value: VideoCaption | null) {
		caption = value;
		cues = value?.cues?.map((c) => ({ ...c })) ?? [];
		if (value?.style) style = { ...value.style };
		language = value?.language ?? language;
		dirty = false;
	}
	async function load() {
		const result = await videoStudio(`/jobs/${job.id}/captions`, { signal: controller.signal });
		if (disposed) return;
		sourceText = result.source_text;
		adopt(result.caption);
	}
	async function reload() {
		if (dirty && !confirm('重新载入会放弃尚未保存的字幕修改，继续？')) return;
		busy = true;
		try {
			await load();
			error = '';
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	async function poll() {
		if (!active || polling || disposed) return;
		polling = true;
		try {
			await load();
			error = '';
		} catch (e) {
			if (!disposed) error = `${e}`;
		} finally {
			polling = false;
		}
	}
	onMount(() => {
		(async () => {
			try {
				await load();
				const blob = await videoStudio(
					`/jobs/${job.id}/video`,
					{ signal: controller.signal },
					true
				);
				if (!disposed) movieUrl = URL.createObjectURL(blob);
			} catch (e) {
				if (!disposed) error = `${e}`;
			} finally {
				loading = false;
			}
		})();
		timer = setInterval(poll, 3000);
	});
	onDestroy(() => {
		disposed = true;
		controller.abort();
		clearInterval(timer);
		if (movieUrl) URL.revokeObjectURL(movieUrl);
		if (vttUrl) URL.revokeObjectURL(vttUrl);
	});
	export function close() {
		if (!dirty || confirm('字幕修改尚未保存，确定关闭？')) onclose();
	}
	function unload(event: BeforeUnloadEvent) {
		if (dirty) {
			event.preventDefault();
			event.returnValue = '';
		}
	}
	async function generate() {
		if (cues.length && !confirm('重新识别会替换当前字幕和手动修改，继续？')) return;
		busy = true;
		try {
			adopt(
				await videoPost(`/jobs/${job.id}/captions`, {
					revision: caption?.revision ?? null,
					language
				})
			);
			renderedPreview = false;
			error = '';
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	function validation() {
		let previous = 0;
		for (const c of cues) {
			if (
				!Number.isFinite(c.start) ||
				!Number.isFinite(c.end) ||
				c.start < previous ||
				c.end <= c.start ||
				c.end > (caption?.duration ?? job.duration) + 0.001 ||
				!c.text.trim()
			)
				return '请检查每句时间：起点小于终点、各句不重叠、终点不超过视频时长，文字不能为空。';
			previous = c.end;
		}
		return cues.length ? '' : '请保留至少一句字幕。';
	}
	async function save() {
		const invalid = validation();
		if (invalid) {
			error = invalid;
			return;
		}
		busy = true;
		try {
			adopt(
				await videoStudio(`/jobs/${job.id}/captions`, {
					method: 'PUT',
					body: JSON.stringify({ revision: caption?.revision, cues, style })
				})
			);
			renderedPreview = false;
			error = '';
			toast.success('字幕已保存');
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	async function render() {
		busy = true;
		try {
			adopt(await videoPost(`/jobs/${job.id}/captions/render`, { revision: caption?.revision }));
			error = '';
			renderedPreview = false;
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	async function download(format: 'srt' | 'vtt' | 'ass' | 'mp4') {
		busy = true;
		try {
			await downloadCaption(job, format);
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	async function telegram() {
		busy = true;
		try {
			receipt = await videoPost(`/jobs/${job.id}/telegram?variant=captioned`);
			if (receipt?.status === 'sent') toast.success('带字幕视频已发送 TG');
			else if (receipt?.error) error = receipt.error;
			await refresh();
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}
	async function resolveReceipt(received: boolean) {
		if (!receipt || (!received && !confirm('已在 Telegram 核对，确定没有收到这份字幕版视频？')))
			return;
		busy = true;
		try {
			await videoPost(`/deliveries/${receipt.id}/resolve`, { received });
			await refresh();
			error = '';
		} catch (e) {
			error = `${e}`;
		} finally {
			busy = false;
		}
	}

	function seek(cue: CaptionCue) {
		if (player) {
			player.currentTime = cue.start;
			currentTime = cue.start;
		}
	}
	function split(index: number) {
		const cue = cues[index];
		if (cue.text.trim().length < 2 || cue.end - cue.start < 0.1) return;
		const chars = Array.from(cue.text);
		const middle = Math.floor(chars.length / 2);
		const time = Math.round((cue.start + cue.end) * 500) / 1000;
		cues = [
			...cues.slice(0, index),
			{ ...cue, end: time, text: chars.slice(0, middle).join('').trim() },
			{ ...cue, start: time, text: chars.slice(middle).join('').trim() },
			...cues.slice(index + 1)
		];
		dirty = true;
	}
	function merge(index: number) {
		const first = cues[index],
			next = cues[index + 1];
		cues = [
			...cues.slice(0, index),
			{ ...first, end: next.end, text: `${first.text}\n${next.text}` },
			...cues.slice(index + 2)
		];
		dirty = true;
	}
	function hiddenTrack() {
		if (player?.textTracks?.[0]) player.textTracks[0].mode = 'hidden';
	}
</script>

<svelte:window on:beforeunload={unload} />
<section
	class="caption-container mt-3 min-w-0 rounded-lg border border-gray-200 p-3 dark:border-gray-700"
	aria-label="视频字幕编辑器"
	aria-busy={locked}
>
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h4 class="text-sm font-medium">
			字幕 <span class="text-xs text-gray-500"
				>{dirty ? '· 未保存' : caption?.version ? `· v${caption.version}` : ''}</span
			>
		</h4>
		<div class="flex items-center gap-3 text-xs">
			<button on:click={reload} disabled={locked} class="underline disabled:opacity-40"
				>重新载入</button
			><button
				on:click={close}
				title="关闭字幕编辑器"
				aria-label="关闭字幕编辑器"
				class="size-7 rounded hover:bg-gray-100 dark:hover:bg-gray-800">×</button
			>
		</div>
	</div>
	<div class="my-3 flex flex-wrap items-center gap-3 text-xs">
		<label
			>语言 <select
				bind:value={language}
				disabled={locked}
				class="rounded border bg-transparent p-1 dark:border-gray-600"
			>
				{#each [['', '自动检测'], ['zh', '中文'], ['en', '英语'], ['ja', '日语'], ['ko', '韩语'], ['de', '德语'], ['fr', '法语'], ['ru', '俄语'], ['pt', '葡萄牙语'], ['es', '西班牙语'], ['it', '意大利语']] as [value, label]}<option
						{value}>{label}</option
					>{/each}
			</select></label
		>
		<button
			disabled={locked}
			on:click={generate}
			class="rounded bg-gray-900 px-3 py-1.5 text-white disabled:opacity-40 dark:bg-gray-100 dark:text-gray-900"
			>{cues.length ? '重新生成字幕' : '生成字幕'}</button
		>
		{#if locked}<span class="inline-flex items-center gap-1" role="status"
				><WorkingIndicator />{active
					? caption?.operation === 'render'
						? '正在烧录字幕…'
						: '正在识别 / 对齐字幕…'
					: '正在处理…'}</span
			>{/if}
	</div>
	{#if active}<p class="mb-3 text-xs text-gray-500">
			字幕在本机后台处理，可以关闭面板，稍后返回。
		</p>{/if}
	{#if error || caption?.error}<p
			role="alert"
			class="mb-3 break-words text-xs text-red-600 dark:text-red-400"
		>
			{error || caption?.error}
		</p>{/if}
	<div class="caption-layout grid min-w-0 gap-4">
		<div class="min-w-0">
			{#if movieUrl}
				<div class="relative overflow-hidden rounded bg-black">
					<video
						bind:this={player}
						bind:currentTime
						bind:clientHeight={playerHeight}
						src={movieUrl}
						controls
						playsinline
						preload="metadata"
						class="w-full"
						on:loadedmetadata={hiddenTrack}
					>
						<track
							kind="captions"
							src={vttUrl}
							srclang={language || 'zh'}
							label="字幕"
							on:load={hiddenTrack}
						/>
					</video>
					{#if currentCue}<div
							aria-hidden="true"
							class="pointer-events-none absolute left-[3%] right-[3%] whitespace-pre-line text-center leading-tight"
							style:font-family="'PingFang SC', sans-serif"
							style:font-size={`${Math.max(10, (style.size * playerHeight) / 720)}px`}
							style:color={style.color}
							style:top={style.position === 'top' ? `${(style.margin / 720) * 100}%` : 'auto'}
							style:bottom={style.position === 'bottom' ? `${(style.margin / 720) * 100}%` : 'auto'}
							style:text-shadow="-1px -1px 1px #000, 1px 1px 1px #000"
						>
							<span style:background={style.background ? '#0009' : 'transparent'}
								>{currentCue.text}</span
							>
						</div>{/if}
				</div>
			{/if}
			<p class="mt-2 text-[11px] text-gray-500">
				点击句子前的时间定位播放。样式为近似预览，以烧录成片为准。
			</p>
			{#if sourceText}<details class="mt-3 text-xs">
					<summary class="cursor-pointer text-gray-500">原始播报文案</summary>
					<p class="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words">{sourceText}</p>
				</details>{/if}
			{#if caption?.mode}<p class="mt-2 text-[11px] text-gray-500">
					{caption.mode === 'alignment' ? '根据原文对齐成片音轨' : '根据实际成片音轨识别'} · 请校对人名、专有名词与时间。
				</p>{/if}
		</div>
		<div class="min-w-0">
			{#if cues.length}
				<fieldset disabled={locked} class="space-y-3 disabled:opacity-60">
					<div
						class="flex flex-wrap items-center gap-3 text-xs"
						on:input={() => (dirty = true)}
						on:change={() => (dirty = true)}
					>
						<label
							>字号 <input
								aria-label="字幕字号"
								type="number"
								min="20"
								max="80"
								bind:value={style.size}
								class="w-14 rounded border bg-transparent p-1 dark:border-gray-600"
							/></label
						>
						<label class="flex items-center gap-1"
							>颜色 <input
								aria-label="字幕颜色"
								type="color"
								bind:value={style.color}
								class="h-6 w-8 bg-transparent"
							/></label
						>
						<label
							>位置 <select
								bind:value={style.position}
								class="rounded border bg-transparent p-1 dark:border-gray-600"
								><option value="bottom">底部</option><option value="top">顶部</option></select
							></label
						>
						<label
							>边距 <input
								type="number"
								min="20"
								max="160"
								bind:value={style.margin}
								class="w-14 rounded border bg-transparent p-1 dark:border-gray-600"
							/></label
						>
						<label class="flex items-center gap-1"
							><input type="checkbox" bind:checked={style.background} />黑色底框</label
						>
					</div>
					<div class="max-h-96 space-y-2 overflow-y-auto pr-1">
						{#each cues as cue, index}
							<div
								class="rounded border p-2"
								class:border-blue-400={currentCue === cue}
								class:border-gray-200={currentCue !== cue}
							>
								<div class="mb-1 flex flex-wrap items-center gap-2 text-[11px]">
									<button
										type="button"
										on:click={() => seek(cue)}
										title="定位到这句"
										class="text-blue-600">▶ {index + 1}</button
									>
									<input
										aria-label={`第 ${index + 1} 句开始秒数`}
										type="number"
										min="0"
										step="0.01"
										bind:value={cue.start}
										on:input={() => (dirty = true)}
										class="w-20 rounded border bg-transparent px-1 dark:border-gray-600"
									/>
									<span>—</span>
									<input
										aria-label={`第 ${index + 1} 句结束秒数`}
										type="number"
										min="0"
										step="0.01"
										bind:value={cue.end}
										on:input={() => (dirty = true)}
										class="w-20 rounded border bg-transparent px-1 dark:border-gray-600"
									/><span>秒</span>
									<button
										on:click={() => split(index)}
										disabled={cue.text.trim().length < 2}
										class="underline disabled:opacity-40"
										title="按文字和时长中点拆分，再手动调整">拆分</button
									>
									<button
										on:click={() => merge(index)}
										disabled={index === cues.length - 1 ||
											cue.text.length + (cues[index + 1]?.text.length ?? 0) >= 500}
										class="underline disabled:opacity-40">合并下句</button
									>
									<button
										aria-label={`删除第 ${index + 1} 句`}
										title="删除这句"
										disabled={cues.length < 2}
										class="ml-auto text-gray-400 hover:text-red-500"
										on:click={() => {
											cues = cues.filter((_, i) => i !== index);
											dirty = true;
										}}>×</button
									>
								</div>
								<textarea
									aria-label={`第 ${index + 1} 句字幕`}
									bind:value={cue.text}
									on:input={() => (dirty = true)}
									maxlength="500"
									rows="2"
									class="w-full resize-y rounded border border-gray-200 bg-transparent p-1 text-sm dark:border-gray-600"
								></textarea>
							</div>
						{/each}
					</div>
				</fieldset>
				<div class="mt-3 flex flex-wrap items-center gap-3 text-xs">
					<button
						disabled={locked || !dirty}
						on:click={save}
						class="rounded bg-gray-900 px-3 py-1.5 text-white disabled:opacity-40 dark:bg-gray-100 dark:text-gray-900"
						>保存字幕</button
					>
					{#each ['srt', 'vtt', 'ass'] as format}<button
							disabled={locked || dirty}
							on:click={() => download(format as 'srt' | 'vtt' | 'ass')}
							class="underline disabled:opacity-40">下载 {format.toUpperCase()}</button
						>{/each}
					<button disabled={locked || dirty} on:click={render} class="underline disabled:opacity-40"
						>{rendered ? '字幕版已就绪' : '生成带字幕视频'}</button
					>
				</div>
				{#if caption?.rendered_version != null && !rendered}<p class="mt-2 text-xs text-amber-600">
						字幕有更新，请保存后重新生成字幕版视频。
					</p>{/if}
				{#if rendered}<div class="mt-3 flex flex-wrap gap-3 text-xs">
						<button on:click={() => (renderedPreview = !renderedPreview)} class="underline"
							>{renderedPreview ? '收起成片' : '观看字幕成片'}</button
						>
						<button
							disabled={locked}
							on:click={() => download('mp4')}
							class="underline disabled:opacity-40">下载带字幕 MP4</button
						>
						{#if isAdmin}<button
								disabled={locked || ['unknown', 'sending'].includes(receipt?.status ?? '')}
								on:click={telegram}
								class="underline disabled:opacity-40">发送字幕版 TG</button
							>{/if}
					</div>{/if}
			{:else if !loading && !active}<p class="py-6 text-center text-sm text-gray-500">
					生成字幕后，可在这里编辑每句文字和时间。
				</p>{/if}
		</div>
	</div>
	{#if isAdmin && receipt?.status === 'unknown'}
		<div class="mt-3 space-y-2 text-xs text-amber-700 dark:text-amber-400">
			<p>字幕版 TG 发送结果待核实，请先检查收件情况。</p>
			<div class="flex flex-wrap gap-3">
				<button disabled={locked} on:click={() => resolveReceipt(true)} class="underline"
					>TG 已收到</button
				><button disabled={locked} on:click={() => resolveReceipt(false)} class="underline"
					>确认未收到，允许重发</button
				>
			</div>
		</div>
	{/if}

	{#if renderedPreview && rendered}<div class="mt-3">
			<StudioMedia
				path={`/jobs/${job.id}/captions/file?format=mp4`}
				kind="video"
				version={String(caption?.rendered_version)}
				autoplay
				compact
			/>
		</div>{/if}
</section>

<style>
	.caption-container {
		container-type: inline-size;
		container-name: caption-editor;
	}
	.caption-layout {
		grid-template-columns: minmax(0, 1fr);
	}
	@container caption-editor (min-width: 48rem) {
		.caption-layout {
			grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
		}
	}
</style>
