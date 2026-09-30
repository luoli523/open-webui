<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { user } from '$lib/stores';
	import { studio, post } from '$lib/apis/audio-studio';
	import WorkingIndicator from './WorkingIndicator.svelte';
	export let disabled = false;
	export let onrecord: (file: File, text: string) => void;
	export let onclear: () => void;
	export let onbusy: (busy: boolean) => void;
	let instructions = '';

	const languages = [
		{
			value: 'chinese',
			label: '中文',
			sample: '你好，欢迎来到今天的故事。让我们一起出发，探索这个奇妙的世界吧！'
		},
		{
			value: 'english',
			label: '英语 · English',
			sample:
				'Hello! Welcome to our story. Let us set off together and explore this wonderful world!'
		},
		{
			value: 'japanese',
			label: '日语 · 日本語',
			sample:
				'こんにちは。今日の物語へようこそ。一緒に出発して、この素晴らしい世界を探検しましょう！'
		},
		{
			value: 'korean',
			label: '韩语 · 한국어',
			sample:
				'안녕하세요. 오늘의 이야기에 오신 것을 환영합니다. 함께 출발해서 이 멋진 세상을 탐험해 봐요!'
		},
		{
			value: 'german',
			label: '德语 · Deutsch',
			sample:
				'Hallo! Willkommen zu unserer Geschichte. Lasst uns gemeinsam aufbrechen und diese wunderbare Welt entdecken!'
		},
		{
			value: 'french',
			label: '法语 · Français',
			sample:
				'Bonjour ! Bienvenue dans notre histoire. Partons ensemble explorer ce monde merveilleux !'
		},
		{
			value: 'russian',
			label: '俄语 · Русский',
			sample:
				'Здравствуйте! Добро пожаловать в нашу историю. Давайте вместе отправимся в путь и исследуем этот удивительный мир!'
		},
		{
			value: 'portuguese',
			label: '葡萄牙语 · Português',
			sample:
				'Olá! Bem-vindos à nossa história. Vamos partir juntos e explorar este mundo maravilhoso!'
		},
		{
			value: 'spanish',
			label: '西班牙语 · Español',
			sample:
				'¡Hola! Bienvenidos a nuestra historia. ¡Salgamos juntos a explorar este maravilloso mundo!'
		},
		{
			value: 'italian',
			label: '意大利语 · Italiano',
			sample:
				'Ciao! Benvenuti nella nostra storia. Partiamo insieme alla scoperta di questo meraviglioso mondo!'
		}
	];
	let language = 'chinese';
	let text = languages[0].sample;
	let busy = false;
	let status = '';
	let error = '';
	let controller: AbortController;
	let disposed = false;
	const key = () => `audio-studio:voice-design:${$user?.id}`;
	function remember(id: string) {
		try {
			localStorage.setItem(key(), id);
		} catch {
			/* Optional resume hint. */
		}
	}
	function forget() {
		try {
			localStorage.removeItem(key());
		} catch {
			/* Optional resume hint. */
		}
	}
	async function receive(
		job: { id: string; status: string; text: string; error?: string },
		signal: AbortSignal
	) {
		while (!signal.aborted && ['queued', 'running'].includes(job.status)) {
			status = job.status === 'queued' ? '声音设计排队中…' : '正在生成声音，首次加载模型可能较慢…';
			await new Promise((resolve) => setTimeout(resolve, 1500));
			if (signal.aborted) return;
			job = await studio(`/voice-designs/${job.id}`, { signal });
		}
		if (signal.aborted) return;
		if (job.status !== 'completed') throw new Error(job.error || '声音设计中断，请重新生成');
		const blob = await studio(`/voice-designs/${job.id}/audio`, { signal }, true);
		if (signal.aborted) return;
		onrecord(new File([blob], `voice-design-${job.id}.wav`, { type: 'audio/wav' }), job.text);
		status = '声音已生成。请在下方试听，填写名称后保存音色。';
	}
	async function generate() {
		if (busy || disabled) return;
		controller = new AbortController();
		busy = true;
		onbusy(true);
		onclear();
		error = '';
		status = '提交声音设计…';
		forget();
		try {
			const job = await post('/voice-designs', { instructions, text, language });
			remember(job.id);
			if (!disposed) await receive(job, controller.signal);
		} catch (e) {
			if (!disposed) error = `${e}`;
		} finally {
			busy = false;
			if (!disposed) onbusy(false);
		}
	}
	onMount(() => {
		let id = '';
		try {
			id = localStorage.getItem(key()) || '';
		} catch {
			/* Optional resume hint. */
		}
		if (!id) return;
		controller = new AbortController();
		busy = true;
		onbusy(true);
		(async () => {
			try {
				const job = await studio(`/voice-designs/${encodeURIComponent(id)}`, {
					signal: controller.signal
				});
				if (disposed) return;
				instructions = job.instructions;
				text = job.text;
				language = job.language;
				await receive(job, controller.signal);
			} catch (e) {
				if (!disposed) error = `${e}`;
			} finally {
				busy = false;
				if (!disposed) onbusy(false);
			}
		})();
	});
	onDestroy(() => {
		disposed = true;
		controller?.abort();
		onbusy(false);
	});
</script>

<div class="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
	<p class="text-sm text-gray-500">
		用文字描述想要的声音，本地生成试听录音。满意后保存为音色，即可用于人物和播报。
	</p>
	<label class="block text-sm"
		>声音描述<textarea
			bind:value={instructions}
			disabled={busy || disabled}
			maxlength="2000"
			rows="3"
			placeholder="例如：清亮活泼的年轻女性，卡通角色风格，普通话清晰，语调轻快自然。"
			class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-2 dark:border-gray-700"
		></textarea></label
	>
	<label class="block text-sm"
		>试听语言<select
			bind:value={language}
			disabled={busy || disabled}
			on:change={() => {
				text = languages.find((item) => item.value === language)?.sample ?? '';
			}}
			class="ml-3 rounded-lg bg-gray-100 p-2 dark:bg-gray-800"
			>{#each languages as item}<option value={item.value}>{item.label}</option>{/each}</select
		></label
	>
	<label class="block text-sm"
		>试听文案<textarea
			bind:value={text}
			disabled={busy || disabled}
			maxlength="500"
			rows="3"
			class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-2 dark:border-gray-700"
		></textarea></label
	>
	<button
		type="button"
		disabled={busy || disabled || !instructions.trim() || !text.trim()}
		on:click={generate}
		class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-40 dark:bg-white dark:text-black"
	>
		{#if busy}<WorkingIndicator />{/if}{busy ? '正在设计…' : '生成设计音色'}
	</button>
	{#if status}<p role="status" class="text-xs text-gray-500">{status}</p>{/if}
	{#if error}<p role="alert" class="text-sm text-red-600 dark:text-red-400">{error}</p>{/if}
</div>
