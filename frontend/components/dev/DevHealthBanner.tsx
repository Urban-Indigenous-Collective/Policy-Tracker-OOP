import { ApiHealthSmoke } from "@/components/ApiHealthSmoke";

export function DevHealthBanner() {
  if (process.env.NODE_ENV !== "development") {
    return null;
  }

  if (process.env.NEXT_PUBLIC_SHOW_DEV_HEALTH_BANNER !== "true") {
    return null;
  }

  return (
    <div className="border-t border-surface-border bg-background px-4 py-2">
      <div className="mx-auto max-w-artboard">
        <ApiHealthSmoke placement="banner" />
      </div>
    </div>
  );
}
