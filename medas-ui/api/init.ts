import { ChatMessageProps } from "@/model/ChatMessage";

// Server-side only: this module is imported from a Server Component, so the
// backend origin never reaches the browser bundle and needs no NEXT_PUBLIC_.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

interface InitResponse {
	messages: ChatMessageProps[];
}

const init = async (user: string): Promise<InitResponse> => {
	// `user` is a query parameter, not a body. The endpoint is a GET, and
	// fetch rejects a GET carrying a body before the request leaves the
	// process -- the previous JSON body could never have arrived.
	const url = `${API_BASE_URL}/init?user=${encodeURIComponent(user)}`;

	const response = await fetch(url);

	if (!response.ok) {
		throw new Error(`Failed to init profile (${response.status})`);
	}

	// json() is `any` either way, so this annotates rather than asserts: it
	// keeps the field access below type-checked without pretending the
	// payload was validated at runtime.
	const data: InitResponse = await response.json();

	return data;
};

export { init };
