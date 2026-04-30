interface HealthBadgeProps {
  value: string;
}

export function HealthBadge({ value }: HealthBadgeProps) {
  const label = value.replaceAll("_", " ");

  return (
    <span className={`health-badge health-badge--${value}`}>
      {label}
    </span>
  );
}