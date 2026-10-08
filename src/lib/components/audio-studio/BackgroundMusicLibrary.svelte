<script lang="ts">
	import { onMount, tick } from 'svelte';

	type Track = {
		id: string;
		title: string;
		artist: string;
		album: string;
		year: string;
		duration: number;
		background: string;
		scenes: string;
		usage: string;
		url: string;
	};
	type Library = { id: string; name: string; description: string; tracks: Track[] };
	let libraries: Library[] = [];
	let libraryId = '';
	let selected: Track | null = null;
	let search = '';
	let loading = true;
	let error = '';
	let playbackError = '';
	let player: HTMLAudioElement;
	let disposed = false;
	$: library = libraries.find((item) => item.id === libraryId);
	$: query = search.trim().toLocaleLowerCase();
	$: tracks = (library?.tracks ?? []).filter((track) =>
		[track.title, track.artist, track.album, track.scenes, track.usage]
			.join(' ')
			.toLocaleLowerCase()
			.includes(query)
	);
	const duration = (seconds: number) =>
		`${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

	async function load() {
		loading = true;
		error = '';
		try {
			const response = await fetch('/audio/background-music/catalog.json');
			if (!response.ok) throw new Error('背景音乐暂时无法加载，请重试。');
			const result: Library[] = await response.json();
			if (disposed) return;
			libraries = result;
			chooseLibrary(result[0]?.id ?? '');
		} catch (e) {
			if (!disposed) error = e instanceof Error ? e.message : '背景音乐加载失败。';
		} finally {
			if (!disposed) loading = false;
		}
	}
	function chooseLibrary(id: string) {
		player?.pause();
		libraryId = id;
		selected = libraries.find((item) => item.id === id)?.tracks[0] ?? null;
		search = '';
		playbackError = '';
	}
	async function listen(track: Track) {
		player?.pause();
		selected = track;
		playbackError = '';
		await tick();
		if (disposed) return;
		try {
			await player.play();
		} catch {
			if (!disposed) playbackError = '未能开始播放，请使用播放器重试。';
		}
	}
	onMount(() => {
		load();
		return () => {
			disposed = true;
			player?.pause();
		};
	});
</script>

<section class="min-w-0 space-y-5" aria-label="背景音乐库">
	<div>
		<h2 class="font-semibold">背景音乐库</h2>
		<p class="mt-1 text-sm text-gray-500">按曲库浏览，试听并查看适合的场景与用途。</p>
	</div>
	{#if loading}
		<p role="status" class="py-8 text-sm text-gray-500">正在加载背景音乐…</p>
	{:else if error}
		<div role="alert" class="rounded-lg border border-red-200 p-4 text-sm dark:border-red-900">
			<p>{error}</p>
			<button type="button" class="mt-2 underline" on:click={load}>重新加载</button>
		</div>
	{:else if !libraries.length}
		<p class="py-8 text-sm text-gray-500">还没有背景音乐库。</p>
	{:else}
		<div class="flex flex-wrap gap-2" aria-label="选择背景音乐库">
			{#each libraries as item (item.id)}
				<button
					type="button"
					aria-pressed={libraryId === item.id}
					on:click={() => chooseLibrary(item.id)}
					class="rounded-lg px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 {libraryId ===
					item.id
						? 'bg-gray-900 text-white dark:bg-white dark:text-black'
						: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'}"
					>{item.name} <span class="ml-1 text-xs">{item.tracks.length} 首</span></button
				>
			{/each}
		</div>
		{#if library}
			<p class="text-sm text-gray-500">{library.description}</p>
		{/if}
		<div class="music-columns grid min-w-0 grid-cols-1 items-start gap-6">
			<div class="min-w-0">
				<label class="block text-sm">
					搜索音乐
					<input
						type="search"
						bind:value={search}
						placeholder="曲名、专辑、场景或用途"
						class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2.5 dark:border-gray-700"
					/>
				</label>
				<p role="status" class="my-3 text-xs text-gray-500">{tracks.length} 首音乐</p>
				<ul
					class="max-h-[60vh] divide-y divide-gray-100 overflow-y-auto overscroll-contain dark:divide-gray-800"
				>
					{#each tracks as track (track.id)}
						<li>
							<button
								type="button"
								on:click={() => listen(track)}
								aria-label={`试听 ${track.title}`}
								aria-pressed={selected?.id === track.id}
								class="flex w-full items-center gap-3 rounded-lg p-3 text-left hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] dark:hover:bg-gray-800 {selected?.id ===
								track.id
									? 'bg-gray-100 dark:bg-gray-800'
									: ''}"
							>
								<span class="shrink-0 text-xs text-gray-400">{track.id}</span>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm font-medium">{track.title}</span>
									<span class="mt-1 block truncate text-xs text-gray-500"
										>{track.album} · {track.year}</span
									>
								</span>
								<span class="shrink-0 text-xs text-gray-500">{duration(track.duration)}</span>
								<span class="shrink-0 text-xs" aria-hidden="true">试听</span>
							</button>
						</li>
					{:else}
						<li class="py-8 text-sm text-gray-500">没有匹配的音乐，请尝试其他曲名或场景。</li>
					{/each}
				</ul>
			</div>
			{#if selected}
				<section
					class="min-w-0 space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700"
					aria-label="音乐详情"
				>
					<div>
						<h3 class="font-semibold">{selected.title}</h3>
						<p class="mt-1 text-sm text-gray-500">
							{selected.artist} · {selected.album} · {selected.year}
						</p>
					</div>
					{#key selected.url}
						<audio
							bind:this={player}
							src={selected.url}
							controls
							preload="none"
							class="w-full"
							on:error={() => (playbackError = '音频加载失败，请重试或下载后播放。')}
						>
							<track kind="captions" />
						</audio>
					{/key}
					{#if playbackError}<p role="alert" class="text-sm text-red-600 dark:text-red-400">
							{playbackError}
						</p>{/if}
					<dl class="space-y-3 text-sm leading-6">
						<div>
							<dt class="font-medium">适用场景</dt>
							<dd class="mt-1 text-gray-600 dark:text-gray-300">{selected.scenes}</dd>
						</div>
						<div>
							<dt class="font-medium">用途建议</dt>
							<dd class="mt-1 text-gray-600 dark:text-gray-300">{selected.usage}</dd>
						</div>
					</dl>
					<details class="text-xs leading-5 text-gray-500">
						<summary class="cursor-pointer">出处与背景</summary>
						<p class="mt-2">{selected.background}</p>
					</details>
					<a
						href={selected.url}
						download
						class="inline-block rounded-lg border border-gray-200 px-3 py-2 text-sm hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-800"
						>下载 MP3</a
					>
				</section>
			{/if}
		</div>
	{/if}
</section>

<style>
	@container audio-studio (min-width: 56rem) {
		.music-columns {
			grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		}
	}
</style>
