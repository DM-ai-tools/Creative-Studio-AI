import React from 'react'
import AuthShell from '@/components/auth/AuthShell'
import { AuthProvider } from '@/hooks/useAuth'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthShell>{children}</AuthShell>
    </AuthProvider>
  )
}
