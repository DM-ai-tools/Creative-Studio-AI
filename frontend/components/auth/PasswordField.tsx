'use client'

import { forwardRef, useState } from 'react'
import Input from '@/components/ui/Input'
import { AUTH_INPUT, AUTH_LABEL } from '@/components/auth/authField'

type PasswordFieldProps = {
  label: string
  placeholder?: string
  error?: string
} & React.InputHTMLAttributes<HTMLInputElement>

const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(function PasswordField(
  { label, placeholder, error, ...props },
  ref
) {
  const [visible, setVisible] = useState(false)

  return (
    <Input
      ref={ref}
      label={label}
      type={visible ? 'text' : 'password'}
      placeholder={placeholder}
      error={error}
      labelClassName={AUTH_LABEL}
      className={`${AUTH_INPUT} !pr-10`}
      rightElement={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="p-1 text-muted hover:text-charcoal"
          aria-label={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.1A9.8 9.8 0 0112 5c5 0 9 4 10.5 7-0.4.8-1 1.7-1.7 2.5M6.1 6.1C4 7.7 2.5 9.8 1.5 12c1.5 3 5.5 7 10.5 7 1.6 0 3.1-.4 4.5-1.1" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>
      }
      {...props}
    />
  )
})

export default PasswordField
