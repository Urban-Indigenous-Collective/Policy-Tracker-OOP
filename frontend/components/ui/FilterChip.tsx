import Image from "next/image";

type FilterChipProps = {
  label: string;
  active?: boolean;
};

export function FilterChip({ label, active = true }: FilterChipProps) {
  return (
    <div className="flex min-w-0 max-w-full items-center gap-[18px] whitespace-nowrap 2xl:shrink-0">
      <Image
        src="/ui/switch-active.svg"
        alt=""
        width={46}
        height={21}
        className={active ? "opacity-100" : "opacity-40"}
        aria-hidden
      />
      <span className="text-xs font-bold tracking-[0.2em] text-white">
        {label}
      </span>
    </div>
  );
}
