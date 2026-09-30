<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { studio, type Voice } from '$lib/apis/audio-studio';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let voice: Voice | undefined = undefined;
	export let compact = false;
	let paused = true;
	let url = '';
	let busy = false;
	let error = '';
	let status = '';
	let player: HTMLAudioElement;
	let controller: AbortController;
	let selected = '';
	const instance = Symbol('voice-preview');
	function clear() {
		controller?.abort();
		player?.pause();
		if (url) URL.revokeObjectURL(url);
		url = '';
		busy = false;
		error = '';
		status = '';
	}
	$: if (`${voice?.id}:${voice?.version}` !== selected) {
		selected = `${voice?.id}:${voice?.version}`;
		clear();
	}
	function announce() {
		window.dispatchEvent(new CustomEvent('studio-voice-preview', { detail: instance }));
	}
	async function listen() {
		if (!voice || busy) return;
		if (url && !paused) {
			player?.pause();
			return;
		}
		announce();
		if (url) {
			try {
				await player?.play();
			} catch {
				/* Native controls remain available. */
			}
			return;
		}
		const current = new AbortController();
		controller = current;
		busy = true;
		error = '';
		status = '准备试听…';
		try {
			let sample = await studio(`/voices/${voice.id}/sample`, {
				method: 'POST',
				signal: current.signal
			});
			while (!current.signal.aborted && ['queued', 'running'].includes(sample.status)) {
				status = sample.status === 'queued' ? '试听排队中…' : '正在生成试听…';
				await new Promise((resolve) => setTimeout(resolve, 1500));
				if (current.signal.aborted) return;
				sample = await studio(`/voice-samples/${sample.id}`, { signal: current.signal });
			}
			if (current.signal.aborted) return;
			if (sample.status !== 'completed') throw new Error(sample.error || '试听生成中断，请重试');
			const blob = await studio(
				`/voice-samples/${sample.id}/audio`,
				{ signal: current.signal },
				true
			);
			if (current.signal.aborted) return;
			url = URL.createObjectURL(blob);
			await tick();
			if (!current.signal.aborted) {
				try {
					await player?.play();
				} catch {
					/* Browser may require a second click to play. */
				}
			}
		} catch (e) {
			if (!current.signal.aborted) error = `${e}`;
		} finally {
			if (controller === current) busy = false;
		}
	}
	onMount(() => {
		const stopOther = (event: Event) => {
			if ((event as CustomEvent).detail !== instance) {
				player?.pause();
				controller?.abort();
				busy = false;
			}
		};
		window.addEventListener('studio-voice-preview', stopOther);
		return () => window.removeEventListener('studio-voice-preview', stopOther);
	});
	onDestroy(clear);
</script>

<div class={compact ? 'relative inline-flex shrink-0 items-center' : 'space-y-2'}>
	<button
		type="button"
		disabled={!voice || busy}
		on:click={listen}
		title={busy ? status : paused ? '试听音色' : '暂停试听'}
		aria-label={busy ? status : `${paused ? '试听' : '暂停'} ${voice?.name ?? '音色'}`}
		class={compact
			? 'inline-flex size-7 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-900 focus-visible:outline focus-visible:outline-2 disabled:opacity-40 dark:hover:bg-gray-800 dark:hover:text-white'
			: 'inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800'}
	>
		{#if busy}<WorkingIndicator />{:else}<svg
				aria-hidden="true"
				class="size-4"
				viewBox="0 0 24 24"
				fill="currentColor"
				>{#if paused}<path d="M8 5v14l11-7z" />{:else}<path
						d="M6 5h4v14H6zM14 5h4v14h-4z"
					/>{/if}</svg
			>{/if}
		{#if !compact}{busy ? status : voice ? `试听音色 · ${voice.name}` : '选择音色后试听'}{/if}
	</button>
	{#if busy && !compact}<p role="status" class="text-xs text-gray-500">
			首次试听由本地模型生成，完成后会缓存。
		</p>{/if}
	{#if url}<audio
			bind:this={player}
			bind:paused
			src={url}
			controls={!compact}
			on:play={announce}
			class={compact ? 'hidden' : 'w-full'}><track kind="captions" /></audio
		>{/if}
	{#if error}<p role="alert" class="text-sm text-red-600 dark:text-red-400">{error}</p>{/if}
</div>
