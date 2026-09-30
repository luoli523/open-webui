<script lang="ts">
	import { onDestroy } from 'svelte';
	import { user } from '$lib/stores';
	import { toast } from 'svelte-sonner';
	import { studio, type Voice } from '$lib/apis/audio-studio';
	import VoiceRecorder from './VoiceRecorder.svelte';
	export let voices: Voice[] = [];
	export let refresh: () => Promise<void>;
	let editing: Voice | null = null;
	let name = '';
	let text = '';
	let file: File | null = null;
	let source: 'upload' | 'record' = 'upload';
	let saving = false;
	let transcribing = false;
	let preview = '';
	let referencePreview = '';
	let previewId = '';
	let generation = 0;
	let disposed = false;
	let fileInput: HTMLInputElement;
	let deleting = '';
	function selectFile(next: File, transcript = '') {
		generation += 1;
		file = next;
		text = transcript;
		if (preview) URL.revokeObjectURL(preview);
		preview = URL.createObjectURL(next);
	}
	function reset() {
		editing = null;
		name = '';
		text = '';
		file = null;
		generation += 1;
		if (preview) URL.revokeObjectURL(preview);
		preview = '';
		if (fileInput) fileInput.value = '';
	}
	function edit(v: Voice) {
		reset();
		editing = v;
		name = v.name;
		text = v.ref_text || '';
	}
	async function save() {
		saving = true;
		try {
			const form = new FormData();
			form.set('name', name.trim());
			form.set('ref_text', text.trim());
			if (file) form.set('file', file);
			await studio(editing ? `/voices/${editing.id}` : '/voices', {
				method: editing ? 'PUT' : 'POST',
				body: form
			});
			reset();
			await refresh();
			toast.success('音色已保存，可以用于生成播报');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			saving = false;
		}
	}
	async function transcribe() {
		if (!file) return;
		const current = generation;
		transcribing = true;
		try {
			const form = new FormData();
			form.set('file', file);
			const result = await studio('/transcriptions', { method: 'POST', body: form });
			if (!disposed && current === generation) text = result.text;
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			transcribing = false;
		}
	}
	async function listen(v: Voice) {
		try {
			const blob = await studio(`/voices/${v.id}/reference`, {}, true);
			if (disposed) return;
			if (referencePreview) URL.revokeObjectURL(referencePreview);
			referencePreview = URL.createObjectURL(blob);
			previewId = v.id;
		} catch (e) {
			toast.error(`${e}`);
		}
	}
	async function remove(id: string) {
		try {
			await studio(`/voices/${id}`, { method: 'DELETE' });
			deleting = '';
			if (editing?.id === id) reset();
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		}
	}
	onDestroy(() => {
		disposed = true;
		generation += 1;
		if (preview) URL.revokeObjectURL(preview);
		if (referencePreview) URL.revokeObjectURL(referencePreview);
	});
</script>

