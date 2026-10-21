import Link from "next/link";

const donateClassName =
  "inline-flex shrink-0 items-center justify-center rounded-full bg-accent px-10 py-3.5 font-sans text-label-xs font-bold leading-none tracking-label text-white no-underline hover:opacity-90";

type DonateLinkProps = {
  className?: string;
  onClick?: () => void;
};

/** Figma nav Donate (33:401): 12px bold, 3px tracking, pill from vertical padding — not fixed height. */
export function DonateLink({ className = "", onClick }: DonateLinkProps) {
  return (
    <Link
      href="https://urbanindigenouscollective.org/donate"
      className={`${donateClassName} ${className}`.trim()}
      onClick={onClick}
    >
      DONATE
    </Link>
  );
}
