<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { videoStudio } from '$lib/apis/video-studio';
	export let onchange: () => void = () => {};
	let baseUrl = 'http://127.0.0.1:8092';
	let enabled = false;
	let busy = false;
	let loaded = false;
	let error = '';
	async function load() {
		try {
			const data = await videoStudio('/config/local-h3');
			baseUrl = data.base_url;
			enabled = data.enabled;
			loaded = true;
			error = '';
		} catch (e) {
			error = `${e}`;
		}
	}
	async function save() {
		busy = true;
		try {
			await videoStudio('/config/local-h3', {
				method: 'PUT',
				body: JSON.stringify({ base_url: baseUrl, enabled })
			});
			onchange();
			toast.success('本地 H3 设置已保存');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	onMount(load);
</script>

<details class="rounded-xl border border-gray-200 p-4 dark:border-gray-800">
	<summary class="cursor-pointer text-sm font-medium">本地 H3 设置（管理员）</summary>
	<div class="mt-4 space-y-4 text-sm">
		{#if error}<p role="alert">
				{error} <button class="underline" on:click={load}>重试</button>
			</p>{/if}
		<label class="block"
			>服务地址<input
				bind:value={baseUrl}
				class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
			/></label
		>
		<label class="flex items-center gap-2"
			><input type="checkbox" bind:checked={enabled} />允许本地视频生成</label
		>
		<p class="text-xs leading-5 text-gray-500">
			在本机生成，无云端生成费用。暂停新任务不会取消已提交的任务。
		</p>
		<button
			disabled={busy || !loaded}
			on:click={save}
			class="rounded-lg bg-gray-100 px-4 py-2 disabled:opacity-40 dark:bg-gray-800"
			>{busy ? '正在保存…' : '保存设置'}</button
		>
	</div>
</details>
