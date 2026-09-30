<script lang="ts">
	import Spinner from '$lib/components/common/Spinner.svelte';
</script>

<span class="working inline-flex shrink-0 align-middle" aria-hidden="true"
	><Spinner className="size-4" /></span
>

<style>
	@media (prefers-reduced-motion: reduce) {
		.working :global(.spinner_ajPY) {
			animation: none !important;
		}
	}
</style>
