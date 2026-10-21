import { ApiHealthSmoke } from "@/components/ApiHealthSmoke";

export function DevHealthBanner() {
  if (process.env.NODE_ENV !== "development") {
    return null;
  }

  return (
    <div className="border-t border-white/10 px-4 py-3">
      <div className="mx-auto max-w-[1512px]">
        <ApiHealthSmoke />
      </div>
    </div>
  );
}
