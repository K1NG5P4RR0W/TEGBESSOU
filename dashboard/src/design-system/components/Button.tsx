import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = "primary", children, ...rest }: ButtonProps): JSX.Element {
  return (
    <button className={`${styles.btn} ${styles[variant]}`} {...rest}>
      {children}
    </button>
  );
}
