<script lang="ts">
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { studio, post, type Job, type Voice } from '$lib/apis/audio-studio';
	import StudioMedia from './StudioMedia.svelte';
	import WorkingIndicator from './WorkingIndicator.svelte';
	import VoicePreview from './VoicePreview.svelte';
	export let voices: Voice[] = [];
	export let defaultVoice = '';
	export let onready: (id: string) => void = () => {};
	let text = '';
	let voice = '';
	let speed = 1;
	let previousDefault = '';
	let job: Job | null = null;
	let busy = false;
	let refreshing = false;
	let disposed = false;
	let error = '';
	$: if (defaultVoice !== previousDefault) {
		previousDefault = defaultVoice;
		if (voices.some((v) => v.id === defaultVoice)) voice = defaultVoice;
	}
	$: if (!voice && voices.length) voice = voices[0].id;
	$: working = busy || job?.status === 'queued' || job?.status === 'running';
	$: matches = job?.text === text.trim() && job?.voice_id === voice && job?.speed === speed;
	$: ready = matches && job?.status === 'completed';
	$: onready(ready && job ? job.id : '');
	const storageKey = () => `audio-studio:video-narration:${$user?.id}`;
	async function refresh() {
		if (!job || refreshing || !['queued', 'running'].includes(job.status)) return;
		refreshing = true;
		try {
			const next = await studio(`/jobs/${job.id}`);
			if (!disposed) {
				job = next;
				error = '';
			}
		} catch (e) {
			if (!disposed) error = `${e}`;
		} finally {
			refreshing = false;
		}
	}
	async function generate() {
		busy = true;
		error = '';
		try {
			const created = await post('/jobs', { text, voice_id: voice, speed });
			try {
				localStorage.setItem(storageKey(), created.id);
			} catch {
				/* Storage may be disabled. */
			}
			if (!disposed) job = created;
		} catch (e) {
			if (!disposed) error = `${e}`;
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		let saved: string | null = null;
		try {
			saved = localStorage.getItem(storageKey());
		} catch {
			/* Optional resume hint. */
		}
		if (saved) {
			busy = true;
			studio(`/jobs/${encodeURIComponent(saved)}`)
				.then((found: Job) => {
					if (!disposed) {
						job = found;
						text = found.text;
						voice = found.voice_id;
						speed = found.speed;
					}
				})
				.catch(() => {
					/* A removed historical job should not block a new draft. */
				})
				.finally(() => {
					busy = false;
				});
		}
		const timer = setInterval(refresh, 3000);
		return () => {
			disposed = true;
			clearInterval(timer);
		};
	});
</script>

<div class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-800">
	<p class="text-sm leading-6 text-gray-500">
		输入文案，由本地 TTS 生成配音。试听后，在下方生成视频预览。
	</p>
	<label class="block text-sm"
		>播报文案<textarea
			bind:value={text}
			disabled={working}
			maxlength="10000"
			rows="6"
			placeholder="输入人物需要播报的内容……"
			class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 leading-7 disabled:opacity-60 dark:border-gray-700"
		></textarea></label
	>
	<label class="block text-sm"
		>配音音色<select
			bind:value={voice}
			disabled={working}
			class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900"
			><option value="" disabled>请选择音色</option>{#each voices as item}<option value={item.id}
					>{item.name}</option
				>{/each}</select
		></label
	>
	<VoicePreview voice={voices.find((v) => v.id === voice)} />
	<div class="flex flex-wrap items-center justify-between gap-3 text-sm">
		<label
			>语速 <select
				bind:value={speed}
				disabled={working}
				class="rounded-lg bg-gray-100 p-2 dark:bg-gray-800"
				>{#each [0.5, 0.75, 1, 1.25, 1.5, 2] as value}<option {value}>{value}×</option
					>{/each}</select
			></label
		><span class="text-xs text-gray-500">{text.length} / 10000</span>
	</div>
	<button
		disabled={working || !text.trim() || !voices.some((v) => v.id === voice) || ready}
		on:click={generate}
		class="inline-flex items-center justify-center gap-2 rounded-lg bg-gray-100 px-4 py-3 text-sm disabled:opacity-50 dark:bg-gray-800"
		>{#if working}<WorkingIndicator />{/if}{busy
			? '正在提交…'
			: job?.status === 'queued'
				? '配音排队中…'
				: job?.status === 'running'
					? '正在生成配音…'
					: ready
						? '配音已完成'
						: '生成配音'}</button
	>
	{#if working}<p role="status" class="text-xs leading-5 text-gray-500">
			配音在后台生成，可离开页面，稍后返回查看。成品也会保存在播报历史。
		</p>{/if}
	{#if error}<p role="alert" class="text-sm text-red-600">{error}</p>{/if}
	{#if job?.status === 'failed' || job?.status === 'interrupted'}<p
			role="alert"
			class="text-sm text-red-600"
		>
			{job.error || '配音生成中断，请重新生成。'}
		</p>{/if}
	{#if ready && job}<StudioMedia path={`/jobs/${job.id}/audio?format=mp3`} kind="audio" />
		<p class="text-xs text-gray-500">配音已就绪。试听确认后，可在下方生成短预览。</p>
	{:else if job?.status === 'completed'}<p class="text-xs text-gray-500">
			文案或音色已修改，请重新生成配音。
		</p>{/if}
</div>
