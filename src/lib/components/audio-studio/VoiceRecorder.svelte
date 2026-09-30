<script lang="ts">
	import { onDestroy } from 'svelte';
	export let onrecord: (file: File, text: string) => void;
	const script =
		'你好，欢迎收听今天的分享。我会用自然、清晰的声音，为你讲述身边的故事。愿每一天都有新的发现，也有值得期待的美好。';
	let recording = false;
	let requesting = false;
	let seconds = 0;
	let error = '';
	let recorder: MediaRecorder | undefined;
	let stream: MediaStream | undefined;
	let timer: ReturnType<typeof setInterval> | undefined;
	let disposed = false;
	function release() {
		clearInterval(timer);
		stream?.getTracks().forEach((t) => t.stop());
	}
	function stop() {
		if (recorder?.state === 'recording') recorder.stop();
		release();
		recording = false;
	}
	async function start() {
		error = '';
		requesting = true;
		try {
			if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
				throw new Error(
					'当前地址或浏览器不支持录音。请通过 localhost 或 HTTPS 打开，也可以上传录音。'
				);
			stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			if (disposed) {
				release();
				return;
			}
			const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find((t) =>
				MediaRecorder.isTypeSupported(t)
			);
			recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
			const chunks: Blob[] = [];
			recorder.ondataavailable = (e) => {
				if (e.data.size) chunks.push(e.data);
			};
			recorder.onstop = () => {
				if (!disposed)
					onrecord(
						new File(chunks, 'recording', { type: recorder?.mimeType || 'audio/webm' }),
						script
					);
				release();
				recording = false;
			};
			recorder.onerror = () => {
				error = '录音中断，请重试';
				stop();
			};
			recorder.start();
			recording = true;
			seconds = 0;
			timer = setInterval(() => {
				seconds += 1;
				if (seconds >= 120) stop();
			}, 1000);
		} catch (e) {
			error = e instanceof Error ? e.message : '无法访问麦克风，请检查权限';
			release();
		} finally {
			requesting = false;
		}
	}
	onDestroy(() => {
		disposed = true;
		stop();
	});
</script>

<div class="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-800">
	<p class="text-sm text-gray-500">请自然朗读下方文字，录完可试听或重新录制。</p>
	<p class="text-sm leading-7">{script}</p>
	<div class="flex items-center gap-3">
		{#if recording}<button
				type="button"
				class="rounded-lg bg-red-600 px-4 py-2 text-sm text-white"
				on:click={stop}>停止录音</button
			>
		{:else}<button
				type="button"
				class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-black"
				disabled={requesting}
				on:click={start}>{requesting ? '正在请求麦克风…' : '开始录音'}</button
			>{/if}
		<span class="text-sm tabular-nums" role="status"
			>{recording ? `录音中 · ${seconds} 秒` : ''}</span
		>
	</div>
	{#if error}<p class="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>{/if}
</div>
