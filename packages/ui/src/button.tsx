import type { ButtonHTMLAttributes, ReactNode } from 'react'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly children: ReactNode
  readonly variant?: 'primary' | 'secondary' | 'ghost'
}

export function Button({ children, className = '', variant = 'primary', ...props }: ButtonProps) {
  return (
    <button className={`ld-button ld-button--${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  )
}
