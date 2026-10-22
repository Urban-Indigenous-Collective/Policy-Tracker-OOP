import { StateDrawerBillRow } from "@/components/state/StateDrawerBillRow";
import type { PublicBill } from "@/lib/api/types";

type StateBillListProps = {
  stateCode: string;
  bills: PublicBill[];
  emptyMessage?: string;
};

export function StateBillList({
  stateCode,
  bills,
  emptyMessage,
}: StateBillListProps) {
  if (bills.length === 0) {
    return (
      <p className="uic-drawer-bill-body-regular text-muted">
        {emptyMessage ?? "No live policies are published for this state yet."}
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-drawer-row pb-2">
      {bills.map((bill) => (
        <StateDrawerBillRow key={bill.id} stateCode={stateCode} bill={bill} />
      ))}
    </ul>
  );
}
