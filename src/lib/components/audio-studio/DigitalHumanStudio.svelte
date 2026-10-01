<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import type { Job, Voice } from '$lib/apis/audio-studio';
	import {
		videoStudio,
		videoPost,
		type Portrait,
		type Provider,
		type VideoJob,
		type Receipt
	} from '$lib/apis/video-studio';
	import StudioMedia from './StudioMedia.svelte';
	import VideoJobResult from './VideoJobResult.svelte';
	import VideoProviderSettings from './VideoProviderSettings.svelte';
	import LocalVideoSettings from './LocalVideoSettings.svelte';
	import TextNarration from './TextNarration.svelte';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let audioJobs: Job[] = [];
	export let voices: Voice[] = [];
	export let initialAudio = '';
	export let initialPortrait = '';
	export let managePortraits: () => void = () => {};
	let portraits: Portrait[] = [];
	let providers: Provider[] = [];
	let jobs: VideoJob[] = [];
	let receipts: Receipt[] = [];
	let portrait = initialPortrait;
	let audio = initialAudio;
	let narrationMode = 'existing';
	let textAudio = '';
	let provider = 'local_h3';
	let steps = 12;
	const stepSeconds: Record<number, number> = { 8: 430, 12: 626, 20: 1003 };
	let previewStart = 0;
	let previewSeconds = 5;
	let ratio = '1:1';
	let busy = false;
	let loading = true;
	let refreshing = false;
	let error = '';
	$: engine = providers.find((p) => p.id === provider);
	$: if (engine && !engine.aspect_ratios.includes(ratio)) ratio = engine.aspect_ratios[0];
	$: if (engine?.supported_steps && !engine.supported_steps.includes(steps))
		steps = engine.default_steps ?? 12;
	$: selectedPortrait = portraits.find((p) => p.id === portrait);
	$: completedAudio = audioJobs.filter((j) => j.status === 'completed');
	$: selectedAudio = narrationMode === 'text' ? textAudio : audio;
	async function refresh() {
		if (refreshing) return;
		refreshing = true;
		try {
			const [people, engines, videos] = await Promise.all([
				videoStudio('/portraits'),
				videoStudio('/providers'),
				videoStudio('/jobs')
			]);
			portraits = people;
			providers = engines;
			jobs = videos;
			if (!portrait && portraits.length) portrait = portraits[0].id;
			if (!audio && completedAudio.length) audio = completedAudio[0].id;
			if ($user?.role === 'admin') receipts = await videoStudio('/deliveries');
			error = '';
		} catch (e) {
			error = `${e}`;
		} finally {
			refreshing = false;
			loading = false;
		}
	}
	async function generate() {
		busy = true;
		try {
			await videoPost('/jobs', {
				portrait_id: portrait,
				audio_job_id: selectedAudio,
				provider_id: provider,
				aspect_ratio: ratio,
				steps,
				preview_start: previewStart,
				preview_seconds: previewSeconds
			});
			await refresh();
			toast.success('已提交预览，请在视频记录中查看');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		refresh();
		const timer = setInterval(refresh, 5000);
		return () => clearInterval(timer);
	});
</script>

