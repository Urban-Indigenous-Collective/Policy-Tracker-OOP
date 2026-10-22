import Link from "next/link";

import { StateDrawerBillIdStack } from "@/components/state/StateDrawerBillIdStack";
import type { PublicBill } from "@/lib/api/types";
import { stateCodeForUrl } from "@/lib/api/state-code";
import { billStatusVariant } from "@/lib/bill/status-variant";
import { formatDrawerSessionYear } from "@/lib/state/format-drawer-session-year";

/** Same status scale as the drawer pill. Missing or unrecognized status stays muted. */
const sessionStatusClass: Record<ReturnType<typeof billStatusVariant>, string> = {
  passed: "text-status-passed",
  failed: "text-status-failed",
  pending: "text-status-pending",
  neutral: "text-muted",
};

type PolicyListBillRowProps = {
  stateCode: string;
  bill: PublicBill;
};

export function PolicyListBillRow({ stateCode, bill }: PolicyListBillRowProps) {
  const href = `/states/${stateCodeForUrl(stateCode)}/bills/${bill.slug}`;
  const billId = bill.billNumber?.trim() || "—";
  const title = bill.name?.trim() || bill.summary?.trim() || "Untitled bill";
  const session = formatDrawerSessionYear(bill.session);

  return (
    <li className="min-w-0 w-full max-w-full">
      <Link
        href={href}
        className="group grid w-full min-w-0 max-w-full grid-cols-[minmax(0,var(--width-drawer-bill-col-id))_minmax(0,1fr)] gap-x-drawer-bill-col-gap outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <div className="col-start-1 flex min-w-0 max-w-full items-start overflow-visible">
          <StateDrawerBillIdStack billId={billId} bill={bill} />
        </div>
        <div className="col-start-2 min-w-0">
          {session ? (
            <p className={`uic-drawer-bill-session ${sessionStatusClass[billStatusVariant(bill)]}`}>
              {session}
            </p>
          ) : null}
          <p className="uic-drawer-bill-body-regular font-sans font-normal leading-drawer-bill-desc opacity-100 transition-opacity duration-150 group-hover:opacity-70 group-focus-visible:opacity-70 motion-reduce:transition-none">
            {title}
          </p>
        </div>
      </Link>
    </li>
  );
}
