"use client";

import { createContext, useContext } from "react";

type MapBillNavValue = {
  /** When set (embed map), bill rows open the analysis panel in-place. */
  selectBill: ((slug: string) => void) | null;
};

const MapBillNavContext = createContext<MapBillNavValue>({ selectBill: null });

export function MapBillNavProvider({
  selectBill,
  children,
}: {
  selectBill: ((slug: string) => void) | null;
  children: React.ReactNode;
}) {
  return (
    <MapBillNavContext.Provider value={{ selectBill }}>
      {children}
    </MapBillNavContext.Provider>
  );
}

export function useMapBillNav(): MapBillNavValue {
  return useContext(MapBillNavContext);
}
