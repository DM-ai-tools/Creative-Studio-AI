import Image from 'next/image'
import Link from 'next/link'
import { BrandMark } from '@/components/brand/BrandMark'

export default function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white lg:grid lg:grid-cols-2">
      <section className="relative flex min-h-screen flex-col overflow-y-auto px-6 py-6 sm:px-12 lg:px-16 xl:px-20">
        <div className="flex items-center justify-between gap-4">
          <Link href="/" className="flex w-fit items-center gap-2.5">
            <BrandMark size={32} />
            <span className="text-[17px] font-bold tracking-tight text-ink">
              creativestudio
              <sup className="relative -top-2 ml-0.5 text-[9px] font-semibold text-accent">ai</sup>
            </span>
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-[13px] font-medium text-muted hover:text-ink lg:hidden"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
            Home
          </Link>
        </div>

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-[400px] py-12">{children}</div>
        </div>
      </section>

      <aside className="relative hidden min-h-screen lg:block">
        <Image
          src="/auth/studio-team-4k.jpg"
          alt="Creative team collaborating in studio"
          fill
          priority
          quality={95}
          className="object-cover object-center"
          sizes="50vw"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/25 via-transparent to-black/20" />
        <Link
          href="/"
          className="absolute right-7 top-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-white drop-shadow-md transition-opacity hover:opacity-80"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
          Back to Home
        </Link>
      </aside>
    </div>
  )
}
