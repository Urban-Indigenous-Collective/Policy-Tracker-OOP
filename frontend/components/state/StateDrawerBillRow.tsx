import Link from "next/link";

import { StateDrawerBillIdStack } from "@/components/state/StateDrawerBillIdStack";
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
    <li className="w-drawer-bill-row min-w-0 max-w-full">
      <Link
        href={href}
        className="group grid w-drawer-bill-row min-w-0 max-w-full grid-cols-[minmax(0,var(--width-drawer-bill-col-id))_minmax(0,var(--width-drawer-bill-col-title))] gap-x-drawer-bill-col-gap outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <div className="col-start-1 flex min-w-0 max-w-full items-start overflow-visible">
          <StateDrawerBillIdStack billId={billId} bill={bill} />
        </div>
        <p className="uic-drawer-bill-body-regular col-start-2 w-[var(--width-drawer-bill-col-title)] min-w-0 font-sans font-normal leading-drawer-bill-body opacity-100 transition-opacity duration-150 group-hover:opacity-70 group-focus-visible:opacity-70 motion-reduce:transition-none">
          {title}
        </p>
      </Link>
    </li>
  );
}
