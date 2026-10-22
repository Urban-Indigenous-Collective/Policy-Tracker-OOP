import Image from "next/image";

type FilterChipProps = {
  label: string;
  active?: boolean;
  onClick?: () => void;
};

export function FilterChip({ label, active = true, onClick }: FilterChipProps) {
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`flex min-w-0 max-w-full items-center gap-filter-switch-gap whitespace-nowrap 2xl:shrink-0 ${
        onClick
          ? "cursor-pointer rounded-md border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent"
          : ""
      }`}
    >
      <Image
        src="/ui/switch-active.svg"
        alt=""
        width={46}
        height={21}
        className={active ? "opacity-100" : "opacity-inactive"}
        aria-hidden
      />
      <span className="uic-label text-foreground">{label}</span>
    </Wrapper>
  );
}
