import { Fragment, type ReactNode } from "react";

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Split plain text into alternating non-match / match segments (case-insensitive). */
export function splitTextBySearchQuery(
  text: string,
  query: string,
): { text: string; match: boolean }[] {
  const trimmed = query.trim();
  if (!trimmed) return [{ text, match: false }];

  const pattern = new RegExp(escapeRegExp(trimmed), "gi");
  const parts: { text: string; match: boolean }[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ text: text.slice(lastIndex, match.index), match: false });
    }
    parts.push({ text: match[0], match: true });
    lastIndex = match.index + match[0].length;
    if (match[0].length === 0) {
      pattern.lastIndex += 1;
    }
  }

  if (lastIndex < text.length) {
    parts.push({ text: text.slice(lastIndex), match: false });
  }

  return parts.length > 0 ? parts : [{ text, match: false }];
}

export function countSearchMatchesInText(text: string, query: string): number {
  return splitTextBySearchQuery(text, query).filter((part) => part.match).length;
}

/**
 * Split on paired `**` markers (markdown-style bold). Odd unclosed pair bolds through end of string.
 * Delimiters are removed; content is plain text for React nodes (no HTML injection).
 */
export function splitTextByInlineBold(
  text: string,
): { text: string; bold: boolean }[] {
  const parts: { text: string; bold: boolean }[] = [];
  let index = 0;
  let bold = false;

  while (index < text.length) {
    const marker = text.indexOf("**", index);
    if (marker === -1) {
      const rest = text.slice(index);
      if (rest) parts.push({ text: rest, bold });
      break;
    }
    if (marker > index) {
      parts.push({ text: text.slice(index, marker), bold });
    }
    bold = !bold;
    index = marker + 2;
  }

  return parts.length > 0 ? parts : [{ text, bold: false }];
}

function renderSearchHighlights(
  text: string,
  query: string,
  keyPrefix: string | number,
): ReactNode {
  const parts = splitTextBySearchQuery(text, query);
  return parts.map((part, index) =>
    part.match ? (
      <mark
        key={`${keyPrefix}-m${index}`}
        className="uic-bill-search-mark"
        data-bill-search-match
      >
        {part.text}
      </mark>
    ) : (
      <Fragment key={`${keyPrefix}-m${index}`}>{part.text}</Fragment>
    ),
  );
}

type HighlightSearchTextProps = {
  text: string;
  query: string;
};

/** Inline `**bold**` plus optional query matches in `<mark>` for in-panel search. */
export function HighlightSearchText({ text, query }: HighlightSearchTextProps): ReactNode {
  const trimmedQuery = query.trim();
  const boldParts = splitTextByInlineBold(text);

  if (boldParts.length === 1 && !boldParts[0].bold && !trimmedQuery) {
    return text;
  }

  return boldParts.map((part, index) => {
    const content = trimmedQuery
      ? renderSearchHighlights(part.text, trimmedQuery, index)
      : part.text;

    if (part.bold) {
      return (
        <strong key={index} className="font-semibold">
          {content}
        </strong>
      );
    }
    return <Fragment key={index}>{content}</Fragment>;
  });
}
