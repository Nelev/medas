import { ChatMessageProps } from "@/model/ChatMessage";

// Server-side only: this module is imported from a Server Component, so the
// backend origin never reaches the browser bundle and needs no NEXT_PUBLIC_.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

interface InitResponse {
	messages: ChatMessageProps[];
}

const init = async (user: string): Promise<InitResponse> => {
	const url = `${API_BASE_URL}/?user=${encodeURIComponent("Mattia")}`;

	const response = await fetch(url);

	if (!response.ok) {
		throw new Error(`Failed to init profile (${response.status})`);
	}

	const data: InitResponse = await response.json();

	return data;
};

export { init };
