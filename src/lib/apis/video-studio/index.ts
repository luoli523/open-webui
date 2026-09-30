import { WEBUI_API_BASE_URL } from '$lib/constants';

export type Portrait = {
	id: string;
	name: string;
	version: string;
	revision: number;
	default_voice_id: string;
	width: number;
	height: number;
	input_type: string;
};
export type Provider = {
	id: string;
	name: string;
	cloud: boolean;
	paid: boolean;
	configured: boolean;
	enabled: boolean;
	input_types: string[];
	aspect_ratios: string[];
	resolutions: string[];
	preview_resolution: string;
	final_resolution: string;
	max_duration_seconds: number;
	duration_note: string;
};
export type VideoJob = {
	auto_captions?: boolean;
	caption_ready?: boolean;
	caption_hash?: string;
	caption_status?: string;
	caption_operation?: string;
	caption_version?: number;
	caption_error?: string;
	id: string;
	revision: number;
	title: string;
	credit?: string;
	status: string;
	stage: 'preview' | 'final';
	portrait_name: string;
	provider_id: string;
	aspect_ratio: string;
	resolution: string;
	duration: number;
	full_duration: number;
	created_at: number;
	fingerprint: string;
	external_id?: string;
	error?: string;
	preview_id?: string;
	attempt: number;
	retry_requires_payment: boolean;
};
export type Receipt = {
	id: string;
	job_id: string;
	status: string;
	error?: string;
	variant?: 'original' | 'captioned';
	artifact_hash?: string;
};

export async function videoStudio(path: string, options: RequestInit = {}, binary = false) {
	const headers = new Headers(options.headers);
	headers.set('Authorization', `Bearer ${localStorage.token}`);
	if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
	const response = await fetch(`${WEBUI_API_BASE_URL}/video-studio${path}`, {
		...options,
		headers
	});
	if (!response.ok) {
		const data = await response.json().catch(() => ({}));
		throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请稍后重试');
	}
	return binary ? response.blob() : response.json();
}
export const videoPost = (path: string, data: unknown = {}) =>
	videoStudio(path, { method: 'POST', body: JSON.stringify(data) });

export async function downloadVideo(job: VideoJob, original = false) {
	const blob = await videoStudio(
		`/jobs/${job.id}/video${original ? '?variant=original' : ''}`,
		{},
		true
	);
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = `${job.title.replace(/[\\/:*?"<>|]/g, '_')}-${job.stage}.mp4`;
	link.click();
	setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export type CaptionCue = { start: number; end: number; text: string };
export type CaptionStyle = {
	size: number;
	color: string;
	position: 'bottom' | 'top';
	margin: number;
	background: boolean;
};
export type VideoCaption = {
	render_ready: boolean;
	revision: number;
	status: string;
	operation: string;
	error?: string;
	cues: CaptionCue[];
	style: CaptionStyle;
	version: number;
	rendered_version: number | null;
	mode?: string;
	duration?: number;
	language: string;
};
export async function downloadCaption(job: VideoJob, format: 'srt' | 'vtt' | 'ass' | 'mp4') {
	const blob = await videoStudio(`/jobs/${job.id}/captions/file?format=${format}`, {}, true);
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = `${job.title.replace(/[\\/:*?"<>|]/g, '_')}-字幕.${format}`;
	link.click();
	setTimeout(() => URL.revokeObjectURL(url), 60000);
}
