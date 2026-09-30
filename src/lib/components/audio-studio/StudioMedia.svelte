<script lang="ts">
	import { onDestroy } from 'svelte';
	import { videoStudio } from '$lib/apis/video-studio';
	import { studio } from '$lib/apis/audio-studio';
	export let path: string;
	export let kind: 'image' | 'video' | 'audio' = 'image';
	export let alt = '';
	export let version = '';
	let url = '';
	let error = '';
	let loading = false;
	let controller: AbortController;
	let disposed = false;
	let identity = '';
	$: if (`${path}:${version}` !== identity) {
		identity = `${path}:${version}`;
		controller?.abort();
		if (url) URL.revokeObjectURL(url);
		url = '';
		error = '';
		loading = false;
		if (kind === 'image') load();
	}
	async function load() {
		controller?.abort();
		const current = new AbortController();
		controller = current;
		loading = true;
		error = '';
		try {
			const blob = await (kind === 'audio' ? studio : videoStudio)(
				path,
				{ signal: current.signal },
				true
			);
			if (!disposed && !current.signal.aborted) url = URL.createObjectURL(blob);
		} catch (e) {
			if (!current.signal.aborted) error = `${e}`;
		} finally {
			if (controller === current) loading = false;
		}
	}
	onDestroy(() => {
		disposed = true;
		controller?.abort();
		if (url) URL.revokeObjectURL(url);
	});
</script>

{#if url}
	{#if kind === 'image'}
		<img
			src={url}
			{alt}
			class="max-h-64 w-full rounded-lg bg-gray-100 object-contain dark:bg-gray-900"
		/>
	{:else if kind === 'video'}
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			src={url}
			controls
			playsinline
			preload="metadata"
			class="max-h-[32rem] w-full rounded-lg bg-black"
		></video>
	{:else}
		<audio src={url} controls class="w-full"></audio>
	{/if}
{:else}
	<button
		class="w-full rounded-lg border border-gray-200 p-4 text-sm dark:border-gray-700 disabled:opacity-50"
		disabled={loading}
		on:click={load}
	>
		{loading
			? '正在加载…'
			: kind === 'image'
				? '加载照片'
				: kind === 'audio'
					? '试听配音'
					: '播放视频'}
	</button>
{/if}
{#if error}<p role="alert" class="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>{/if}
