interface PremiumButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "accent" | "signal" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export function PremiumButton({
  variant = "accent",
  size = "md",
  className = "",
  ...props
}: PremiumButtonProps) {
  const base =
    "inline-flex items-center justify-center rounded-xl font-semibold tracking-tight transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:pointer-events-none";

  const variants: Record<string, string> = {
    accent: "bg-accent text-accent-foreground hover:bg-accent-hover shadow-sm shadow-accent/20",
    signal: "bg-signal text-white hover:bg-signal/90 shadow-sm shadow-signal/20",
    ghost: "bg-surface-raised text-foreground border border-border hover:bg-surface hover:border-border-strong",
    danger: "bg-danger/10 text-danger hover:bg-danger/20 border border-danger/30 hover:border-danger",
  };

  const sizes: Record<string, string> = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-xs",
    lg: "px-6 py-2.5 text-sm",
  };

  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />
  );
}
