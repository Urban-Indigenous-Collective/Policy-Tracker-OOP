"use client";

import { BillPanelDrawer } from "@/components/bill/BillPanelDrawer";
import { StatePanel } from "@/components/state/StatePanel";
import type { PublicStateBillsResponse, PublicStatesResponse } from "@/lib/api/types";
import type { MapLayerSelection } from "@/lib/map/bill-layers";
import {
  drawerCategoryForState,
  type MapPaintFallback,
} from "@/lib/map/resolve-map-paint-categories";
import { useDrawerSlide } from "@/lib/state/drawer-motion";

type StatePanelDrawerProps = {
  stateCode: string | null;
  billSlug?: string | null;
  statesResponse?: PublicStatesResponse | null;
  mapLayerMode: MapLayerSelection;
  mapPaintFallback?: MapPaintFallback;
  onClose: () => void;
  onCloseBill?: () => void;
  initialBills?: PublicStateBillsResponse | null;
};

/** Keeps the panel mounted through the slide-out, then unmounts. */
export function StatePanelDrawer({
  stateCode,
  billSlug = null,
  statesResponse = null,
  mapLayerMode,
  mapPaintFallback,
  onClose,
  onCloseBill,
  initialBills = null,
}: StatePanelDrawerProps) {
  const { activeKey: activeCode, slideIn, onSlideTransitionEnd } =
    useDrawerSlide(stateCode);

  if (!activeCode) return null;

  const stateCategory = drawerCategoryForState(
    statesResponse ?? undefined,
    mapLayerMode,
    activeCode,
    mapPaintFallback,
  );

  return (
    <>
      <BillPanelDrawer
        stateCode={activeCode}
        billSlug={stateCode ? billSlug : null}
        onClose={onCloseBill ?? onClose}
      />
      <StatePanel
        stateCode={activeCode}
        stateCategory={stateCategory}
        mapLayerMode={mapLayerMode}
        onClose={onClose}
        onCloseBill={onCloseBill}
        billPanelOpen={Boolean(stateCode && billSlug)}
        initialBills={activeCode === stateCode ? initialBills : null}
        slideIn={slideIn}
        onSlideTransitionEnd={onSlideTransitionEnd}
      />
    </>
  );
}
