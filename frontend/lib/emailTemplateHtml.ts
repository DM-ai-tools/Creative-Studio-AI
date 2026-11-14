import type { EmailTemplate } from '@/types'

const esc = (value: unknown) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#039;')

const safeUrl = (value: unknown, fallback = '#') => {
  const text = String(value ?? '').trim()
  if (!text) return fallback
  if (/^(https?:|mailto:|tel:|#)/i.test(text)) return esc(text)
  return fallback
}

const safeColor = (value: unknown, fallback: string) => {
  const text = String(value ?? '').trim()
  return /^#[0-9a-f]{3,8}$/i.test(text) ? text : fallback
}

export function buildEmailHtml(template: EmailTemplate, resolved?: { hero?: string | null; logo?: string | null }) {
  const c = template.content
  const hero = resolved?.hero ?? c.hero_url
  const logo = resolved?.logo ?? c.logo_url
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${esc(template.subject || template.campaign_name)}</title>
</head>
<body style="margin:0;padding:0;background:${safeColor(c.background_color, '#F5F5F2')};font-family:Arial,Helvetica,sans-serif;color:${safeColor(c.text_color, '#202124')};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">${esc(template.preheader)}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:${safeColor(c.background_color, '#F5F5F2')};">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;background:${safeColor(c.surface_color, '#FFFFFF')};border-radius:16px;overflow:hidden;">
        ${c.show_logo && logo ? `<tr><td style="padding:24px 32px 16px;"><img src="${safeUrl(logo, '')}" alt="${esc(c.brand_name)}" style="display:block;max-width:160px;max-height:52px;width:auto;height:auto;border:0;"></td></tr>` : ''}
        ${c.show_hero && hero ? `<tr><td><img src="${safeUrl(hero, '')}" alt="" width="640" style="display:block;width:100%;max-width:640px;height:auto;border:0;"></td></tr>` : ''}
        <tr><td style="padding:36px 32px 16px;">
          <div style="font-size:12px;line-height:18px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:${safeColor(c.secondary_color, '#A3D16B')};">${esc(c.eyebrow)}</div>
          <h1 style="margin:10px 0 14px;font-size:34px;line-height:41px;color:${safeColor(c.primary_color, '#111827')};">${esc(c.headline)}</h1>
          <p style="margin:0;font-size:17px;line-height:27px;color:${safeColor(c.text_color, '#202124')};white-space:pre-line;">${esc(c.body)}</p>
        </td></tr>
        <tr><td style="padding:16px 32px 40px;">
          <a href="${safeUrl(c.cta_url)}" style="display:inline-block;background:${safeColor(c.secondary_color, '#A3D16B')};color:#111111;text-decoration:none;font-size:16px;line-height:20px;font-weight:700;padding:14px 24px;border-radius:8px;">${esc(c.cta_text)}</a>
        </td></tr>
        <tr><td style="padding:24px 32px;background:${safeColor(c.primary_color, '#111827')};color:#ffffff;font-size:12px;line-height:19px;text-align:center;">
          ${esc(c.footer_text)}<br><a href="#" style="color:#ffffff;text-decoration:underline;">Unsubscribe</a>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`
}

