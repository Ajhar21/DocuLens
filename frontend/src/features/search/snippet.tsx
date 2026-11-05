import type { ReactNode } from "react";

/**
 * Pure, safe renderer for backend search snippets.
 *
 * Backend ts_headline produces text with `<mark>...</mark>` tags around matched tokens.
 * All surrounding text is untrusted document OCR/text.
 *
 * Security: NEVER uses dangerouslySetInnerHTML.
 * Splits on `<mark>` and `</mark>` tags and produces typed React nodes:
 * - Highlighted content is wrapped in `<mark className="...">...</mark>`.
 * - All other content (including any malicious HTML, script tags, event handlers)
 *   is rendered as raw string children, which React escapes automatically.
 */
export function renderSnippet(snippet: string | null | undefined): ReactNode {
  if (!snippet) return null;

  // Split on <mark> and </mark> tags case-insensitively
  const parts = snippet.split(/(<\/?mark>)/i);
  let isMarked = false;
  const nodes: ReactNode[] = [];

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (!part) continue;

    const lower = part.toLowerCase();
    if (lower === "<mark>") {
      isMarked = true;
      continue;
    }
    if (lower === "</mark>") {
      isMarked = false;
      continue;
    }

    if (isMarked) {
      nodes.push(
        <mark
          key={i}
          className="rounded bg-amber-200 px-0.5 font-semibold text-foreground dark:bg-amber-900/60 dark:text-amber-100"
        >
          {part}
        </mark>,
      );
    } else {
      nodes.push(part);
    }
  }

  return nodes;
}

