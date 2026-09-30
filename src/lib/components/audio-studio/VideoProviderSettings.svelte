<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { videoStudio } from '$lib/apis/video-studio';
	export let onchange: () => void = () => {};
	let key = '';
	let enabled = false;
	let configured = false;
	let loaded = false;
	let busy = false;
	let error = '';
	async function load() {
		try {
			const data = await videoStudio('/config');
			configured = data.configured;
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
			await videoStudio('/config', {
				method: 'PUT',
				body: JSON.stringify({ api_key: key.trim() || null, enabled })
			});
			key = '';
			await load();
			onchange();
			toast.success('视频引擎配置已保存');
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
	onMount(load);
</script>

<details class="rounded-xl border border-gray-200 p-4 dark:border-gray-800">
	<summary class="cursor-pointer text-sm font-medium"
		>HeyGen 设置（管理员） · {configured ? '已保存密钥' : '尚未配置'}</summary
	>
	<div class="mt-4 space-y-4 text-sm">
		{#if error}<p role="alert">
				{error} <button class="underline" on:click={load}>重试</button>
			</p>{/if}
		<label class="block"
			>API Key<input
				type="password"
				autocomplete="new-password"
				bind:value={key}
				placeholder={configured ? '留空保留原密钥' : '输入 HeyGen API Key'}
				class="mt-2 w-full rounded-lg border border-gray-200 bg-transparent p-3 dark:border-gray-700"
			/></label
		>
		<label class="flex items-center gap-2"
			><input type="checkbox" bind:checked={enabled} />允许提交新的视频生成任务</label
		>
		<p class="text-xs leading-5 text-gray-500">
			密钥仅保存在服务端。预览和完整版均会消耗 HeyGen
			额度，费用以账户实际计费为准。暂停新任务不会取消已提交的任务。
		</p>
		<button
			disabled={!loaded || busy || (!configured && !key.trim())}
			on:click={save}
			class="rounded-lg bg-gray-100 px-4 py-2 disabled:opacity-40 dark:bg-gray-800"
			>{busy ? '正在保存…' : '保存设置'}</button
		>
	</div>
</details>
