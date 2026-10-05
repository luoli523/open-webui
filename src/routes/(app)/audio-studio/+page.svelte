<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { user, showSidebar, WEBUI_NAME } from '$lib/stores';
	import Sidebar from '$lib/components/icons/Sidebar.svelte';
	import ImageStudio from '$lib/components/audio-studio/ImageStudio.svelte';
	import VoiceLibrary from '$lib/components/audio-studio/VoiceLibrary.svelte';
	import JobResult from '$lib/components/audio-studio/JobResult.svelte';
	import TelegramSettings from '$lib/components/audio-studio/TelegramSettings.svelte';
	import PortraitLibrary from '$lib/components/audio-studio/PortraitLibrary.svelte';
	import DigitalHumanStudio from '$lib/components/audio-studio/DigitalHumanStudio.svelte';
	import WorkingIndicator from '$lib/components/audio-studio/WorkingIndicator.svelte';
	import VoicePreview from '$lib/components/audio-studio/VoicePreview.svelte';
	import { studio, post, type Voice, type Job, type Delivery } from '$lib/apis/audio-studio';
	let tab = 'voices';
	let videoAudio = '';
	let videoPortrait = '';
	let voices: Voice[] = [];
	let jobs: Job[] = [];
	let deliveries: Delivery[] = [];
	let voice = '';
	let text = '';
	let title = '';
	let speed = 1;
	let submitting = false;
	let loading = true;
	let error = '';
	let telegram = false;
	let refreshing = false;
	async function loadVoices() {
		voices = await studio('/voices');
		if (!voices.some((v) => v.id === voice))
			voice = voices.find((v) => v.id === 'guige')?.id || voices[0]?.id || '';
	}
	async function refresh() {
		if (refreshing) return;
		refreshing = true;
		try {
			jobs = await studio('/jobs');
			if ($user?.role === 'admin') deliveries = await studio('/deliveries');
		} finally {
			refreshing = false;
		}
	}
	async function load() {
		loading = true;
		error = '';
		try {
			await Promise.all([loadVoices(), refresh()]);
		} catch (e) {
			error = `${e}`;
		} finally {
			loading = false;
		}
	}
	async function generate() {
		submitting = true;
		try {
			await post('/jobs', { text, voice_id: voice, speed, title });
			await refresh();
			toast.success('已加入生成队列');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			submitting = false;
		}
	}
	onMount(() => {
		load();
		const timer = setInterval(() => refresh().catch(() => {}), 3000);
		const voiceTimer = setInterval(() => loadVoices().catch(() => {}), 15000);
		const reloadVoices = () => loadVoices().catch(() => {});
		window.addEventListener('focus', reloadVoices);
		return () => {
			clearInterval(timer);
			clearInterval(voiceTimer);
			window.removeEventListener('focus', reloadVoices);
		};
	});
</script>

<svelte:head><title>视频语音工作台 · {$WEBUI_NAME}</title></svelte:head>
<div
	class="flex h-screen max-h-[100dvh] w-full min-w-0 flex-col overflow-hidden transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: 'max-w-full'}"
