"use client";

type StateSubscribeBellProps = {
  onClick: () => void;
  label: string;
};

/** Bell affordance for state update subscriptions — matches drawer left-edge border tone. */
export function StateSubscribeBell({ onClick, label }: StateSubscribeBellProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="inline-flex size-[1.75rem] shrink-0 cursor-pointer items-center justify-center rounded-full border border-white text-white outline-none transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25"
    >
      <BellIcon className="size-[0.875rem]" />
    </button>
  );
}

function BellIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      focusable="false"
    >
      <path
        d="M12 3.5c-2.9 0-5.25 2.2-5.25 4.9v2.1c0 .7-.28 1.37-.78 1.87L4.8 13.54c-.5.5-.78 1.17-.78 1.87 0 .72.58 1.3 1.3 1.3h13.36c.72 0 1.3-.58 1.3-1.3 0-.7-.28-1.37-.78-1.87l-1.17-1.17a2.65 2.65 0 0 1-.78-1.87V8.4C17.25 5.7 14.9 3.5 12 3.5Z"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
      <path
        d="M9.75 18.2a2.4 2.4 0 0 0 4.5 0"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </svg>
  );
}
