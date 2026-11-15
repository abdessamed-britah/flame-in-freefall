// One call to Gemini over REST, with the settings of src/ai.py call_gemini(): temperature 0,
// low thinking, system instruction. Server-side only; the key never reaches the browser.
import { AIUnavailable, type LLM } from "./checks.ts";

const API = "https://generativelanguage.googleapis.com/v1beta/models";

export function gemini(model: string, key: string, timeoutMs = 20_000): LLM {
  return async (system, user) => {
    let r: Response;
    try {
      r = await fetch(`${API}/${model}:generateContent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: system }] },
          contents: [{ role: "user", parts: [{ text: user }] }],
          generationConfig: { temperature: 0, maxOutputTokens: 8000, thinkingConfig: { thinkingLevel: "LOW" } },
        }),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (e) {
      const timeout = e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");
      throw new AIUnavailable(timeout ? `no answer within ${timeoutMs / 1000} s` : "could not reach the AI service");
    }
    if (r.status === 429) throw new AIUnavailable("the AI service is rate-limiting requests (429)");
    if (r.status === 400 || r.status === 401 || r.status === 403) throw new AIUnavailable(`the API key or request was rejected (${r.status})`);
    if (!r.ok) throw new AIUnavailable(`the AI service returned an error (${r.status})`);
    const body = (await r.json()) as { candidates?: { content?: { parts?: { text?: string; thought?: boolean }[] } }[] };
    const text = (body.candidates?.[0]?.content?.parts ?? []).filter((p) => !p.thought).map((p) => p.text ?? "").join("").trim();
    if (!text) throw new AIUnavailable("the AI service returned no text");
    return text;
  };
}
