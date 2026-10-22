import Link from "next/link";

import { StateDrawerStatusPill } from "@/components/state/StateDrawerStatusPill";
import type { PublicBill } from "@/lib/api/types";

type StateDrawerBillRowProps = {
  stateCode: string;
  bill: PublicBill;
};

export function StateDrawerBillRow({ stateCode, bill }: StateDrawerBillRowProps) {
  const href = `/states/${stateCode}/bills/${bill.slug}`;
  const billId = bill.billNumber?.trim() || "—";
  const title = bill.name?.trim() || bill.summary?.trim() || "Untitled bill";

  return (
    <li className="w-drawer-bill-row max-w-full">
      <Link
        href={href}
        className="group flex gap-3 outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <div className="flex w-drawer-bill-col-id shrink-0 flex-col gap-2">
          <span className="uic-drawer-bill-id group-hover:text-accent">{billId}</span>
          <StateDrawerStatusPill bill={bill} />
        </div>
        <p className="uic-drawer-bill-body-regular font-sans font-normal leading-drawer-bill-body w-drawer-bill-col-title min-w-0 group-hover:text-accent">
          {title}
        </p>
      </Link>
    </li>
  );
}
