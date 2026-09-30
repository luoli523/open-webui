<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { studio } from '$lib/apis/audio-studio';
	export let onchange: (configured: boolean) => void;
	let chat = '';
	let token = '';
	let configured = false;
	let busy = false;
	let open = false;
	onMount(async () => {
		try {
			const c = await studio('/telegram/config');
			chat = c.chat_id;
			configured = c.configured;
			onchange(configured);
		} catch (e) {
			toast.error(`${e}`);
		}
	});
	async function save() {
		busy = true;
		try {
			const c = await studio('/telegram/config', {
				method: 'PUT',
				body: JSON.stringify({ chat_id: chat, token: token.trim() || null })
			});
			configured = c.configured;
			token = '';
			onchange(configured);
			toast.success('Telegram 设置已保存');
			open = false;
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			busy = false;
		}
	}
</script>

<div class="rounded-xl border border-gray-200 p-4 dark:border-gray-800">
	<button
		class="flex w-full items-center justify-between text-sm"
		aria-expanded={open}
		on:click={() => (open = !open)}
		><span>Telegram 设置</span><span class="text-xs text-gray-500"
			>{configured ? '已配置' : '尚未配置'} · {open ? '收起' : '展开'}</span
		></button
	>
	{#if open}<div class="mt-4 space-y-3">
			<p class="text-xs leading-5 text-gray-500">
				设置默认接收聊天。私聊请先向 Bot 发送 /start；群组或频道需授予 Bot 发送权限。
			</p>
			<label class="block text-sm"
				>Bot Token<input
					class="mt-1 w-full rounded-lg border border-gray-200 bg-transparent p-2 dark:border-gray-700"
					type="password"
					autocomplete="new-password"
					bind:value={token}
					placeholder={configured ? '留空保留已有 Token' : '填写 Bot Token'}
				/></label
			><label class="block text-sm"
				>目标 chat_id<input
					class="mt-1 w-full rounded-lg border border-gray-200 bg-transparent p-2 dark:border-gray-700"
					bind:value={chat}
					placeholder="个人、群组或频道 ID"
				/></label
			><button
				class="rounded-lg bg-gray-100 px-3 py-2 text-sm dark:bg-gray-800"
				disabled={busy}
				on:click={save}>{busy ? '保存中…' : '保存设置'}</button
			>
		</div>{/if}
</div>
