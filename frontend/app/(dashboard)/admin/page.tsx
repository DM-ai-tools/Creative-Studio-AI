'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Select from '@/components/ui/Select'
import { useApi } from '@/hooks/useApi'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { timeAgo, formatFileSize } from '@/lib/utils'
import type { User } from '@/types'
import { useRouter } from 'next/navigation'

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

export default function AdminPage() {
  const router = useRouter()
  const { user } = useAuth()
  const [updatingRole, setUpdatingRole] = useState<string | null>(null)

  const { data: users, isLoading: usersLoading, refetch: refetchUsers } = useApi(
    () => adminApi.listUsers(), []
  )
  const { data: stats, isLoading: statsLoading } = useApi(() => adminApi.getStats(), [])

  if (user?.role !== 'admin') {
    return (
      <div className="p-10 text-center">
        <p className="text-sm text-mid">Admin access required.</p>
        <Button className="mt-3" onClick={() => router.push('/dashboard')}>Back to Dashboard</Button>
      </div>
    )
  }

  const handleRoleChange = async (userId: string, role: string) => {
    setUpdatingRole(userId)
    try {
      await adminApi.updateRole(userId, role)
      toast.success('Role updated')
      refetchUsers()
    } catch {
      toast.error('Failed to update role')
    } finally {
      setUpdatingRole(null)
    }
  }

  const handleDeactivate = async (userId: string) => {
    if (!confirm('Deactivate this user?')) return
    try {
      await adminApi.deactivateUser(userId)
      toast.success('User deactivated')
      refetchUsers()
    } catch {
      toast.error('Failed to deactivate user')
    }
  }

  return (
    <div>
      <Topbar title="Admin Dashboard" subtitle="Manage users, roles, and workspace settings" />

      <div className="p-5 space-y-4">
        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Users', value: statsLoading ? '—' : stats?.users },
            { label: 'Briefs', value: statsLoading ? '—' : stats?.briefs },
            { label: 'Variants', value: statsLoading ? '—' : stats?.variants },
            { label: 'Storage', value: statsLoading ? '—' : formatFileSize(stats?.storage_bytes ?? 0) },
          ].map((s) => (
            <Card key={s.label}>
              <div className="text-xs font-bold text-lt uppercase tracking-wide mb-1">{s.label}</div>
              <div className="text-2xl font-extrabold text-navy">{s.value}</div>
            </Card>
          ))}
        </div>

        {/* Users table */}
        <Card title="Team Members" padding={false}>
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-light">
                {['Name', 'Email', 'Role', 'Status', 'Joined', 'Actions'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usersLoading
                ? [...Array(3)].map((_, i) => (
                    <tr key={i}><td colSpan={6} className="px-4 py-3"><div className="skeleton h-5 rounded" /></td></tr>
                  ))
                : (users ?? []).map((u: User) => (
                    <tr key={u.id} className="border-b border-border hover:bg-light/50">
                      <td className="px-4 py-2.5 font-semibold text-navy">{u.full_name}</td>
                      <td className="px-4 py-2.5 text-mid">{u.email}</td>
                      <td className="px-4 py-2.5">
                        {u.id === user?.id ? (
                          <Badge variant="blue">{u.role}</Badge>
                        ) : (
                          <select
                            value={u.role}
                            onChange={(e) => handleRoleChange(u.id, e.target.value)}
                            disabled={updatingRole === u.id}
                            className="text-xs border border-border rounded px-1.5 py-1 text-navy bg-white"
                          >
                            {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={u.is_active ? 'green' : 'red'}>{u.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      <td className="px-4 py-2.5 text-lt whitespace-nowrap">{timeAgo(u.created_at)}</td>
                      <td className="px-4 py-2.5">
                        {u.id !== user?.id && u.is_active && (
                          <Button size="sm" variant="danger" onClick={() => handleDeactivate(u.id)}>
                            Deactivate
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}
