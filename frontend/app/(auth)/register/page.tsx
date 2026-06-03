'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

const schema = z.object({
  full_name: z.string().min(2, 'Full name required'),
  email: z.string().email('Invalid email address'),
  tenant_name: z.string().min(2, 'Company name required'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirm_password: z.string(),
}).refine((d) => d.password === d.confirm_password, {
  message: "Passwords don't match",
  path: ['confirm_password'],
})
type FormData = z.infer<typeof schema>

export default function RegisterPage() {
  const router = useRouter()
  const { register: registerUser } = useAuth()
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
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
      toast.success('Account created! Let\'s set up your brand.')
      router.push('/onboarding')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Registration failed'
      toast.error(msg)
    }
  }

  return (
    <>
      <h2 className="text-xl font-bold text-navy mb-1">Create your workspace</h2>
      <p className="text-xs text-lt mb-5">Start generating AI-powered Meta Ads</p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
        <Input label="Full name" placeholder="Jane Smith" error={errors.full_name?.message} {...register('full_name')} />
        <Input label="Work email" type="email" placeholder="jane@company.com" error={errors.email?.message} {...register('email')} />
        <Input label="Company name" placeholder="Northwood Coffee Co." error={errors.tenant_name?.message} {...register('tenant_name')} />
        <Input label="Password" type="password" placeholder="8+ characters" error={errors.password?.message} {...register('password')} />
        <Input label="Confirm password" type="password" placeholder="Repeat password" error={errors.confirm_password?.message} {...register('confirm_password')} />
        <Button type="submit" variant="primary" size="lg" isLoading={isSubmitting} className="w-full mt-2">
          Create account
        </Button>
      </form>

      <p className="text-center text-xs text-lt mt-4">
        Already have an account?{' '}
        <Link href="/login" className="text-mint font-semibold hover:underline">Sign in</Link>
      </p>
    </>
  )
}
