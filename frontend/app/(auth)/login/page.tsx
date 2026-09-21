'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import PasswordField from '@/components/auth/PasswordField'
import { AUTH_INPUT, AUTH_LABEL } from '@/components/auth/authField'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

const schema = z.object({
  email: z
    .string()
    .min(1, 'Email or username is required')
    .refine(
      (value) =>
        /^[a-zA-Z0-9._-]+$/.test(value) ||
        z.string().email().safeParse(value).success,
      'Enter a valid email or username',
    ),
  password: z.string().min(1, 'Password is required'),
})
type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const router = useRouter()
  const { login, user, isLoading } = useAuth()
  const [remember, setRemember] = useState(true)

  useEffect(() => {
    if (!isLoading && user) router.replace('/dashboard')
  }, [user, isLoading, router])
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: FormData) => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('cs_remember', remember ? '1' : '0')
      }
      await login(data.email, data.password)
      router.push('/dashboard')
    } catch (err: unknown) {
      const axiosErr = err as {
        code?: string
        response?: { data?: { detail?: string } }
        message?: string
      }
      if (axiosErr.code === 'ECONNABORTED') {
        toast.error('Cannot reach API — is the backend running on http://localhost:8000?')
        return
      }
      if (!axiosErr.response) {
        toast.error('Cannot reach API — start the backend (npm run start:backend)')
        return
      }
      const msg = axiosErr.response?.data?.detail || 'Login failed'
      toast.error(String(msg))
    }
  }

  if (isLoading || user) {
    return null
  }

  return (
    <>
      <h1 className="mb-8 text-center text-[34px] font-bold tracking-tight text-ink">Sign in</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        <Input
          label="Email Address"
          type="text"
          placeholder="your@email.com"
          error={errors.email?.message}
          labelClassName={AUTH_LABEL}
          className={AUTH_INPUT}
          autoComplete="email"
          {...register('email')}
        />
        <PasswordField
          label="Password"
          placeholder="Your password"
          error={errors.password?.message}
          autoComplete="current-password"
          {...register('password')}
        />

        <div className="flex items-center justify-between pt-0.5">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-charcoal">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="h-4 w-4 rounded border-[#c8cacd] text-ink accent-ink"
            />
            Remember me
          </label>
          <Link href="/forgot-password" className="text-[13px] font-medium text-accent-dark hover:underline">
            Forgot Password?
          </Link>
        </div>

        <Button
          type="submit"
          variant="secondary"
          size="lg"
          isLoading={isSubmitting}
          className="mt-1 h-12 w-full rounded-xl text-[15px]"
        >
          Sign in
        </Button>
      </form>

      <p className="mt-5 text-center text-[11px] leading-relaxed text-muted">
        By proceeding, you acknowledge and accept our{' '}
        <span className="underline decoration-muted/70 underline-offset-2">Terms and Conditions</span> and{' '}
        <span className="underline decoration-muted/70 underline-offset-2">Privacy Policy</span>.
      </p>

    </>
  )
}
