import { ApiHealthSmoke } from "@/components/ApiHealthSmoke";

export function DevHealthBanner() {
  if (process.env.NODE_ENV !== "development") {
    return null;
  }

  return (
    <div className="border-t border-surface-border px-4 py-3">
      <div className="mx-auto max-w-artboard">
        <ApiHealthSmoke />
      </div>
    </div>
  );
}
