<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { videoStudio } from '$lib/apis/video-studio';
	import ImagePreview from '$lib/components/common/ImagePreview.svelte';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let id: string;
	export let name: string;
	let button: HTMLButtonElement;
	let url = '';
	let loading = false;
	let error = '';
	let show = false;
	let controller: AbortController;
	let disposed = false;
	async function load() {
		loading = true;
		controller = new AbortController();
		try {
			const blob = await videoStudio(`/portraits/${id}/image`, { signal: controller.signal }, true);
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
	disabled={!url}
	on:click={() => (show = true)}
	aria-label={`查看 ${name} 大图`}
	title={error || '查看大图'}
	class="relative inline-flex h-20 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-gray-100 text-gray-500 focus-visible:outline focus-visible:outline-2 dark:bg-gray-900"
>
	{#if url}<img
			src={url}
			alt={name}
			class="h-full w-full object-cover"
		/>{:else if loading}<WorkingIndicator />{:else if error}<span class="text-xs text-red-600"
			>加载失败</span
		>{/if}
</button>
<ImagePreview bind:show src={url} alt={name} />
