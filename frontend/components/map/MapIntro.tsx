import type { CSSProperties } from "react";
import {
  HERO_COLUMN_GAP_PX,
  INTRO_MAX_PX,
  TITLE_MAX_PX,
} from "@/lib/layout/figma-layout";

const INTRO_PARAGRAPHS = [
  `Our interactive map gives a general overview of state legislation addressing Missing and Murdered Indigenous Women, Girls, Trans, and Two-Spirit relatives (MMIWGT2S). Each state is grouped by the status of MMIWGT2S-related bills introduced since 2020: passed, failed, or still pending. A state's color reflects legislative activity, not the safety of Indigenous communities or the strength of a law's implementation. A bill that passes may still lack funding, enforcement, or tribal consultation, and a state with no legislation may still have strong community-led efforts underway.`,
  `The map is a starting point. For bill text, summaries, and UIC's analysis of each policy's strengths and gaps, see the Policy Table below. If a term is unfamiliar, our Glossary of Key Terms explains the language of this work through an Indigenous lens.`,
];

export function MapIntro() {
  return (
    <section className="mt-6 lg:mt-10">
      <div
        className="grid gap-9 sm:gap-10 lg:grid-cols-[var(--title-col)_minmax(0,1fr)] lg:items-start lg:gap-[var(--hero-col-gap)]"
        style={
          {
            ["--title-col" as string]: `min(${TITLE_MAX_PX}px, 100%)`,
            ["--hero-col-gap" as string]: `${HERO_COLUMN_GAP_PX}px`,
          } as CSSProperties
        }
      >
        <h1 className="max-w-[394px] font-mono text-[clamp(1.75rem,4.2vw+1rem,2.25rem)] font-bold leading-[1.15] text-accent lg:pl-[47px] lg:text-[36px]">
          <span className="whitespace-nowrap">Missing &amp; Murdered</span>
          <br />
          <span className="whitespace-nowrap">Indigenous Persons</span>
          <br />
          Policies
        </h1>

        <div
          className="space-y-6 text-[13px] font-semibold leading-6 text-white"
          style={{ maxWidth: INTRO_MAX_PX }}
        >
          {INTRO_PARAGRAPHS.map((paragraph) => (
            <p key={paragraph.slice(0, 32)}>{paragraph}</p>
          ))}
          <p className="font-semibold text-white/90">
            Policies current as of September 18, 2026
          </p>
        </div>
      </div>
    </section>
  );
}
