"use client";

import { createContext, useContext } from "react";

export type EmbedChromeValue = {
  /** True when rendered under `/embed/*` (no site nav/footer). */
  embed: boolean;
  /** How deep links should open from drawers/rows inside an iframe. */
  linkTarget: "_self" | "_blank" | "_top";
};

const defaultValue: EmbedChromeValue = {
  embed: false,
  linkTarget: "_self",
};

const EmbedChromeContext = createContext<EmbedChromeValue>(defaultValue);

export function EmbedChromeProvider({
  value,
  children,
}: {
  value: EmbedChromeValue;
  children: React.ReactNode;
}) {
  return (
    <EmbedChromeContext.Provider value={value}>
      {children}
    </EmbedChromeContext.Provider>
  );
}

export function useEmbedChrome(): EmbedChromeValue {
  return useContext(EmbedChromeContext);
}
