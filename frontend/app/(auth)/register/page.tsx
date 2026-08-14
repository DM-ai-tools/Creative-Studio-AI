'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import PasswordField from '@/components/auth/PasswordField'
import { AUTH_INPUT, AUTH_LABEL } from '@/components/auth/authField'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

const schema = z
  .object({
    full_name: z.string().min(2, 'Full name required'),
    email: z.string().email('Invalid email address'),
    tenant_name: z.string().min(2, 'Company name required'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: "Passwords don't match",
    path: ['confirm_password'],
  })
type FormData = z.infer<typeof schema>

export default function RegisterPage() {
  const router = useRouter()
  const { register: registerUser } = useAuth()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: FormData) => {
    try {
      await registerUser({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
        tenant_name: data.tenant_name,
      })
      toast.success("Account created! Let's set up your brand.")
      router.push('/onboarding')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Registration failed'
      toast.error(String(msg))
    }
  }

  return (
    <>
      <h1 className="mb-8 text-center text-[34px] font-bold tracking-tight text-ink">Sign up</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Full Name"
          placeholder="Jane Smith"
          error={errors.full_name?.message}
          labelClassName={AUTH_LABEL}
          className={AUTH_INPUT}
          autoComplete="name"
          {...register('full_name')}
        />
        <Input
          label="Email Address"
          type="email"
          placeholder="your@email.com"
          error={errors.email?.message}
          labelClassName={AUTH_LABEL}
          className={AUTH_INPUT}
          autoComplete="email"
          {...register('email')}
        />
        <Input
          label="Company Name"
          placeholder="Northwood Coffee Co."
          error={errors.tenant_name?.message}
          labelClassName={AUTH_LABEL}
          className={AUTH_INPUT}
          autoComplete="organization"
          {...register('tenant_name')}
        />
        <PasswordField
          label="Password"
          placeholder="8+ characters"
          error={errors.password?.message}
          autoComplete="new-password"
          {...register('password')}
        />
        <PasswordField
          label="Confirm Password"
          placeholder="Repeat password"
          error={errors.confirm_password?.message}
          autoComplete="new-password"
          {...register('confirm_password')}
        />

        <Button
          type="submit"
          variant="secondary"
          size="lg"
          isLoading={isSubmitting}
          className="mt-2 h-12 w-full rounded-xl text-[15px]"
        >
          Sign up
        </Button>
      </form>

      <p className="mt-5 text-center text-[11px] leading-relaxed text-muted">
        By proceeding, you acknowledge and accept our{' '}
        <span className="underline decoration-muted/70 underline-offset-2">Terms and Conditions</span> and{' '}
        <span className="underline decoration-muted/70 underline-offset-2">Privacy Policy</span>.
      </p>

      <p className="mt-8 text-center text-[13px] text-muted">
        Already have an account?{' '}
        <Link href="/login" className="font-semibold text-accent-dark hover:underline">
          Sign in
        </Link>
      </p>
    </>
  )
}