<div class="voice-columns grid min-w-0 grid-cols-1 gap-6">
	<section class="min-w-0 space-y-4">
		<h2 class="font-semibold">{editing ? `编辑音色 · ${editing.name}` : '创建新音色'}</h2>
		<div class="flex gap-2">
			<button
				class="rounded-lg px-3 py-2 text-sm {source === 'upload'
					? 'bg-gray-100 dark:bg-gray-800'
					: ''}"
				on:click={() => (source = 'upload')}>上传录音</button
			><button
				class="rounded-lg px-3 py-2 text-sm {source === 'record'
					? 'bg-gray-100 dark:bg-gray-800'
					: ''}"
				on:click={() => (source = 'record')}>麦克风录制</button
			>
		</div>
		{#if source === 'upload'}
			<label class="block rounded-xl border border-dashed border-gray-300 p-5 dark:border-gray-700"
				><span class="mb-3 block text-sm">选择清晰的单人录音 · 1–120 秒，最大 20 MB</span><input
					bind:this={fileInput}
					type="file"
					accept="audio/*,.m4a,.wav,.mp3,.webm"
					disabled={saving}
					on:change={(e) => {
						const f = e.currentTarget.files?.[0];
						if (f) selectFile(f);
					}}
					class="max-w-full text-sm"
				/></label
			>
		{:else}<VoiceRecorder onrecord={selectFile} />{/if}
		{#if preview}<audio class="w-full" src={preview} controls preload="metadata"
				><track kind="captions" /></audio
			>{/if}
		{#if editing && !file}<p class="text-sm text-gray-500">未选择新录音时保留已有参考录音。</p>{/if}
		<label class="block text-sm"
			>音色名称<input
				class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
				maxlength="80"
				bind:value={name}
				placeholder="例如：我的日常声音"
			/></label
		>
		<div class="flex items-center justify-between gap-2">
			<label for="reference-text" class="text-sm"
				>参考原文 <span class="text-gray-500">（选填）</span></label
			><button
				class="text-sm underline disabled:opacity-40"
				disabled={!file || transcribing || saving}
				on:click={transcribe}>{transcribing ? '正在本地识别…' : '自动识别原文'}</button
			>
		</div>
		<textarea
			id="reference-text"
			class="w-full rounded-lg border border-gray-200 bg-transparent p-3 text-sm dark:border-gray-700"
			rows="4"
			maxlength="10000"
			bind:value={text}
			placeholder="录音里说的话。留空即可仅用录音创建音色。"
		></textarea>
		<p class="text-xs leading-5 text-gray-500">
			提供准确原文可增加参考信息；留空使用声音特征。自动识别后可修改文字，现场录音请核对是否与朗读文本一致。
		</p>
		<div class="flex gap-3">
			<button
				class="rounded-lg bg-gray-900 px-4 py-2.5 text-sm text-white disabled:opacity-40 dark:bg-white dark:text-black"
				disabled={saving || transcribing || !name.trim() || (!editing && !file)}
				on:click={save}
				>{saving ? '正在保存…' : text.trim() ? '保存音色' : '仅用录音保存音色'}</button
			>{#if editing}<button class="text-sm" on:click={reset}>取消编辑</button>{/if}
		</div>
	</section>
	<section class="min-w-0">
		<h2 class="mb-4 font-semibold">已保存的声音</h2>
		<div class="divide-y divide-gray-100 dark:divide-gray-800">
			{#each voices.filter((v) => v.kind === 'clone') as voice (voice.id)}
				<div class="space-y-3 py-4">
					<div class="flex items-start justify-between gap-3">
						<div>
							<p class="font-medium">{voice.name}</p>
							<p class="mt-1 text-xs text-gray-500">
								{voice.mode === 'reference' ? '录音 + 参考原文' : '仅参考录音'} · {voice.owner_id
									? '个人音色'
									: '已有音色'}
							</p>
						</div>
						<button class="text-sm underline" on:click={() => listen(voice)}>试听录音</button>
					</div>
					{#if previewId === voice.id && referencePreview}<audio
							class="w-full"
							src={referencePreview}
							controls><track kind="captions" /></audio
						>{/if}
					{#if voice.owner_id === $user?.id || $user?.role === 'admin'}<div
							class="flex gap-4 text-sm"
						>
							<button on:click={() => edit(voice)}>编辑</button><button
								class="text-red-600 dark:text-red-400"
								on:click={() => (deleting = voice.id)}>删除</button
							>
						</div>{/if}
					{#if deleting === voice.id}<div
							class="rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-900"
						>
							<p>删除“{voice.name}”？已生成的播报会保留。</p>
							<div class="mt-2 flex gap-4">
								<button class="text-red-600" on:click={() => remove(voice.id)}>确认删除</button
								><button on:click={() => (deleting = '')}>取消</button>
							</div>
						</div>{/if}
				</div>
			{:else}<p class="py-6 text-sm text-gray-500">
					还没有保存的音色，上传或录制一段声音开始。
				</p>{/each}
		</div>
	</section>
</div>

<style>
	@container audio-studio (min-width: 56rem) {
		.voice-columns {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
</style>
