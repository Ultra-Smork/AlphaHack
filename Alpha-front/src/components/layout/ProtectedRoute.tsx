import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/contexts/AuthContext'
import { toast } from '@/hooks/use-toast'
import type { UserRole } from '@/lib/types'

interface ProtectedRouteProps {
  requiredRole?: UserRole
}

function homeForRole(role: UserRole) {
  return role === 'bank' ? '/bank' : '/applications'
}

function AccessDeniedRedirect({ home }: { home: string }) {
  useEffect(() => {
    toast({
      title: 'Нет доступа',
      description: 'Этот раздел недоступен для вашей роли.',
      variant: 'destructive',
    })
  }, [])

  return <Navigate to={home} replace />
}

export function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { user, token } = useAuth()
  const location = useLocation()

  if (!token || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  const home = homeForRole(user.role)

  if (requiredRole && user.role !== requiredRole) {
    return <AccessDeniedRedirect home={home} />
  }

  return <Outlet />
}
