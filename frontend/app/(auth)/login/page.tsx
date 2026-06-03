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
  email: z.string().min(1, 'Email or username is required').refine(
    (value) => value === 'admin' || z.string().email().safeParse(value).success,
    'Enter a valid email or use admin'
  ),
  password: z.string().min(1, 'Password is required'),
})
type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: FormData) => {
    try {
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

  return (
    <>
      <h2 className="text-xl font-bold text-charcoal mb-1 tracking-tight">Welcome back</h2>
      <p className="text-sm text-muted mb-6">Sign in to your creative workspace</p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Email or username"
          type="text"
          placeholder="admin"
          error={errors.email?.message}
          {...register('email')}
        />
        <Input
          label="Password"
          type="password"
          placeholder="••••••••"
          error={errors.password?.message}
          {...register('password')}
        />
        <Button type="submit" variant="primary" size="lg" isLoading={isSubmitting} className="w-full mt-2">
          Sign in
        </Button>
      </form>

      <p className="text-center text-xs text-lt mt-5">
        Don't have an account?{' '}
        <Link href="/register" className="text-accent font-semibold hover:underline">
          Create one
        </Link>
      </p>
    </>
  )
}
