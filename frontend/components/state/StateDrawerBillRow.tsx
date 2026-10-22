import Link from "next/link";

import { StateDrawerBillId } from "@/components/state/StateDrawerBillId";
import { StateDrawerStatusPill } from "@/components/state/StateDrawerStatusPill";
import type { PublicBill } from "@/lib/api/types";
import { stateCodeForUrl } from "@/lib/api/state-code";

type StateDrawerBillRowProps = {
  stateCode: string;
  bill: PublicBill;
};

export function StateDrawerBillRow({ stateCode, bill }: StateDrawerBillRowProps) {
  const href = `/states/${stateCodeForUrl(stateCode)}/bills/${bill.slug}`;
  const billId = bill.billNumber?.trim() || "—";
  const title = bill.name?.trim() || bill.summary?.trim() || "Untitled bill";

  return (
    <li className="w-drawer-bill-row max-w-full">
      <Link
        href={href}
        className="group flex gap-3 outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <div className="flex w-drawer-bill-col-id shrink-0 flex-col gap-2">
          <StateDrawerBillId>{billId}</StateDrawerBillId>
          <StateDrawerStatusPill bill={bill} />
        </div>
        <p className="uic-drawer-bill-body-regular w-drawer-bill-col-title min-w-0 font-sans font-normal leading-drawer-bill-body opacity-100 transition-opacity duration-150 group-hover:opacity-70 group-focus-visible:opacity-70 motion-reduce:transition-none">
          {title}
        </p>
      </Link>
    </li>
  );
}
