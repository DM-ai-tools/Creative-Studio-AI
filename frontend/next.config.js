/** @type {import('next').NextConfig} */
const apiOrigin = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(
  /\/api\/v1\/?$/,
  ''
)

const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/files/:path*',
        destination: `${apiOrigin}/files/:path*`,
      },
    ]
  },
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost' },
      { protocol: 'https', hostname: '**' },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
  },
}

module.exports = nextConfig