<div class="video-columns grid min-w-0 grid-cols-1 items-start gap-8">
	<section class="min-w-0 space-y-5">
		<div>
			<h2 class="font-semibold">创建数字人视频</h2>
			<p class="mt-2 text-sm leading-6 text-gray-500">
				选好人物，输入文案或选择已有播报，先看短预览，再生成完整版。
			</p>
		</div>
		{#if error}<p role="alert" class="text-sm text-red-600">
				{error} <button class="underline" on:click={refresh}>重新连接</button>
			</p>{/if}
		{#if loading}<p role="status" class="text-sm text-gray-500">正在加载…</p>{/if}
		<label class="block text-sm"
			>视频引擎<select
				bind:value={provider}
				class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
				>{#each providers as p}<option value={p.id}
						>{p.name}{p.cloud ? ' · 云端' : ' · 本地'}</option
					>{/each}</select
			></label
		>
		{#if engine && (!engine.configured || !engine.enabled)}<p
				class="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800"
			>
				{engine.configured ? '视频引擎已暂停新任务。' : '尚未配置视频引擎。'}{$user?.role ===
				'admin'
					? '请在下方设置中配置并启用。'
					: '请联系管理员。'}
			</p>{/if}
		<label class="block text-sm"
			>选择人物<select
				bind:value={portrait}
				class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
				><option value="" disabled>请选择人物</option
				>{#each portraits.filter((p) => engine?.input_types.includes(p.input_type)) as p}<option
						value={p.id}>{p.name}</option
					>{/each}</select
			></label
		>
		<button class="text-sm underline" on:click={managePortraits}>上传 / 管理人物</button>
		{#if selectedPortrait}<StudioMedia
				path={`/portraits/${portrait}/image`}
				version={selectedPortrait.version}
				alt={selectedPortrait.name}
			/>{/if}
		<fieldset class="flex flex-wrap gap-4 text-sm">
			<legend class="mb-2">配音来源</legend>
			<label class="inline-flex items-center gap-2"
				><input type="radio" bind:group={narrationMode} value="existing" />已有播报</label
			>
			<label class="inline-flex items-center gap-2"
				><input type="radio" bind:group={narrationMode} value="text" />输入文本</label
			>
		</fieldset>
		{#if narrationMode === 'text'}
			<TextNarration
				{voices}
				defaultVoice={selectedPortrait?.default_voice_id ?? ''}
				onready={(id) => (textAudio = id)}
			/>
		{:else}
			<label class="block text-sm"
				>选择已生成的播报<select
					bind:value={audio}
					class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
					><option value="" disabled>请选择播报</option>{#each completedAudio as item}<option
							value={item.id}>{item.title} · {item.voice_name}</option
						>{/each}</select
				></label
			>
			{#if audio}<StudioMedia path={`/jobs/${audio}/audio?format=mp3`} kind="audio" />{/if}
		{/if}
		<label class="block text-sm"
			>画面比例<select
				bind:value={ratio}
				class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
				>{#each engine?.aspect_ratios ?? [] as value}<option {value}
						>{value === '16:9' ? '横屏 16:9' : value === '9:16' ? '竖屏 9:16' : value}</option
					>{/each}</select
			></label
		>

		{#if provider === 'local_h3'}
			<label class="block text-sm"
				>生成步数<select
					bind:value={steps}
					class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
				>
					{#each engine?.supported_steps ?? [8, 12, 20] as count}<option value={count}
							>{count} 步{count === (engine?.default_steps ?? 12) ? '（默认）' : ''}</option
						>{/each}
				</select></label
			>
			<div class="grid grid-cols-2 gap-3">
				<label class="block text-sm"
					>预览起点（秒）<input
						type="number"
						min="0"
						max="298"
						step="0.1"
						bind:value={previewStart}
						class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
					/></label
				>
				<label class="block text-sm"
					>预览长度（秒）<input
						type="number"
						min="2"
						max="15"
						step="0.1"
						bind:value={previewSeconds}
						class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
					/></label
				>
			</div>
			<p class="text-xs leading-5 text-gray-500">
				512×512 · 步数越高耗时越长，可能改善声音效果。以本机样片估算，本次约 {Math.ceil(
					((previewSeconds / (107 / 24)) * (stepSeconds[steps] ?? 430)) / 60
				)} 分钟，实际随素材变化。{engine?.long_video_enabled
					? '支持分段生成完整版。'
					: '目前支持短片；长片分段待启用。'}
			</p>
		{:else}
			<p class="text-xs leading-5 text-gray-500">
				预览取开头最多15秒（{engine?.preview_resolution ??
					'720p'}），完整版使用完整配音（{engine?.final_resolution ??
					'1080p'}）。{engine?.duration_note ?? ''}
			</p>
		{/if}

		{#if engine?.cloud || engine?.paid}
			<p class="text-xs leading-5 text-gray-500">
				{engine?.cloud ? '照片与成品配音将上传至所选引擎。' : ''}
				{engine?.paid ? '生成预览会产生费用，按引擎账户实际计费。' : ''}
			</p>
		{/if}

		<button
			disabled={busy ||
				!selectedAudio ||
				!selectedPortrait ||
				!engine?.enabled ||
				!engine?.configured}
			on:click={generate}
			class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gray-900 p-3 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-black"
			>{#if busy}<WorkingIndicator />{/if}{busy ? '正在提交…' : '生成短预览'}</button
		>
		{#if $user?.role === 'admin'}<LocalVideoSettings onchange={refresh} /><VideoProviderSettings
				onchange={refresh}
			/>{/if}
	</section>
	<section class="min-w-0 space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="font-semibold">视频记录</h2>
			<button class="text-sm underline" disabled={refreshing} on:click={refresh}>刷新</button>
		</div>
		{#each jobs as job (job.id)}<VideoJobResult
				{job}
				{refresh}
				isAdmin={$user?.role === 'admin'}
				hasFinal={jobs.some((j) => j.preview_id === job.id)}
				delivery={receipts.find((r) => r.job_id === job.id && r.variant !== 'captioned')}
				captionDelivery={receipts.find(
					(r) =>
						r.job_id === job.id &&
						r.variant === 'captioned' &&
						['unknown', 'sending'].includes(r.status)
				) ??
					receipts.find(
						(r) =>
							r.job_id === job.id &&
							r.variant === 'captioned' &&
							r.artifact_hash === job.caption_hash
					)}
			/>{:else}{#if !loading && !error}<p class="py-12 text-center text-sm leading-7 text-gray-500">
					还没有视频记录。<br />选择人物和播报，生成第一段预览。
				</p>{/if}{/each}
	</section>
</div>

<style>
	@container audio-studio (min-width: 56rem) {
		.video-columns {
			grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
		}
	}
</style>
