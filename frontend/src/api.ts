export const API = import.meta.env.VITE_API_BASE ?? "http://localhost:8001/api";
export const CENTER: [number, number] = [40.195, -75.425];

export async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const parsed = JSON.parse(text);
      message = String(parsed.detail || message);
    } catch {
      // Keep the raw response text when it is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
