<script lang="ts">
	export let accept = '';
	export let label = '选择文件';
	export let hint = '';
	export let fileName = '';
	export let disabled = false;
	export let onselect: (file: File) => void;
	let input: HTMLInputElement;
</script>

<div
	class="space-y-3 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4 transition-colors hover:border-gray-400 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-900/50 dark:hover:border-gray-500 dark:hover:bg-gray-900"
>
	<input
		bind:this={input}
		type="file"
		{accept}
		{disabled}
		aria-label={label}
		class="hidden"
		on:change={(event) => {
			const file = event.currentTarget.files?.[0];
			if (file) onselect(file);
			event.currentTarget.value = '';
		}}
	/>
	<button
		type="button"
		{disabled}
		on:click={() => input.click()}
		class="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
	>
		<svg
			aria-hidden="true"
			class="size-5"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"><path d="M12 16V4m-4 4 4-4 4 4M4 16v4h16v-4" /></svg
		>
		{label}
	</button>
	<p class="break-all text-sm" aria-live="polite">{fileName || '尚未选择文件'}</p>
	{#if hint}<p class="text-xs leading-5 text-gray-500">{hint}</p>{/if}
</div>
