import { cn } from "@/lib/utils";

/**
 * Nodrat brand mark — inline SVG component (#78).
 *
 * Brand renkleri (tailwind.config.ts):
 *   brand-700  #243B53  (mat lacivert)
 *   accent-500 #FFA000  (sıcak amber)
 *
 * Variants:
 *   - "wordmark": N mark + "nodrat" wordmark (yatay)
 *   - "mark":     sadece N mark (kare)
 *
 * Sizes (height baz):
 *   - sm: 20px
 *   - md: 28px (default)
 *   - lg: 40px
 *
 * Tone (renk modu):
 *   - "default" (light bg): mat lacivert mark + lacivert wordmark
 *   - "inverse" (dark bg):  şeffaf çerçeveli mark + beyaz wordmark
 *
 * a11y: role="img" + aria-label = "Nodrat"
 */
type LogoVariant = "wordmark" | "mark";
type LogoSize = "sm" | "md" | "lg";
type LogoTone = "default" | "inverse";

interface LogoProps {
  variant?: LogoVariant;
  size?: LogoSize;
  tone?: LogoTone;
  className?: string;
}

const SIZE_HEIGHT: Record<LogoSize, number> = {
  sm: 20,
  md: 28,
  lg: 40,
};

export function Logo({
  variant = "wordmark",
  size = "md",
  tone = "default",
  className,
}: LogoProps) {
  const height = SIZE_HEIGHT[size];
  const isInverse = tone === "inverse";

  // Renk paleti
  const markBg = isInverse ? "#FFFFFF" : "#243B53";
  const markStroke = isInverse ? "#243B53" : "#FFFFFF";
  const accentDot = "#FFA000";
  const wordmarkFill = isInverse ? "#FFFFFF" : "#243B53";

  if (variant === "mark") {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 64 64"
        height={height}
        width={height}
        role="img"
        aria-label="Nodrat"
        className={cn("flex-shrink-0", className)}
      >
        <rect width="64" height="64" rx="12" fill={markBg} />
        <path
          d="M16 48 V16 L40 42 V16"
          fill="none"
          stroke={markStroke}
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="50" cy="16" r="3.5" fill={accentDot} />
      </svg>
    );
  }

  // wordmark: 200x60 viewBox
  const width = (height / 60) * 200;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 60"
      height={height}
      width={width}
      role="img"
      aria-label="Nodrat"
      className={cn("flex-shrink-0", className)}
    >
      <rect x="2" y="10" width="40" height="40" rx="8" fill={markBg} />
      <path
        d="M11 42 V18 L24 35 V18"
        fill="none"
        stroke={markStroke}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="33" cy="18" r="2.6" fill={accentDot} />
      <text
        x="52"
        y="40"
        fontFamily="Inter, ui-sans-serif, system-ui, sans-serif"
        fontSize="28"
        fontWeight="600"
        letterSpacing="-0.5"
        fill={wordmarkFill}
      >
        nodrat
      </text>
    </svg>
  );
}
