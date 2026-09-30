<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import type { Voice } from '$lib/apis/audio-studio';
	import { videoStudio, type Portrait } from '$lib/apis/video-studio';
	import StudioMedia from './StudioMedia.svelte';
	export let voices: Voice[] = [];
	export let onuse: (portrait: Portrait) => void = () => {};
	let portraits: Portrait[] = [];
	let editing: Portrait | null = null;
	let name = '';
	let voice = '';
	let files: FileList;
	let input: HTMLInputElement;
	let busy = false;
	let error = '';
	let loading = true;
	async function refresh() {
		try {
			portraits = await videoStudio('/portraits');
			error = '';
		} catch (e) {
			error = `${e}`;
		} finally {
			loading = false;
		}
	}
	function edit(item: Portrait | null) {
		editing = item;
		name = item?.name ?? '';
		voice = item?.default_voice_id ?? '';
		if (input) {
			input.value = '';
			files = input.files as FileList;
		}
	}
	async function save() {
		busy = true;
		try {
			const form = new FormData();
			form.set('name', name);
			form.set('default_voice_id', voice);
			if (files?.[0]) form.set('file', files[0]);
			if (editing) form.set('revision', String(editing.revision));
			await videoStudio(editing ? `/portraits/${editing.id}` : '/portraits', {
				method: editing ? 'PUT' : 'POST',
				body: form
			});
			edit(null);
			await refresh();
			toast.success('人物已保存');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	async function remove(item: Portrait) {
		if (!confirm(`删除人物「${item.name}」？已生成的视频仍会保留。`)) return;
		busy = true;
		try {
			await videoStudio(`/portraits/${item.id}`, { method: 'DELETE' });
			if (editing?.id === item.id) edit(null);
			await refresh();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	onMount(refresh);
</script>

<div class="portraits grid min-w-0 grid-cols-1 items-start gap-8">
	<section class="min-w-0 space-y-4">
		<h2 class="font-semibold">{editing ? '编辑人物' : '添加人物'}</h2>
		<p class="text-sm leading-6 text-gray-500">
			使用正脸、嘴部清晰的照片。照片保存在本机，提交视频生成时才上传到所选引擎。
		</p>
		<form class="space-y-4" on:submit|preventDefault={save}>
			<label class="block text-sm"
				>人物名称<input
					bind:value={name}
					required
					maxlength="80"
					class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
					placeholder="例如：桂哥 · 正装"
				/></label
			>
			<label class="block text-sm"
				>人物照片{editing ? '（选填，上传后替换）' : ''}<input
					bind:this={input}
					bind:files
					type="file"
					accept="image/jpeg,image/png"
					required={!editing}
					class="mt-2 block w-full text-sm"
				/></label
			>
			<p class="text-xs leading-5 text-gray-500">
				JPG / PNG，不超过20 MB；短边至少256像素。保留原图比例，超大图片会缩小。
			</p>
			<label class="block text-sm"
				>默认音色<select
					bind:value={voice}
					class="mt-2 w-full rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
					><option value="">不设置</option>{#each voices as v}<option value={v.id}>{v.name}</option
						>{/each}</select
				></label
			>
			<div class="flex flex-wrap gap-3">
				<button
					type="submit"
					disabled={busy || !name.trim()}
					class="rounded-lg bg-gray-900 px-5 py-3 text-sm text-white disabled:opacity-40 dark:bg-white dark:text-black"
					>{busy ? '正在保存…' : '保存人物'}</button
				>{#if editing}<button
						type="button"
						class="px-3 text-sm"
						disabled={busy}
						on:click={() => edit(null)}>取消编辑</button
					>{/if}
			</div>
		</form>
	</section>
	<section class="min-w-0 space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="font-semibold">已保存的人物</h2>
			<button class="text-sm underline" on:click={refresh}>刷新</button>
		</div>
		{#if error}<p role="alert" class="text-sm text-red-600">{error}</p>{/if}
		{#if loading}<p role="status" class="text-sm text-gray-500">正在加载人物…</p>{/if}
		{#each portraits as item (item.id)}
			<article class="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-800">
				<StudioMedia path={`/portraits/${item.id}/image`} version={item.version} alt={item.name} />
				<h3 class="break-words font-medium">{item.name}</h3>
				<p class="text-xs text-gray-500">
					{item.width} × {item.height} · 默认音色：{voices.find(
						(v) => v.id === item.default_voice_id
					)?.name ?? '未设置或音色已不可用'}
				</p>
				<div class="flex flex-wrap gap-4 text-sm">
					<button class="underline" on:click={() => onuse(item)}>使用此人物</button><button
						class="underline"
						disabled={busy}
						on:click={() => edit(item)}>编辑</button
					><button class="text-red-600" disabled={busy} on:click={() => remove(item)}>删除</button>
				</div>
			</article>
		{:else}{#if !loading && !error}<p class="py-12 text-center text-sm text-gray-500">
					保存一张照片，建立你的第一个人物。
				</p>{/if}{/each}
	</section>
</div>

<style>
	@container audio-studio (min-width: 56rem) {
		.portraits {
			grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		}
	}
</style>
