'use client'

import Link from 'next/link'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { AUTH_INPUT, AUTH_LABEL } from '@/components/auth/authField'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) {
      toast.error('Enter your email address')
      return
    }
    setSent(true)
    toast.success('If an account exists, your workspace admin can reset the password.')
  }

  return (
    <>
      <h1 className="mb-3 text-center text-[34px] font-bold tracking-tight text-ink">Forgot Password?</h1>
      <p className="mb-8 text-center text-[14px] text-muted">
        Enter the email on your account. We&apos;ll point you to a reset.
      </p>

      <form onSubmit={onSubmit} className="space-y-5">
        <Input
          label="Email Address"
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          labelClassName={AUTH_LABEL}
          className={AUTH_INPUT}
          autoComplete="email"
        />
        <Button type="submit" variant="secondary" size="lg" className="h-12 w-full rounded-xl text-[15px]">
          {sent ? 'Email noted' : 'Send reset link'}
        </Button>
      </form>

      <p className="mt-10 text-center text-[13px] text-muted">
        Remembered it?{' '}
        <Link href="/login" className="font-semibold text-accent-dark hover:underline">
          Sign in
        </Link>
      </p>
    </>
  )
}
