import { WEBUI_API_BASE_URL } from '$lib/constants';

export type Voice = {
	id: string;
	name: string;
	kind: 'preset' | 'clone';
	owner_id?: string;
	ref_text?: string;
	mode?: string;
	version: string;
	engine?: string;
	language?: string;
	credit?: string;
	license_url?: string;
};
export type Job = {
	id: string;
	title: string;
	text: string;
	voice_id: string;
	voice_name: string;
	credit?: string;
	speed: number;
	status: string;
	created_at: number;
	error?: string;
};
export type Delivery = {
	id: string;
	job_id: string;
	status: string;
	error?: string;
	message_id?: number;
};

export async function studio(path: string, options: RequestInit = {}, binary = false) {
	const headers = new Headers(options.headers);
	headers.set('Authorization', `Bearer ${localStorage.token}`);
	if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
	const response = await fetch(`${WEBUI_API_BASE_URL}/audio-studio${path}`, {
		...options,
		headers
	});
	if (!response.ok) {
		const data = await response.json().catch(() => ({}));
		throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请稍后重试');
	}
	return binary ? response.blob() : response.json();
}

export const post = (path: string, data: unknown) =>
	studio(path, { method: 'POST', body: JSON.stringify(data) });
