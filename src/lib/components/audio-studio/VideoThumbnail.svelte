<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { videoStudio } from '$lib/apis/video-studio';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let id: string;
	export let title: string;
	export let expanded = false;
	export let ontoggle: () => void;
	let button: HTMLButtonElement;
	let url = '';
	let loading = false;
	let error = '';
	let controller: AbortController;
	let disposed = false;
	async function load() {
		loading = true;
		controller = new AbortController();
		try {
			const blob = await videoStudio(`/jobs/${id}/thumbnail`, { signal: controller.signal }, true);
			if (!disposed) url = URL.createObjectURL(blob);
		} catch (e) {
			if (!disposed) error = `${e}`;
		} finally {
			loading = false;
		}
	}
	onMount(() => {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) {
					observer.disconnect();
					load();
				}
			},
			{ rootMargin: '100px' }
		);
		observer.observe(button);
		return () => observer.disconnect();
	});
	onDestroy(() => {
		disposed = true;
		controller?.abort();
		if (url) URL.revokeObjectURL(url);
	});
</script>

<button
	bind:this={button}
	type="button"
	on:click={ontoggle}
	aria-expanded={expanded}
	aria-label={`${expanded ? '收起' : '播放'} ${title}`}
	title={error || (expanded ? '收起视频' : '播放视频')}
	class="relative inline-flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md bg-gray-100 text-gray-500 focus-visible:outline focus-visible:outline-2 dark:bg-gray-900"
>
	{#if url}<img src={url} alt={`${title} 首帧`} class="h-full w-full object-contain" />{/if}
	<span class="absolute inset-0 flex items-center justify-center">
		<span
			class="inline-flex size-6 items-center justify-center rounded-full bg-black/50 text-white"
		>
			{#if loading}<WorkingIndicator />{:else}<svg
					aria-hidden="true"
					class="size-3"
					viewBox="0 0 24 24"
					fill="currentColor"><path d="M8 5v14l11-7z" /></svg
				>{/if}
		</span>
	</span>
</button>
