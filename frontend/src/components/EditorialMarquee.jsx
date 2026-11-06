const ITEMS = [
  "RUU PILKADA 2024",
  "KERUGIAN NEGARA RP 300 T",
  "KEBEBASAN PERS #111",
  "TAPERA",
  "DINASTI POLITIK",
  "MEGAPROYEK IKN",
  "HARUN MASIKU BURON",
  "BTS 4G RP 8 T",
  "INDEKS PERSEPSI KORUPSI 34",
];

export default function EditorialMarquee({ className = "" }) {
  const row = ITEMS.map((t) => `  ●  ${t}`).join("  ");
  return (
    <div
      data-testid="editorial-marquee"
      className={`overflow-hidden whitespace-nowrap bg-red-700 py-1.5 text-[11px] font-mono font-semibold tracking-[0.18em] text-white ${className}`}
    >
      <div className="animate-marquee inline-block">
        <span>{row}</span>
        <span>{row}</span>
      </div>
    </div>
  );
}