>
	<header
		class="flex shrink-0 items-center gap-3 border-b border-gray-100 px-4 py-3 dark:border-gray-800"
	>
		<button
			aria-label="切换侧栏"
			class="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-800"
			on:click={() => showSidebar.set(!$showSidebar)}><Sidebar className="size-5" /></button
		>
		<h1 class="text-lg font-semibold">视频语音工作台</h1>
	</header>
	<main class="studio-content min-h-0 min-w-0 flex-1 overflow-y-auto">
		<div class="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
			<div>
				<p class="text-sm text-gray-500">从文字播报到人物口播，保存声音与形象。</p>
				<nav
					class="mt-4 flex flex-wrap gap-x-5 border-b border-gray-200 dark:border-gray-800"
					aria-label="工作台页面"
				>
					{#each [{ id: 'voices', label: '音色库' }, { id: 'portraits', label: '人物库' }, { id: 'generate', label: '生成播报' }, { id: 'video', label: '生成视频' }, ...($user?.role === 'admin' ? [{ id: 'images', label: '生成图像' }] : [])] as item}<button
							class="border-b-2 px-1 py-3 text-sm {tab === item.id
								? 'border-gray-900 font-medium dark:border-white'
								: 'border-transparent text-gray-500'}"
							aria-current={tab === item.id ? 'page' : undefined}
							on:click={() => (tab = item.id)}>{item.label}</button
						>{/each}
				</nav>
			</div>
			{#if error}<div role="alert" class="rounded-lg border border-red-200 p-4 text-sm">
					<p>{error}</p>
					<button class="mt-2 underline" on:click={load}>重新连接</button>
				</div>{/if}
			{#if loading}<p role="status" class="py-8 text-sm text-gray-500">正在加载工作台…</p>
			{:else if tab === 'voices'}<VoiceLibrary {voices} refresh={loadVoices} />
			{:else if tab === 'portraits'}<PortraitLibrary
					{voices}
					refreshVoices={loadVoices}
					onuse={(p) => {
						videoPortrait = p.id;
						if (voices.some((v) => v.id === p.default_voice_id)) voice = p.default_voice_id;
						tab = 'video';
					}}
				/>
			{:else if tab === 'images' && $user?.role === 'admin'}<ImageStudio />
			{:else if tab === 'video'}<DigitalHumanStudio
					audioJobs={jobs}
					{voices}
					initialAudio={videoAudio}
					initialPortrait={videoPortrait}
					managePortraits={() => (tab = 'portraits')}
				/>
			{:else}<div class="studio-columns grid min-w-0 grid-cols-1 items-start gap-8">
					<section class="min-w-0 space-y-5">
						<h2 class="font-semibold">创建播报</h2>
						<label class="block text-sm"
							>选择声音<select
								bind:value={voice}
								class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
								><option value="" disabled>请选择音色</option><optgroup label="克隆音色"
									>{#each voices.filter((v) => v.kind === 'clone') as v}<option value={v.id}
											>{v.name}</option
										>{/each}</optgroup
								><optgroup label="预设音色"
									>{#each voices.filter((v) => v.kind === 'preset') as v}<option value={v.id}
											>{v.name}</option
										>{/each}</optgroup
								></select
							></label
						>
						<VoicePreview voice={voices.find((v) => v.id === voice)} />
						<label class="block text-sm"
							>标题 <span class="text-gray-500">（选填）</span><input
								class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
								bind:value={title}
								maxlength="100"
								placeholder="便于查找和下载"
							/></label
						>
						<label class="block text-sm"
							>播报文案<textarea
								class="mt-2 w-full rounded-xl border border-gray-200 bg-transparent p-4 leading-7 dark:border-gray-700"
								rows="9"
								bind:value={text}
								maxlength="10000"
								placeholder="输入需要播报的内容……"
							></textarea></label
						>
						<div class="flex items-center justify-between gap-3 text-sm">
							<label class="flex items-center gap-2"
								>语速 <select class="rounded-lg bg-gray-100 p-2 dark:bg-gray-800" bind:value={speed}
									>{#each [0.5, 0.75, 1, 1.25, 1.5, 2] as value}<option {value}>{value}×</option
										>{/each}</select
								></label
							><span class="text-xs text-gray-500">{text.length} / 10000</span>
						</div>
						<button
							class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gray-900 p-3 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-black"
							disabled={submitting || !text.trim() || !voice}
							on:click={generate}
							>{#if submitting}<WorkingIndicator />{/if}{submitting
								? '正在提交…'
								: '生成播报'}</button
						>
						{#if $user?.role === 'admin'}<TelegramSettings
								onchange={(value) => (telegram = value)}
							/>{/if}
					</section>
					<section class="min-w-0">
						<div class="flex items-center justify-between">
							<h2 class="font-semibold">最近生成</h2>
							<button
								class="text-xs text-gray-500"
								on:click={() => refresh().catch((e) => toast.error(`${e}`))}>刷新</button
							>
						</div>
						{#each jobs as job (job.id)}<JobResult
								{job}
								{refresh}
								onvideo={(item) => {
									videoAudio = item.id;
									tab = 'video';
								}}
								canSend={$user?.role === 'admin' && telegram}
								delivery={deliveries.find((d) => d.job_id === job.id)}
							/>{:else}<div class="py-12 text-center text-sm leading-7 text-gray-500">
								还没有播报记录<br />输入文案，生成第一段音频。
							</div>{/each}
					</section>
				</div>{/if}
		</div>
	</main>
</div>

<style>
	.studio-content {
		container: audio-studio / inline-size;
	}

	@container audio-studio (min-width: 56rem) {
		.studio-columns {
			grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
		}
	}
</style>
