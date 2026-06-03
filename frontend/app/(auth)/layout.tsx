import React from 'react'
import { AuthProvider } from '@/hooks/useAuth'
import { IconSparkles } from '@/components/ui/icons'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <div className="min-h-screen relative overflow-hidden flex items-center justify-center p-6">
        {/* Ambient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-ink via-[#25262e] to-ink" />
        <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-accent/20 blur-[120px]" />
        <div className="absolute bottom-[-15%] right-[-10%] w-[45%] h-[45%] rounded-full bg-success/15 blur-[100px]" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px)',
            backgroundSize: '48px 48px',
          }}
        />

        <div className="relative w-full max-w-[420px] animate-slide-up">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-gradient shadow-glow mb-4">
              <IconSparkles className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Creative<span className="text-accent">Studio</span> AI
            </h1>
            <p className="text-subtle text-sm mt-2 font-medium">Premium AI creative engine for Meta Ads</p>
          </div>
          <div className="glass-panel rounded-3xl p-8 md:p-10 border border-white/20 shadow-card">
            {children}
          </div>
        </div>
      </div>
    </AuthProvider>
  )
}
