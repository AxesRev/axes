"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type AgentContextRecord = {
  content: string;
  updated_at: string | null;
};

type SaveState = "idle" | "loading" | "saving" | "saved" | "error";

const SAVE_DEBOUNCE_MS = 600;

export function AgentContextSection() {
  const [content, setContent] = useState("");
  const [initialContent, setInitialContent] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestContentRef = useRef("");

  const loadAgentContext = useCallback(async (): Promise<void> => {
    setSaveState("loading");
    setErrorMessage(null);

    try {
      const response = await fetch("/api/agent-context");
      const payload = (await response.json()) as AgentContextRecord & { detail?: string };

      if (!response.ok) {
        throw new Error(payload.detail ?? "Could not load agent context.");
      }

      setContent(payload.content);
      setInitialContent(payload.content);
      latestContentRef.current = payload.content;
      setSaveState("idle");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setErrorMessage(message);
      setSaveState("error");
    }
  }, []);

  const saveAgentContext = useCallback(async (nextContent: string): Promise<void> => {
    setSaveState("saving");
    setErrorMessage(null);

    try {
      const response = await fetch("/api/agent-context", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: nextContent }),
      });
      const payload = (await response.json()) as AgentContextRecord & { detail?: string };

      if (!response.ok) {
        throw new Error(payload.detail ?? "Could not save agent context.");
      }

      if (latestContentRef.current !== nextContent) {
        return;
      }

      setInitialContent(payload.content);
      setSaveState("saved");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setErrorMessage(message);
      setSaveState("error");
    }
  }, []);

  useEffect(() => {
    void loadAgentContext();
  }, [loadAgentContext]);

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current !== null) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>): void => {
    const nextContent = event.target.value;
    setContent(nextContent);
    latestContentRef.current = nextContent;

    if (debounceTimerRef.current !== null) {
      clearTimeout(debounceTimerRef.current);
    }

    if (nextContent === initialContent) {
      setSaveState("idle");
      setErrorMessage(null);
      return;
    }

    setSaveState("saving");
    debounceTimerRef.current = setTimeout(() => {
      void saveAgentContext(nextContent);
    }, SAVE_DEBOUNCE_MS);
  };

  const statusLabel = (() => {
    switch (saveState) {
      case "loading":
        return "Loading…";
      case "saving":
        return "Saving…";
      case "saved":
        return "Saved";
      case "error":
        return "Error";
      default:
        return content === initialContent ? "Up to date" : "Unsaved changes";
    }
  })();

  return (
    <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-zinc-950 dark:text-zinc-50">Agent context</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Notes and instructions for your AI agent. Changes save automatically.
          </p>
        </div>
        <span className="shrink-0 text-xs text-zinc-500 dark:text-zinc-400">{statusLabel}</span>
      </div>

      {errorMessage ? <p className="mt-3 text-sm text-red-600">{errorMessage}</p> : null}

      <textarea
        className="mt-4 min-h-48 w-full resize-y rounded-lg border border-zinc-200 bg-white px-3 py-2 font-mono text-sm text-zinc-950 outline-none ring-zinc-400 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
        disabled={saveState === "loading"}
        onChange={handleChange}
        placeholder="Add context for your agent…"
        value={content}
      />
    </section>
  );
}
